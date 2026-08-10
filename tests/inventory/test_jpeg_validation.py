from __future__ import annotations

import hashlib
import struct
from datetime import date, datetime, timezone

import cv2
import numpy as np
import pytest

from face_moment.inventory import (
    CapturedAtSource,
    InvalidJpegCandidateError,
    InvalidSpaTimezoneError,
    JpegValidationLimits,
    validate_jpeg_candidate,
)


LIMITS = JpegValidationLimits(
    max_compressed_bytes=50_000,
    max_decoded_side_length=32,
    max_decoded_pixels=800,
)
VISIT_DATE = date(2026, 8, 10)
UPLOAD_STARTED_AT = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)


def _jpeg(
    *,
    width: int = 4,
    height: int = 3,
    exif_datetime: str | None = None,
    exif_offset: str | None = None,
    orientation: int | None = None,
) -> bytes:
    pixels = np.full((height, width, 3), 127, dtype=np.uint8)
    encoded_ok, encoded = cv2.imencode(".jpg", pixels)
    assert encoded_ok
    jpeg = encoded.tobytes()
    if orientation is None and exif_datetime is None:
        return jpeg
    return jpeg[:2] + _exif_segment(
        exif_datetime=exif_datetime,
        exif_offset=exif_offset,
        orientation=orientation,
    ) + jpeg[2:]


def _exif_segment(
    *,
    exif_datetime: str | None,
    exif_offset: str | None,
    orientation: int | None,
) -> bytes:
    ifd0_entries: list[tuple[int, int, int, bytes]] = []
    if orientation is not None:
        ifd0_entries.append((0x0112, 3, 1, struct.pack("<H", orientation)))

    exif_entries: list[tuple[int, int, int, bytes]] = []
    if exif_datetime is not None:
        exif_entries.append((0x9003, 2, len(exif_datetime) + 1, exif_datetime.encode() + b"\0"))
    if exif_offset is not None:
        exif_entries.append((0x9011, 2, len(exif_offset) + 1, exif_offset.encode() + b"\0"))
    if exif_entries:
        ifd0_entries.append((0x8769, 4, 1, b""))

    ifd0_size = 2 + 12 * len(ifd0_entries) + 4
    exif_ifd_offset = 8 + ifd0_size
    exif_ifd_size = 2 + 12 * len(exif_entries) + 4
    value_offset = exif_ifd_offset + exif_ifd_size
    value_bytes = bytearray()

    def write_ifd(
        entries: list[tuple[int, int, int, bytes]], *, exif_pointer: int | None = None
    ) -> bytes:
        nonlocal value_offset
        body = bytearray(struct.pack("<H", len(entries)))
        for tag, field_type, count, value in entries:
            body.extend(struct.pack("<HHI", tag, field_type, count))
            if tag == 0x8769:
                assert exif_pointer is not None
                body.extend(struct.pack("<I", exif_pointer))
            elif len(value) <= 4:
                body.extend(value.ljust(4, b"\0"))
            else:
                body.extend(struct.pack("<I", value_offset))
                value_bytes.extend(value)
                value_offset += len(value)
        body.extend(struct.pack("<I", 0))
        return bytes(body)

    ifd0 = write_ifd(ifd0_entries, exif_pointer=exif_ifd_offset)
    exif_ifd = write_ifd(exif_entries)
    tiff = b"II" + struct.pack("<H", 42) + struct.pack("<I", 8) + ifd0 + exif_ifd + value_bytes
    payload = b"Exif\0\0" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def _validate(
    jpeg: bytes,
    *,
    visit_date: date = VISIT_DATE,
    spa_timezone: str = "Asia/Dushanbe",
    upload_started_at: datetime | None = UPLOAD_STARTED_AT,
    limits: JpegValidationLimits = LIMITS,
):
    return validate_jpeg_candidate(
        jpeg,
        visit_date=visit_date,
        spa_timezone=spa_timezone,
        upload_started_at=upload_started_at,
        limits=limits,
    )


def test_valid_jpeg_is_preserved_and_hashed_before_decode() -> None:
    jpeg = _jpeg()

    candidate = _validate(jpeg)

    assert candidate.original_bytes == jpeg
    assert candidate.checksum_sha256 == hashlib.sha256(jpeg).digest()
    assert candidate.byte_size == len(jpeg)
    assert (candidate.width, candidate.height) == (4, 3)
    assert candidate.captured_at == UPLOAD_STARTED_AT
    assert candidate.captured_at_source is CapturedAtSource.UPLOAD_STARTED_AT
    assert candidate.warning is None


@pytest.mark.parametrize(
    ("jpeg", "limits", "code"),
    [
        (b"\x89PNG\r\n\x1a\nnot-a-jpeg", LIMITS, "unsupported_media_type"),
        (_jpeg(), JpegValidationLimits(10, 32, 800), "compressed_bytes_exceeded"),
        (_jpeg(width=33), LIMITS, "decoded_side_exceeded"),
        (_jpeg(width=30, height=30), LIMITS, "decoded_pixels_exceeded"),
        (b"\xff\xd8\xff\xe0broken", LIMITS, "decode_failed"),
        (_jpeg(orientation=9), LIMITS, "invalid_exif_orientation"),
    ],
)
def test_invalid_media_bounds_decode_and_orientation_are_rejected(
    jpeg: bytes, limits: JpegValidationLimits, code: str
) -> None:
    with pytest.raises(InvalidJpegCandidateError, match=code):
        _validate(jpeg, limits=limits)


def test_reliable_exif_uses_explicit_offset_and_warns_without_replacing_visit_date() -> None:
    candidate = _validate(
        _jpeg(exif_datetime="2026:08:09 23:30:00", exif_offset="+03:00", orientation=1)
    )

    assert candidate.captured_at.isoformat() == "2026-08-09T23:30:00+03:00"
    assert candidate.captured_at_source is CapturedAtSource.EXIF
    assert candidate.visit_date == VISIT_DATE
    assert candidate.warning == "exif_date_mismatch"


def test_naive_exif_uses_spa_timezone_and_unreliable_exif_falls_back_to_upload_start() -> None:
    reliable = _validate(_jpeg(exif_datetime="2026:08:10 11:12:13", orientation=1))
    unreliable = _validate(_jpeg(exif_datetime="not-a-date", orientation=1))

    assert reliable.captured_at.isoformat() == "2026-08-10T11:12:13+05:00"
    assert reliable.captured_at_source is CapturedAtSource.EXIF
    assert unreliable.captured_at == UPLOAD_STARTED_AT
    assert unreliable.captured_at_source is CapturedAtSource.UPLOAD_STARTED_AT


def test_missing_exif_and_upload_start_fall_back_to_authoritative_visit_date() -> None:
    candidate = _validate(_jpeg(), upload_started_at=None)

    assert candidate.visit_date == VISIT_DATE
    assert candidate.captured_at.isoformat() == "2026-08-10T01:00:00+05:00"
    assert candidate.captured_at_source is CapturedAtSource.VISIT_DATE_FALLBACK


def test_invalid_spa_timezone_is_not_silently_interpreted() -> None:
    with pytest.raises(InvalidSpaTimezoneError):
        _validate(_jpeg(), spa_timezone="Invalid/Timezone")

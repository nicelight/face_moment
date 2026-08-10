from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import cv2
import numpy as np


class CapturedAtSource(StrEnum):
    EXIF = "exif"
    UPLOAD_STARTED_AT = "upload_started_at"
    VISIT_DATE_FALLBACK = "visit_date_fallback"


class InvalidJpegCandidateError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class InvalidSpaTimezoneError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class JpegValidationLimits:
    max_compressed_bytes: int
    max_decoded_side_length: int
    max_decoded_pixels: int

    def __post_init__(self) -> None:
        if any(
            value <= 0
            for value in (
                self.max_compressed_bytes,
                self.max_decoded_side_length,
                self.max_decoded_pixels,
            )
        ):
            raise ValueError("JPEG validation limits must be positive")


@dataclass(frozen=True, slots=True)
class ValidatedJpegCandidate:
    original_bytes: bytes
    checksum_sha256: bytes
    byte_size: int
    width: int
    height: int
    visit_date: date
    captured_at: datetime
    captured_at_source: CapturedAtSource
    warning: str | None


@dataclass(frozen=True, slots=True)
class _ExifMetadata:
    orientation: int | None
    captured_at_text: str | None
    offset_text: str | None


def validate_jpeg_candidate(
    original_bytes: bytes,
    *,
    visit_date: date,
    spa_timezone: str,
    upload_started_at: datetime | None,
    limits: JpegValidationLimits,
) -> ValidatedJpegCandidate:
    """Return one bounded inventory candidate without staging or persistence."""
    timezone_info = _spa_timezone(spa_timezone)
    if not original_bytes.startswith(b"\xff\xd8"):
        raise InvalidJpegCandidateError("unsupported_media_type")
    if len(original_bytes) > limits.max_compressed_bytes:
        raise InvalidJpegCandidateError("compressed_bytes_exceeded")

    exif = _read_exif(original_bytes)
    if exif.orientation is not None and exif.orientation not in range(1, 9):
        raise InvalidJpegCandidateError("invalid_exif_orientation")

    image = cv2.imdecode(
        np.frombuffer(original_bytes, dtype=np.uint8),
        cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION,
    )
    if image is None or image.size == 0:
        raise InvalidJpegCandidateError("decode_failed")
    height, width = image.shape[:2]
    if max(width, height) > limits.max_decoded_side_length:
        raise InvalidJpegCandidateError("decoded_side_exceeded")
    if width * height > limits.max_decoded_pixels:
        raise InvalidJpegCandidateError("decoded_pixels_exceeded")

    exif_captured_at = _parse_reliable_exif(exif, timezone_info)
    if exif_captured_at is not None:
        captured_at = exif_captured_at
        captured_at_source = CapturedAtSource.EXIF
    elif upload_started_at is not None:
        if upload_started_at.tzinfo is None or upload_started_at.utcoffset() is None:
            raise ValueError("upload_started_at must be timezone-aware")
        captured_at = upload_started_at
        captured_at_source = CapturedAtSource.UPLOAD_STARTED_AT
    else:
        captured_at = datetime.combine(visit_date, datetime.min.time(), timezone_info).replace(
            hour=1
        )
        captured_at_source = CapturedAtSource.VISIT_DATE_FALLBACK

    warning = (
        "exif_date_mismatch"
        if exif_captured_at is not None and exif_captured_at.date() != visit_date
        else None
    )
    return ValidatedJpegCandidate(
        original_bytes=original_bytes,
        checksum_sha256=hashlib.sha256(original_bytes).digest(),
        byte_size=len(original_bytes),
        width=width,
        height=height,
        visit_date=visit_date,
        captured_at=captured_at,
        captured_at_source=captured_at_source,
        warning=warning,
    )


def _spa_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as error:
        raise InvalidSpaTimezoneError(name) from error


def _parse_reliable_exif(
    exif: _ExifMetadata, spa_timezone: ZoneInfo
) -> datetime | None:
    if exif.captured_at_text is None:
        return None
    try:
        local_time = datetime.strptime(exif.captured_at_text, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    if exif.offset_text is not None:
        offset = _parse_offset(exif.offset_text)
        return local_time.replace(tzinfo=offset) if offset is not None else None
    if not _is_real_local_time(local_time, spa_timezone):
        return None
    return local_time.replace(tzinfo=spa_timezone)


def _parse_offset(value: str) -> timezone | None:
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":":
        return None
    try:
        hours = int(value[1:3])
        minutes = int(value[4:6])
    except ValueError:
        return None
    if hours > 23 or minutes > 59:
        return None
    direction = 1 if value[0] == "+" else -1
    return timezone(direction * timedelta(hours=hours, minutes=minutes))


def _is_real_local_time(value: datetime, timezone_info: ZoneInfo) -> bool:
    aware = value.replace(tzinfo=timezone_info)
    return aware.astimezone(timezone.utc).astimezone(timezone_info).replace(tzinfo=None) == value


def _read_exif(jpeg: bytes) -> _ExifMetadata:
    for app1_payload in _app1_payloads(jpeg):
        if not app1_payload.startswith(b"Exif\0\0"):
            continue
        metadata = _read_exif_tiff(app1_payload[6:])
        if metadata is not None:
            return metadata
    return _ExifMetadata(orientation=None, captured_at_text=None, offset_text=None)


def _app1_payloads(jpeg: bytes) -> list[bytes]:
    payloads: list[bytes] = []
    position = 2
    while position + 4 <= len(jpeg) and jpeg[position] == 0xFF:
        while position < len(jpeg) and jpeg[position] == 0xFF:
            position += 1
        if position >= len(jpeg):
            break
        marker = jpeg[position]
        position += 1
        if marker in (0xD9, 0xDA):
            break
        if marker in (0x01, *range(0xD0, 0xD8)):
            continue
        if position + 2 > len(jpeg):
            break
        segment_length = struct.unpack(">H", jpeg[position : position + 2])[0]
        if segment_length < 2 or position + segment_length > len(jpeg):
            break
        segment_start = position + 2
        segment_end = position + segment_length
        if marker == 0xE1:
            payloads.append(jpeg[segment_start:segment_end])
        position = segment_end
    return payloads


def _read_exif_tiff(tiff: bytes) -> _ExifMetadata | None:
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return None
    byte_order = "<" if tiff[:2] == b"II" else ">"
    if _uint16(tiff, 2, byte_order) != 42:
        return None
    ifd0_offset = _uint32(tiff, 4, byte_order)
    if ifd0_offset is None:
        return None
    ifd0 = _ifd_entries(tiff, ifd0_offset, byte_order)
    if ifd0 is None:
        return None
    orientation = _entry_integer(tiff, ifd0.get(0x0112), byte_order)
    exif_offset = _entry_integer(tiff, ifd0.get(0x8769), byte_order)
    if exif_offset is None:
        return _ExifMetadata(orientation=orientation, captured_at_text=None, offset_text=None)
    exif_ifd = _ifd_entries(tiff, exif_offset, byte_order)
    if exif_ifd is None:
        return _ExifMetadata(orientation=orientation, captured_at_text=None, offset_text=None)

    original = _entry_ascii(tiff, exif_ifd.get(0x9003), byte_order)
    if original is not None:
        return _ExifMetadata(
            orientation=orientation,
            captured_at_text=original,
            offset_text=_entry_ascii(tiff, exif_ifd.get(0x9011), byte_order),
        )
    return _ExifMetadata(
        orientation=orientation,
        captured_at_text=_entry_ascii(tiff, exif_ifd.get(0x9004), byte_order),
        offset_text=_entry_ascii(tiff, exif_ifd.get(0x9012), byte_order),
    )


def _ifd_entries(
    tiff: bytes, offset: int, byte_order: str
) -> dict[int, tuple[int, int, int]] | None:
    count = _uint16(tiff, offset, byte_order)
    if count is None or offset + 2 + count * 12 + 4 > len(tiff):
        return None
    entries: dict[int, tuple[int, int, int]] = {}
    for index in range(count):
        entry_offset = offset + 2 + index * 12
        tag = _uint16(tiff, entry_offset, byte_order)
        field_type = _uint16(tiff, entry_offset + 2, byte_order)
        value_count = _uint32(tiff, entry_offset + 4, byte_order)
        value_or_offset = _uint32(tiff, entry_offset + 8, byte_order)
        if (
            tag is not None
            and field_type is not None
            and value_count is not None
            and value_or_offset is not None
        ):
            entries[tag] = (field_type, value_count, value_or_offset)
    return entries


def _entry_integer(
    tiff: bytes, entry: tuple[int, int, int] | None, byte_order: str
) -> int | None:
    if entry is None:
        return None
    field_type, count, value_or_offset = entry
    if count != 1:
        return None
    if field_type == 3:
        return value_or_offset & 0xFFFF if byte_order == "<" else value_or_offset >> 16
    if field_type == 4:
        return value_or_offset
    return None


def _entry_ascii(
    tiff: bytes, entry: tuple[int, int, int] | None, byte_order: str
) -> str | None:
    if entry is None:
        return None
    field_type, count, value_or_offset = entry
    if field_type != 2 or count == 0:
        return None
    if count <= 4:
        packed = struct.pack(f"{byte_order}I", value_or_offset)[:count]
    elif value_or_offset + count <= len(tiff):
        packed = tiff[value_or_offset : value_or_offset + count]
    else:
        return None
    try:
        return packed.rstrip(b"\0").decode("ascii")
    except UnicodeDecodeError:
        return ""


def _uint16(data: bytes, offset: int, byte_order: str) -> int | None:
    if offset < 0 or offset + 2 > len(data):
        return None
    return int(struct.unpack_from(f"{byte_order}H", data, offset)[0])


def _uint32(data: bytes, offset: int, byte_order: str) -> int | None:
    if offset < 0 or offset + 4 > len(data):
        return None
    return int(struct.unpack_from(f"{byte_order}I", data, offset)[0])

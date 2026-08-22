"""Task-owned parsing and admission boundary for realtime proposals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import math
from collections.abc import Mapping
from typing import Any, TypedDict
import uuid

import cv2
import numpy as np
from multipart import MultipartParser
from multipart.multipart import MultipartParseError, parse_options_header

from face_moment.infrastructure.settings import DEFAULT_REALTIME_DEADLINE_MS
from face_moment.processing.revisions import PipelineCode
from face_moment.serving_control.realtime_context import RealtimeContext

MAX_REALTIME_BODY_BYTES = 20_971_520
MAX_OCCURRENCES = 20
_MANIFEST_CONTENT_TYPE = "application/json; charset=utf-8"
_JPEG_CONTENT_TYPE = "image/jpeg"
_DETECTOR_ID = "mediapipe_blazeface_full_range"
_JPEG_QUALITIES = {0.7, 0.75, 0.8, 0.85, 0.9, 0.95}
_MANIFEST_FIELDS = {
    "schema_version",
    "attempt_id",
    "trigger_source",
    "client_release",
    "detector_id",
    "model_version",
    "jpeg_quality",
    "camera_device_id",
    "timing",
    "occurrences",
}
_TIMING_FIELDS = {
    "reference_series_ready_at",
    "local_detection_completed_ms",
    "request_started_ms",
}
_OCCURRENCE_FIELDS = {
    "occurrence_index",
    "frame_index",
    "frame_offset_ms",
    "detector_confidence",
    "crop_part",
}


class RealtimePayloadError(ValueError):
    """The multipart request is outside the accepted v1 transport contract."""


class RealtimeBodyTooLargeError(RealtimePayloadError):
    pass


@dataclass(frozen=True, slots=True)
class MultipartPart:
    name: str
    filename: str | None
    content_type: str | None
    body: bytes


@dataclass(frozen=True, slots=True)
class RealtimeAdmissionPayload:
    attempt_id: uuid.UUID
    trigger_source: str
    client_release: str
    detector_id: str
    model_version: str
    jpeg_quality: int
    camera_device_id: str
    reference_series_ready_at: datetime
    local_detection_completed_ms: int
    request_started_ms: int
    occurrences: tuple[MultipartPart, ...]

    @property
    def proposal_count(self) -> int:
        return len(self.occurrences)


class AdmissionRepositoryValues(TypedDict):
    spa_id: uuid.UUID
    client_attempt_id: uuid.UUID
    trigger_source: str
    client_release: str
    detector_id: str
    model_version: str
    jpeg_quality: int
    camera_device_id: str
    reference_series_ready_at: datetime
    local_detection_completed_ms: int
    request_started_ms: int
    proposal_count: int
    settings_revision: int
    visit_date: date
    pipeline_revision_id: uuid.UUID
    pipeline_code: PipelineCode
    query_source: str
    threshold: float
    quality_settings: Mapping[str, object]
    release_id: str
    deadline_ms: int
    calibration_id: uuid.UUID | None


def parse_realtime_multipart(body: bytes, content_type: str | None) -> RealtimeAdmissionPayload:
    if len(body) > MAX_REALTIME_BODY_BYTES:
        raise RealtimeBodyTooLargeError
    if content_type is None:
        raise RealtimePayloadError("multipart content type is required")
    media_type, options = parse_options_header(content_type)
    if media_type.lower() != b"multipart/form-data" or b"boundary" not in options:
        raise RealtimePayloadError("multipart/form-data with a boundary is required")
    boundary = options[b"boundary"]
    parts = _parse_parts(body, boundary)
    if not parts or parts[0].name != "manifest":
        raise RealtimePayloadError("manifest must be the first part")
    manifest = _decode_manifest(parts[0])
    occurrences = manifest["occurrences"]
    if len(parts) != len(occurrences) + 1:
        raise RealtimePayloadError("multipart parts do not match occurrences")
    crop_parts: list[MultipartPart] = []
    for index, part in enumerate(parts[1:]):
        expected_name = f"crop_{index:03d}"
        if part.name != expected_name or part.filename != f"{expected_name}.jpg":
            raise RealtimePayloadError("crop parts must be ordered and named exactly")
        if part.content_type != _JPEG_CONTENT_TYPE:
            raise RealtimePayloadError("crop parts must be image/jpeg")
        _validate_jpeg(part.body)
        occurrence = occurrences[index]
        if occurrence["crop_part"] != expected_name:
            raise RealtimePayloadError("occurrence crop_part does not match its part")
        crop_parts.append(part)
    return RealtimeAdmissionPayload(
        attempt_id=manifest["attempt_id"],
        trigger_source=manifest["trigger_source"],
        client_release=manifest["client_release"],
        detector_id=manifest["detector_id"],
        model_version=manifest["model_version"],
        jpeg_quality=manifest["jpeg_quality"],
        camera_device_id=manifest["camera_device_id"],
        reference_series_ready_at=manifest["reference_series_ready_at"],
        local_detection_completed_ms=manifest["local_detection_completed_ms"],
        request_started_ms=manifest["request_started_ms"],
        occurrences=tuple(crop_parts),
    )


def _parse_parts(body: bytes, boundary: bytes) -> list[MultipartPart]:
    parts: list[MultipartPart] = []
    current_headers: dict[str, str] = {}
    current_data = bytearray()
    current: dict[str, str | None] | None = None
    header_name = bytearray()
    header_value = bytearray()
    ended = False

    def on_part_begin() -> None:
        nonlocal current_headers, current_data, current
        current_headers = {}
        current_data = bytearray()
        current = None

    def on_header_field(data: bytes, start: int, end: int) -> None:
        header_name.extend(data[start:end])

    def on_header_value(data: bytes, start: int, end: int) -> None:
        header_value.extend(data[start:end])

    def on_header_end() -> None:
        name = header_name.decode("ascii").lower()
        if name in current_headers:
            raise RealtimePayloadError("duplicate multipart header")
        current_headers[name] = header_value.decode("latin-1").strip()
        header_name.clear()
        header_value.clear()

    def on_headers_finished() -> None:
        nonlocal current
        disposition = current_headers.get("content-disposition")
        if disposition is None:
            raise RealtimePayloadError("part name is required")
        kind, options = parse_options_header(disposition)
        if kind.lower() != b"form-data" or b"name" not in options:
            raise RealtimePayloadError("invalid content disposition")
        try:
            name = options[b"name"].decode("utf-8")
            filename = (
                options[b"filename"].decode("utf-8") if b"filename" in options else None
            )
        except UnicodeDecodeError as error:
            raise RealtimePayloadError("multipart names must be UTF-8") from error
        current = {"name": name, "filename": filename}

    def on_part_data(data: bytes, start: int, end: int) -> None:
        current_data.extend(data[start:end])

    def on_part_end() -> None:
        if current is None or current["name"] is None:
            raise RealtimePayloadError("part headers are incomplete")
        parts.append(
            MultipartPart(
                name=current["name"] or "",
                filename=current["filename"],
                content_type=current_headers.get("content-type"),
                body=bytes(current_data),
            )
        )

    def on_end() -> None:
        nonlocal ended
        ended = True

    callbacks = {
        "on_part_begin": on_part_begin,
        "on_header_field": on_header_field,
        "on_header_value": on_header_value,
        "on_header_end": on_header_end,
        "on_headers_finished": on_headers_finished,
        "on_part_data": on_part_data,
        "on_part_end": on_part_end,
        "on_end": on_end,
    }
    try:
        parser = MultipartParser(boundary, callbacks, max_size=MAX_REALTIME_BODY_BYTES)
        parser.write(body)
        parser.finalize()
    except (MultipartParseError, UnicodeDecodeError, ValueError, KeyError) as error:
        if isinstance(error, RealtimePayloadError):
            raise
        raise RealtimePayloadError("malformed multipart body") from error
    if not ended:
        raise RealtimePayloadError("multipart body is incomplete")
    return parts


def _decode_manifest(part: MultipartPart) -> dict[str, Any]:
    if part.content_type != _MANIFEST_CONTENT_TYPE:
        raise RealtimePayloadError("manifest content type is invalid")
    try:
        text = part.body.decode("utf-8")
        manifest = json.loads(text, object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RealtimePayloadError) as error:
        raise RealtimePayloadError("manifest must be strict UTF-8 JSON") from error
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS:
        raise RealtimePayloadError("manifest fields are not the v1 allow-list")
    _require_int(manifest["schema_version"], "schema_version", exact=1)
    attempt_id = _uuid(manifest["attempt_id"], "attempt_id")
    trigger_source = _nonempty_string(manifest["trigger_source"], "trigger_source")
    if trigger_source not in {"sensor", "test"}:
        raise RealtimePayloadError("trigger_source is invalid")
    client_release = _nonempty_string(manifest["client_release"], "client_release")
    model_version = _nonempty_string(manifest["model_version"], "model_version")
    camera_device_id = _nonempty_string(manifest["camera_device_id"], "camera_device_id")
    detector_id = _nonempty_string(manifest["detector_id"], "detector_id")
    if detector_id != _DETECTOR_ID:
        raise RealtimePayloadError("detector_id is invalid")
    jpeg_quality_value = manifest["jpeg_quality"]
    if (
        isinstance(jpeg_quality_value, bool)
        or not isinstance(jpeg_quality_value, (int, float))
        or not math.isfinite(float(jpeg_quality_value))
        or float(jpeg_quality_value) not in _JPEG_QUALITIES
    ):
        raise RealtimePayloadError("jpeg_quality is invalid")
    timing = manifest["timing"]
    if not isinstance(timing, dict) or set(timing) != _TIMING_FIELDS:
        raise RealtimePayloadError("timing fields are invalid")
    ready_at = _timestamp(timing["reference_series_ready_at"])
    local_done = _require_int(timing["local_detection_completed_ms"], "local_detection_completed_ms")
    request_started = _require_int(timing["request_started_ms"], "request_started_ms")
    if local_done > request_started:
        raise RealtimePayloadError("client monotonic markers are out of order")
    raw_occurrences = manifest["occurrences"]
    if not isinstance(raw_occurrences, list) or len(raw_occurrences) > MAX_OCCURRENCES:
        raise RealtimePayloadError("occurrences are not bounded")
    normalized_occurrences: list[dict[str, Any]] = []
    prior_frame = -1
    prior_offset = -1
    for index, raw_occurrence in enumerate(raw_occurrences):
        if not isinstance(raw_occurrence, dict) or set(raw_occurrence) != _OCCURRENCE_FIELDS:
            raise RealtimePayloadError("occurrence fields are invalid")
        _require_int(raw_occurrence["occurrence_index"], "occurrence_index", exact=index)
        frame_index = _require_int(raw_occurrence["frame_index"], "frame_index", minimum=0)
        frame_offset = _require_int(raw_occurrence["frame_offset_ms"], "frame_offset_ms", minimum=0)
        confidence = raw_occurrence["detector_confidence"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0 <= float(confidence) <= 1
        ):
            raise RealtimePayloadError("detector_confidence is invalid")
        crop_part = _nonempty_string(raw_occurrence["crop_part"], "crop_part")
        if crop_part != f"crop_{index:03d}" or frame_index < prior_frame or frame_offset < prior_offset:
            raise RealtimePayloadError("occurrences are not chronological")
        prior_frame, prior_offset = frame_index, frame_offset
        normalized_occurrences.append({"crop_part": crop_part})
    return {
        "schema_version": 1,
        "attempt_id": attempt_id,
        "trigger_source": trigger_source,
        "client_release": client_release,
        "detector_id": detector_id,
        "model_version": model_version,
        "jpeg_quality": int(round(float(jpeg_quality_value) * 100)),
        "camera_device_id": camera_device_id,
        "reference_series_ready_at": ready_at,
        "local_detection_completed_ms": local_done,
        "request_started_ms": request_started,
        "occurrences": normalized_occurrences,
    }


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RealtimePayloadError("duplicate JSON field")
        result[key] = value
    return result


def _uuid(value: object, field_name: str) -> uuid.UUID:
    if not isinstance(value, str):
        raise RealtimePayloadError(f"{field_name} must be a UUID")
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise RealtimePayloadError(f"{field_name} must be a UUID") from error


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise RealtimePayloadError("reference_series_ready_at must be RFC 3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RealtimePayloadError("reference_series_ready_at must be RFC 3339") from error
    if parsed.tzinfo is None:
        raise RealtimePayloadError("reference_series_ready_at must include a timezone")
    return parsed


def _nonempty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 255:
        raise RealtimePayloadError(f"{field_name} must be a bounded non-empty string")
    return value


def _require_int(value: object, field_name: str, *, exact: int | None = None, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RealtimePayloadError(f"{field_name} must be an integer")
    if exact is not None and value != exact:
        raise RealtimePayloadError(f"{field_name} has an unexpected value")
    if minimum is not None and value < minimum:
        raise RealtimePayloadError(f"{field_name} must be non-negative")
    return value


def _validate_jpeg(body: bytes) -> None:
    if b"Exif\x00\x00" in body or b"http://ns.adobe.com/xap/1.0/" in body:
        raise RealtimePayloadError("JPEG metadata is not allowed")
    decoded = cv2.imdecode(np.frombuffer(body, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None or decoded.ndim < 2:
        raise RealtimePayloadError("crop is not a decodable JPEG")
    height, width = decoded.shape[:2]
    if width <= 0 or height <= 0 or width > 512 or height > 512:
        raise RealtimePayloadError("crop dimensions exceed the accepted geometry")


def admission_values(
    payload: RealtimeAdmissionPayload,
    context: RealtimeContext,
    *,
    deadline_ms: int = DEFAULT_REALTIME_DEADLINE_MS,
) -> AdmissionRepositoryValues:
    """Translate validated client data and owner context to repository fields."""

    if isinstance(deadline_ms, bool) or not isinstance(deadline_ms, int) or deadline_ms <= 0:
        raise ValueError("deadline_ms must be positive")
    return {
        "spa_id": context.spa_id,
        "client_attempt_id": payload.attempt_id,
        "trigger_source": payload.trigger_source,
        "client_release": payload.client_release,
        "detector_id": payload.detector_id,
        "model_version": payload.model_version,
        "jpeg_quality": payload.jpeg_quality,
        "camera_device_id": payload.camera_device_id,
        "reference_series_ready_at": payload.reference_series_ready_at,
        "local_detection_completed_ms": payload.local_detection_completed_ms,
        "request_started_ms": payload.request_started_ms,
        "proposal_count": payload.proposal_count,
        "settings_revision": context.settings_revision,
        "visit_date": context.visit_date,
        "pipeline_revision_id": context.pipeline_revision_id,
        "pipeline_code": context.pipeline_code,
        "query_source": context.query_source.value,
        "threshold": context.reference_threshold,
        "quality_settings": context.quality_settings,
        "release_id": context.release_id,
        "deadline_ms": deadline_ms,
        "calibration_id": context.calibration_id,
    }

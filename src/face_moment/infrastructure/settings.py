from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_REALTIME_DEADLINE_MS = 3000
DEFAULT_REALTIME_RATE_LIMIT = 60
DEFAULT_REALTIME_RATE_WINDOW_SECONDS = 60
DEFAULT_REALTIME_RESULT_DISPLAY_MS = 15000
DEFAULT_PROMO_QR_TICKET_SECRET = "face-moment-development-only-qr-ticket"


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    postgresql_capacity_view_path: str
    postgresql_capacity_low_threshold_bytes: int
    minio_capacity_view_path: str
    minio_capacity_low_threshold_bytes: int
    dependency_wait_seconds: float
    staff_session_ttl_seconds: int
    staff_login_rate_limit: int
    staff_login_rate_window_seconds: int
    photo_upload_rate_limit: int
    photo_upload_rate_window_seconds: int
    photo_upload_max_compressed_bytes: int
    photo_upload_max_decoded_side_length: int
    photo_upload_max_decoded_pixels: int
    background_worker_idle_seconds: float
    photo_preview_maximum_edge: int
    photo_preview_jpeg_quality: int
    photo_thumbnail_maximum_edge: int
    photo_thumbnail_jpeg_quality: int
    sface_detector_path: str | None
    sface_detector_id: str | None
    sface_detector_version: str | None
    sface_recognizer_path: str | None
    sface_recognizer_id: str | None
    sface_recognizer_version: str | None
    sface_preprocessing_version: str | None
    sface_alignment_version: str | None
    sface_normalization_version: str | None
    sface_embedding_dimension: int | None
    buffalo_detector_path: str | None
    buffalo_detector_id: str | None
    buffalo_detector_version: str | None
    buffalo_recognizer_path: str | None
    buffalo_recognizer_id: str | None
    buffalo_recognizer_version: str | None
    buffalo_preprocessing_version: str | None
    buffalo_alignment_version: str | None
    buffalo_normalization_version: str | None
    buffalo_embedding_dimension: int | None
    realtime_deadline_ms: int = DEFAULT_REALTIME_DEADLINE_MS
    realtime_rate_limit: int = DEFAULT_REALTIME_RATE_LIMIT
    realtime_rate_window_seconds: int = DEFAULT_REALTIME_RATE_WINDOW_SECONDS
    realtime_result_display_ms: int = DEFAULT_REALTIME_RESULT_DISPLAY_MS
    promo_qr_ticket_secret: str = DEFAULT_PROMO_QR_TICKET_SECRET

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=_required("DATABASE_URL"),
            s3_endpoint_url=_required("S3_ENDPOINT_URL"),
            s3_access_key=_required("S3_ACCESS_KEY"),
            s3_secret_key=_required("S3_SECRET_KEY"),
            s3_bucket=_required("S3_BUCKET"),
            postgresql_capacity_view_path=_required("POSTGRESQL_CAPACITY_VIEW_PATH"),
            postgresql_capacity_low_threshold_bytes=_positive_int(
                "POSTGRESQL_CAPACITY_LOW_THRESHOLD_BYTES", "1073741824"
            ),
            minio_capacity_view_path=_required("MINIO_CAPACITY_VIEW_PATH"),
            minio_capacity_low_threshold_bytes=_positive_int(
                "MINIO_CAPACITY_LOW_THRESHOLD_BYTES", "1073741824"
            ),
            dependency_wait_seconds=float(
                os.environ.get("DEPENDENCY_WAIT_SECONDS", "60")
            ),
            staff_session_ttl_seconds=_positive_int(
                "STAFF_SESSION_TTL_SECONDS", "28800"
            ),
            staff_login_rate_limit=_positive_int("STAFF_LOGIN_RATE_LIMIT", "10"),
            staff_login_rate_window_seconds=_positive_int(
                "STAFF_LOGIN_RATE_WINDOW_SECONDS", "60"
            ),
            photo_upload_rate_limit=_positive_int("PHOTO_UPLOAD_RATE_LIMIT", "10"),
            photo_upload_rate_window_seconds=_positive_int(
                "PHOTO_UPLOAD_RATE_WINDOW_SECONDS", "60"
            ),
            photo_upload_max_compressed_bytes=_positive_int(
                "PHOTO_UPLOAD_MAX_COMPRESSED_BYTES", "10485760"
            ),
            photo_upload_max_decoded_side_length=_positive_int(
                "PHOTO_UPLOAD_MAX_DECODED_SIDE_LENGTH", "4096"
            ),
            photo_upload_max_decoded_pixels=_positive_int(
                "PHOTO_UPLOAD_MAX_DECODED_PIXELS", "16777216"
            ),
            background_worker_idle_seconds=_positive_float(
                "BACKGROUND_WORKER_IDLE_SECONDS", "0.2"
            ),
            photo_preview_maximum_edge=_positive_int(
                "PHOTO_PREVIEW_MAXIMUM_EDGE", "1024"
            ),
            photo_preview_jpeg_quality=_jpeg_quality(
                "PHOTO_PREVIEW_JPEG_QUALITY", "82"
            ),
            photo_thumbnail_maximum_edge=_positive_int(
                "PHOTO_THUMBNAIL_MAXIMUM_EDGE", "320"
            ),
            photo_thumbnail_jpeg_quality=_jpeg_quality(
                "PHOTO_THUMBNAIL_JPEG_QUALITY", "75"
            ),
            sface_detector_path=_optional("SFACE_DETECTOR_PATH"),
            sface_detector_id=_optional("SFACE_DETECTOR_ID"),
            sface_detector_version=_optional("SFACE_DETECTOR_VERSION"),
            sface_recognizer_path=_optional("SFACE_RECOGNIZER_PATH"),
            sface_recognizer_id=_optional("SFACE_RECOGNIZER_ID"),
            sface_recognizer_version=_optional("SFACE_RECOGNIZER_VERSION"),
            sface_preprocessing_version=_optional("SFACE_PREPROCESSING_VERSION"),
            sface_alignment_version=_optional("SFACE_ALIGNMENT_VERSION"),
            sface_normalization_version=_optional("SFACE_NORMALIZATION_VERSION"),
            sface_embedding_dimension=_optional_positive_int(
                "SFACE_EMBEDDING_DIMENSION"
            ),
            buffalo_detector_path=_optional("BUFFALO_DETECTOR_PATH"),
            buffalo_detector_id=_optional("BUFFALO_DETECTOR_ID"),
            buffalo_detector_version=_optional("BUFFALO_DETECTOR_VERSION"),
            buffalo_recognizer_path=_optional("BUFFALO_RECOGNIZER_PATH"),
            buffalo_recognizer_id=_optional("BUFFALO_RECOGNIZER_ID"),
            buffalo_recognizer_version=_optional("BUFFALO_RECOGNIZER_VERSION"),
            buffalo_preprocessing_version=_optional("BUFFALO_PREPROCESSING_VERSION"),
            buffalo_alignment_version=_optional("BUFFALO_ALIGNMENT_VERSION"),
            buffalo_normalization_version=_optional("BUFFALO_NORMALIZATION_VERSION"),
            buffalo_embedding_dimension=_optional_positive_int(
                "BUFFALO_EMBEDDING_DIMENSION"
            ),
            realtime_deadline_ms=_positive_int(
                "REALTIME_DEADLINE_MS", str(DEFAULT_REALTIME_DEADLINE_MS)
            ),
            realtime_rate_limit=_positive_int(
                "REALTIME_RATE_LIMIT", str(DEFAULT_REALTIME_RATE_LIMIT)
            ),
            realtime_rate_window_seconds=_positive_int(
                "REALTIME_RATE_WINDOW_SECONDS",
                str(DEFAULT_REALTIME_RATE_WINDOW_SECONDS),
            ),
            realtime_result_display_ms=_positive_int(
                "REALTIME_RESULT_DISPLAY_MS",
                str(DEFAULT_REALTIME_RESULT_DISPLAY_MS),
            ),
            promo_qr_ticket_secret=os.environ.get(
                "PROMO_QR_TICKET_SECRET", DEFAULT_PROMO_QR_TICKET_SECRET
            ),
        )


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required setting is missing: {name}")
    return value


def _positive_int(name: str, default: str) -> int:
    value = os.environ.get(name, default)
    try:
        parsed = int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer") from error
    if parsed <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return parsed


def _positive_float(name: str, default: str) -> float:
    value = os.environ.get(name, default)
    try:
        parsed = float(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive number") from error
    if parsed <= 0:
        raise RuntimeError(f"{name} must be a positive number")
    return parsed


def _jpeg_quality(name: str, default: str) -> int:
    value = _positive_int(name, default)
    if value > 100:
        raise RuntimeError(f"{name} must be in 1..100")
    return value


def _optional(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _optional_positive_int(name: str) -> int | None:
    value = _optional(name)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer") from error
    if parsed <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return parsed

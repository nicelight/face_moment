"""Inventory-owned application boundary for one secured Photo upload."""

from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.admission import AdmissionCandidate, AdmissionResult, AtomicPhotoAdmission
from face_moment.inventory.candidate_staging import CandidateStager
from face_moment.inventory.validation import JpegValidationLimits, ValidatedJpegCandidate, validate_jpeg_candidate
from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import authenticate_unsafe_staff_request
from face_moment.serving_control import (
    InactiveIngestTargetError,
    IneligibleIngestTargetError,
    IngestTargetRepository,
    InvalidIngestTargetTimezoneError,
    UnknownIngestTargetError,
)


class PhotographerAccessDeniedError(PermissionError):
    """The current staff principal cannot admit a Photo."""


class InvalidPhotoUploadError(ValueError):
    """The exact upload request cannot become an inventory candidate."""


class PhotoUploadRateLimitError(Exception):
    """The authenticated principal has exceeded the configured upload limit."""


@dataclass(frozen=True, slots=True)
class PhotoUploadResult:
    admission: AdmissionResult
    warnings: list[str]


class PhotoUploadRateLimiter:
    """Single-backend limiter keyed by authenticated principal and client IP."""

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = timedelta(seconds=window_seconds)
        self._attempts: dict[tuple[uuid.UUID, str], deque[datetime]] = {}
        self._lock = threading.Lock()

    def allow(self, *, principal_id: uuid.UUID, ip_address: str, now: datetime) -> bool:
        key = (principal_id, ip_address)
        cutoff = now - self._window
        with self._lock:
            attempts = self._attempts.setdefault(key, deque())
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self._limit:
                return False
            attempts.append(now)
            return True


def upload_photo(
    database_session: Session,
    *,
    settings: Settings,
    rate_limiter: PhotoUploadRateLimiter,
    session_token: str | None,
    csrf_cookie_token: str | None,
    csrf_header_token: str | None,
    ip_address: str,
    spa_id: uuid.UUID,
    visit_date: date,
    photo_bytes: bytes,
) -> PhotoUploadResult:
    """Authenticate, authorize and admit exactly one validated JPEG through inventory."""
    principal = authenticate_unsafe_staff_request(
        database_session,
        session_token=session_token,
        csrf_cookie_token=csrf_cookie_token,
        csrf_header_token=csrf_header_token,
    )
    if principal.role is not StaffRole.PHOTOGRAPHER:
        raise PhotographerAccessDeniedError
    if not rate_limiter.allow(
        principal_id=principal.staff_user_id,
        ip_address=ip_address,
        now=datetime.now(timezone.utc),
    ):
        raise PhotoUploadRateLimitError

    try:
        target = IngestTargetRepository(database_session).resolve_ingest_target(spa_id)
    except (
        UnknownIngestTargetError,
        InactiveIngestTargetError,
        InvalidIngestTargetTimezoneError,
        IneligibleIngestTargetError,
    ) as error:
        raise InvalidPhotoUploadError from error

    validated = validate_jpeg_candidate(
        photo_bytes,
        visit_date=visit_date,
        spa_timezone=target.timezone,
        upload_started_at=datetime.now(timezone.utc),
        limits=JpegValidationLimits(
            max_compressed_bytes=settings.photo_upload_max_compressed_bytes,
            max_decoded_side_length=settings.photo_upload_max_decoded_side_length,
            max_decoded_pixels=settings.photo_upload_max_decoded_pixels,
        ),
    )
    # Authentication and target reads begin SQLAlchemy's implicit read transaction.
    # The existing admission boundary owns the subsequent short write transaction.
    database_session.rollback()
    stager = CandidateStager(PrivateObjectStore(settings))
    staged_candidate = stager.stage(validated.original_bytes)
    admission = AtomicPhotoAdmission(database_session).admit(
        ingest_target=target,
        uploader_id=principal.staff_user_id,
        candidate=AdmissionCandidate(
            staged_candidate=staged_candidate,
            validated_jpeg=validated,
        ),
        cleanup_losing_candidate=stager.cleanup,
    )
    return PhotoUploadResult(admission=admission, warnings=_warnings(validated))


def _warnings(candidate: ValidatedJpegCandidate) -> list[str]:
    return ["exif_visit_date_mismatch"] if candidate.warning is not None else []

"""Inventory-owned authenticated read of one Photo processing projection."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import get_current_principal
from face_moment.processing import read_photo_processing_projection


class PhotoProcessingStatusAccessDeniedError(PermissionError):
    """The active staff principal may not read this Photo."""


class PhotoProcessingStatusNotFoundError(LookupError):
    """The requested inventory-owned Photo does not exist."""


class PhotoProcessingStateUnavailableError(RuntimeError):
    """The required processing-owned projection could not be read."""


@dataclass(frozen=True, slots=True)
class PhotoProcessingStatus:
    """Exact safe response assembled by inventory from owner-backed reads."""

    photo_id: uuid.UUID
    pipeline_revision_id: uuid.UUID
    pipeline_code: str
    processing_status: str
    searchable: bool
    attempt_count: int
    status_changed_at: datetime
    searchable_at: datetime | None
    failure_reason: str | None

    def as_response(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "photo_id": str(self.photo_id),
            "pipeline_revision_id": str(self.pipeline_revision_id),
            "pipeline_code": self.pipeline_code,
            "processing_status": self.processing_status,
            "searchable": self.searchable,
            "attempt_count": self.attempt_count,
            "status_changed_at": _utc_z(self.status_changed_at),
            "searchable_at": _utc_z(self.searchable_at),
            "failure_reason": self.failure_reason,
        }


def read_photo_processing_status(
    database_session: Session,
    *,
    session_token: str | None,
    photo_id: uuid.UUID,
) -> PhotoProcessingStatus:
    """Authorize and assemble one safe current status without processing writes."""

    principal = get_current_principal(database_session, session_token=session_token)
    photo = database_session.get(Photo, photo_id)
    if photo is None:
        raise PhotoProcessingStatusNotFoundError
    if (
        principal.role is StaffRole.PHOTOGRAPHER
        and photo.uploader_id != principal.staff_user_id
    ):
        raise PhotoProcessingStatusAccessDeniedError
    if principal.role not in {
        StaffRole.PHOTOGRAPHER,
        StaffRole.OPERATOR,
        StaffRole.DEVELOPER,
    }:
        raise PhotoProcessingStatusAccessDeniedError

    projection = read_photo_processing_projection(
        database_session,
        photo_id=photo.id,
        pipeline_revision_id=photo.admission_pipeline_revision_id,
    )
    if projection is None:
        raise PhotoProcessingStateUnavailableError
    return PhotoProcessingStatus(
        photo_id=projection.photo_id,
        pipeline_revision_id=projection.pipeline_revision_id,
        pipeline_code=projection.pipeline_code,
        processing_status=projection.processing_status,
        searchable=projection.searchable,
        attempt_count=projection.attempt_count,
        status_changed_at=projection.status_changed_at,
        searchable_at=projection.searchable_at,
        failure_reason=projection.failure_reason,
    )


def _utc_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

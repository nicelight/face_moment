"""Inventory-owned Photo selection and visibility transitions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import (
    authenticate_unsafe_staff_request,
    get_current_principal,
)
from face_moment.serving_control.ingest_target import Spa


class PhotoInventoryAccessDeniedError(PermissionError):
    """The active principal cannot access the requested inventory Photo."""


class PhotoInventoryNotFoundError(LookupError):
    """The requested inventory Photo or accessible SPA does not exist."""


class InvalidPhotoInventorySelectionError(ValueError):
    """The required selection interval is invalid."""


@dataclass(frozen=True, slots=True)
class PhotoInventorySelection:
    spa_id: uuid.UUID
    visit_date: date
    captured_from: datetime
    captured_before: datetime
    photos: tuple[Photo, ...]

    def as_response(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "spa_id": str(self.spa_id),
            "visit_date": self.visit_date.isoformat(),
            "captured_from": _isoformat(self.captured_from),
            "captured_before": _isoformat(self.captured_before),
            "photos": [
                {
                    "photo_id": str(photo.id),
                    "captured_at": _isoformat(photo.captured_at),
                    "accepted_at": _isoformat(photo.accepted_at),
                    "active": photo.is_active,
                }
                for photo in self.photos
            ],
        }


@dataclass(frozen=True, slots=True)
class PhotoVisibility:
    photo_id: uuid.UUID
    active: bool

    def as_response(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "photo_id": str(self.photo_id),
            "active": self.active,
        }


def read_photo_inventory(
    database_session: Session,
    *,
    session_token: str | None,
    spa_id: uuid.UUID,
    visit_date: date,
    captured_from: datetime,
    captured_before: datetime,
) -> PhotoInventorySelection:
    """Return the persisted role-scoped inventory projection."""

    normalized_from, normalized_before = _normalize_interval(
        captured_from,
        captured_before,
    )
    principal = get_current_principal(database_session, session_token=session_token)
    _require_accessible_spa(database_session, spa_id)

    statement = select(Photo).where(
        Photo.spa_id == spa_id,
        Photo.visit_date == visit_date,
        Photo.captured_at >= normalized_from,
        Photo.captured_at < normalized_before,
    )
    if principal.role is StaffRole.PHOTOGRAPHER:
        statement = statement.where(Photo.uploader_id == principal.staff_user_id)
    elif principal.role not in {StaffRole.OPERATOR, StaffRole.DEVELOPER}:
        raise PhotoInventoryAccessDeniedError

    return PhotoInventorySelection(
        spa_id=spa_id,
        visit_date=visit_date,
        captured_from=normalized_from,
        captured_before=normalized_before,
        photos=tuple(
            database_session.scalars(statement.order_by(Photo.captured_at, Photo.id))
        ),
    )


def set_photo_visibility(
    database_session: Session,
    *,
    session_token: str | None,
    csrf_cookie_token: str | None,
    csrf_header_token: str | None,
    photo_id: uuid.UUID,
    active: bool,
) -> PhotoVisibility:
    """Authorize and persist the only allowed visibility-field transition."""

    principal = authenticate_unsafe_staff_request(
        database_session,
        session_token=session_token,
        csrf_cookie_token=csrf_cookie_token,
        csrf_header_token=csrf_header_token,
    )
    photo = database_session.scalar(
        select(Photo).where(Photo.id == photo_id).with_for_update()
    )
    if photo is None:
        raise PhotoInventoryNotFoundError
    _require_accessible_spa(database_session, photo.spa_id)
    if principal.role is StaffRole.PHOTOGRAPHER:
        if photo.uploader_id != principal.staff_user_id:
            raise PhotoInventoryAccessDeniedError
    elif principal.role not in {StaffRole.OPERATOR, StaffRole.DEVELOPER}:
        raise PhotoInventoryAccessDeniedError

    if photo.is_active != active:
        photo.is_active = active
        database_session.commit()
    return PhotoVisibility(photo_id=photo.id, active=photo.is_active)


def _require_accessible_spa(database_session: Session, spa_id: uuid.UUID) -> None:
    spa = database_session.get(Spa, spa_id)
    if spa is None:
        raise PhotoInventoryNotFoundError
    if not spa.active:
        raise PhotoInventoryAccessDeniedError


def _normalize_interval(
    captured_from: datetime, captured_before: datetime
) -> tuple[datetime, datetime]:
    if captured_from.tzinfo is None or captured_before.tzinfo is None:
        raise InvalidPhotoInventorySelectionError
    normalized_from = captured_from.astimezone(UTC)
    normalized_before = captured_before.astimezone(UTC)
    if normalized_from >= normalized_before:
        raise InvalidPhotoInventorySelectionError
    return normalized_from, normalized_before


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

"""Inventory-authorized venue media selection and private JPEG delivery."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.inventory.photo_inventory import (
    PhotoInventoryAccessDeniedError, PhotoInventoryNotFoundError, InvalidPhotoInventorySelectionError,
)
from face_moment.inventory.photo_persistence import Photo
from face_moment.platform.auth.principals import StaffPrincipal, StaffRole
from face_moment.platform.auth.sessions import get_current_principal
from face_moment.platform.staff_datetime import STAFF_TIMEZONE
from face_moment.processing.staff_media_projection import read_staff_media_projections
from face_moment.serving_control.ingest_target import Spa


def _authorize_venue(session: Session, session_token: str | None,
                     spa_id: UUID) -> tuple[StaffPrincipal, Spa]:
    principal = get_current_principal(session, session_token=session_token)
    if principal.role not in {StaffRole.PHOTOGRAPHER, StaffRole.OPERATOR, StaffRole.DEVELOPER}:
        raise PhotoInventoryAccessDeniedError
    spa = session.get(Spa, spa_id)
    if spa is None:
        raise PhotoInventoryNotFoundError
    if not spa.active:
        raise PhotoInventoryAccessDeniedError
    return principal, spa


def read_staff_media_venue_name(session: Session, *, session_token: str | None,
                               spa_id: UUID) -> str:
    return _authorize_venue(session, session_token, spa_id)[1].name


def read_staff_venue_media(session: Session, *, session_token: str | None,
                          spa_id: UUID, date_from: date, date_to: date) -> dict[str, object]:
    principal, venue = _authorize_venue(session, session_token, spa_id)
    if date_from > date_to:
        raise InvalidPhotoInventorySelectionError('reversed dates')
    start = datetime.combine(date_from, time.min, STAFF_TIMEZONE)
    try:
        end = datetime.combine(date_to + timedelta(days=1), time.min, STAFF_TIMEZONE)
    except OverflowError as error:
        raise InvalidPhotoInventorySelectionError from error
    statement = select(Photo).where(Photo.spa_id == spa_id, Photo.is_active.is_(True),
                                   Photo.accepted_at >= start, Photo.accepted_at < end)
    if principal.role is StaffRole.PHOTOGRAPHER:
        statement = statement.where(Photo.uploader_id == principal.staff_user_id)
    photos = session.scalars(statement.order_by(Photo.accepted_at.desc(), Photo.id)).all()
    states = read_staff_media_projections(session, photo_revisions=[
        (photo.id, photo.admission_pipeline_revision_id) for photo in photos],
        preferred_revision_id=venue.serving_pipeline_revision_id)
    rows = []
    for photo in photos:
        state = states.get(photo.id)
        if state is not None and state.status == 'no_faces':
            continue
        media_path = f'/api/inventory/venue-media/{photo.id}'
        rows.append({
            'photo_id': str(photo.id),
            'accepted_at': photo.accepted_at.astimezone(UTC).isoformat().replace('+00:00', 'Z'),
            'captured_at': photo.captured_at.astimezone(UTC).isoformat().replace('+00:00', 'Z'),
            'width': photo.width, 'height': photo.height,
            'original_byte_size': photo.original_byte_size,
            'processing_status': state.status if state else None,
            'thumbnail_url': f'{media_path}/thumbnail' if state and state.thumbnail_object_key else None,
            'original_url': f'{media_path}/original',
        })
    return {'schema_version': 1, 'spa_id': str(spa_id), 'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat(), 'photos': rows}


def read_staff_photo_bytes(session: Session, *, session_token: str | None,
                           photo_id: UUID, thumbnail: bool,
                           object_store: PrivateObjectStore) -> bytes:
    # Authenticate before resolving the Photo, including direct URL requests.
    principal = get_current_principal(session, session_token=session_token)
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise PhotoInventoryNotFoundError
    _, venue = _authorize_venue(session, session_token, photo.spa_id)
    if principal.role is StaffRole.PHOTOGRAPHER and photo.uploader_id != principal.staff_user_id:
        raise PhotoInventoryAccessDeniedError
    key = photo.original_object_key
    if thumbnail:
        projection = read_staff_media_projections(session, photo_revisions=[
            (photo.id, photo.admission_pipeline_revision_id)],
            preferred_revision_id=venue.serving_pipeline_revision_id).get(photo.id)
        if projection is None or projection.thumbnail_object_key is None:
            raise PhotoInventoryNotFoundError
        key = projection.thumbnail_object_key
    try:
        return object_store.read(key=key)
    except ClientError as error:
        if error.response.get('Error', {}).get('Code') in {'NoSuchKey', 'NotFound', '404'}:
            raise PhotoInventoryNotFoundError from error
        raise

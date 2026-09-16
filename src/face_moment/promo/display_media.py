"""Promo-owned authenticated projection of issued teaser preview bytes."""

from __future__ import annotations

import uuid

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.processing import read_photo_processing_projection
from face_moment.promo.attempt import PromoAttempt
from face_moment.promo.session import PromoSession


class PromoMediaNotFoundError(LookupError):
    """The requested issued preview is unknown or unavailable."""


def resolve_teaser_media(
    database_session: Session,
    *,
    spa_id: uuid.UUID,
    session_id: uuid.UUID,
    photo_id: uuid.UUID,
    object_store: PrivateObjectStore,
) -> bytes:
    """Read one retained preview referenced by an issued Promo session."""

    session_row = database_session.scalar(
        select(PromoSession).where(
            PromoSession.id == session_id,
            PromoSession.spa_id == spa_id,
        )
    )
    if session_row is None or photo_id not in session_row.teaser_photo_ids:
        raise PromoMediaNotFoundError(str(photo_id))

    revision_id = database_session.scalar(
        select(PromoAttempt.pipeline_revision_id).where(
            PromoAttempt.id == session_row.attempt_id
        )
    )
    if revision_id is None:
        raise PromoMediaNotFoundError(str(photo_id))

    projection = read_photo_processing_projection(
        database_session,
        photo_id=photo_id,
        spa_id=spa_id,
        pipeline_revision_id=revision_id,
    )
    if projection is None:
        raise PromoMediaNotFoundError(str(photo_id))
    preview_key = projection.preview_object_key
    if not isinstance(preview_key, str) or not preview_key:
        raise PromoMediaNotFoundError(str(photo_id))

    try:
        body = object_store.read(key=preview_key)
    except ClientError as error:
        error_code = error.response.get("Error", {}).get("Code")
        if error_code == "NoSuchKey":
            raise PromoMediaNotFoundError(str(photo_id)) from error
        raise
    if not body:
        raise PromoMediaNotFoundError(str(photo_id))
    return body


__all__ = ["PromoMediaNotFoundError", "resolve_teaser_media"]

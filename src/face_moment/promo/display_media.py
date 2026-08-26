"""Promo-owned authenticated projection of issued teaser preview bytes."""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Iterable
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.processing import read_photo_processing_projection
from face_moment.promo.session import PromoSession


class PromoMediaNotFoundError(LookupError):
    """The reference is unknown or its issued preview is unavailable."""


def derive_media_ref(
    session_id: uuid.UUID,
    photo_id: uuid.UUID,
    *,
    qr_ticket_secret: bytes | str,
) -> str:
    """Derive an opaque same-origin reference without exposing IDs."""

    secret = _secret_bytes(qr_ticket_secret)
    message = b"face-moment:promo-media:v1:" + session_id.bytes + photo_id.bytes
    digest = hmac.new(secret, message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def resolve_teaser_media(
    database_session: Session,
    *,
    spa_id: uuid.UUID,
    media_ref: str,
    qr_ticket_secret: bytes | str,
    object_store: PrivateObjectStore,
) -> bytes:
    """Read one issued, active, ready preview through the promo boundary."""

    if not _valid_media_ref(media_ref):
        raise PromoMediaNotFoundError(media_ref)

    matched_photo_id: uuid.UUID | None = None
    sessions: Iterable[PromoSession] = database_session.scalars(
        select(PromoSession).where(PromoSession.spa_id == spa_id)
    )
    for session_row in sessions:
        for photo_id in session_row.teaser_photo_ids:
            expected = derive_media_ref(
                session_row.id,
                photo_id,
                qr_ticket_secret=qr_ticket_secret,
            )
            if hmac.compare_digest(expected, media_ref):
                matched_photo_id = photo_id
                break
        if matched_photo_id is not None:
            break

    if matched_photo_id is None:
        raise PromoMediaNotFoundError(media_ref)

    projection = read_photo_processing_projection(
        database_session,
        photo_id=matched_photo_id,
        spa_id=spa_id,
    )
    if projection is None or not projection.searchable:
        raise PromoMediaNotFoundError(media_ref)
    preview_key = projection.preview_object_key
    if not isinstance(preview_key, str) or not preview_key:
        raise PromoMediaNotFoundError(media_ref)

    try:
        body = object_store.read(key=preview_key)
    except Exception as error:
        raise PromoMediaNotFoundError(media_ref) from error
    if not body:
        raise PromoMediaNotFoundError(media_ref)
    return body


def _valid_media_ref(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 43
        and all(character.isalnum() or character in "-_" for character in value)
    )


def _secret_bytes(value: bytes | str) -> bytes:
    if isinstance(value, str):
        value = value.encode("utf-8")
    if not isinstance(value, bytes) or not value:
        raise ValueError("promo media secret must be non-empty")
    return value


__all__ = ["PromoMediaNotFoundError", "derive_media_ref", "resolve_teaser_media"]

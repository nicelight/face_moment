"""Inventory-owned active Photo scope for public processing reads."""
from __future__ import annotations

from collections.abc import Sequence
import uuid
from dataclasses import dataclass
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.sql import Subquery

from face_moment.inventory.photo_persistence import Photo


def public_active_photo_scope(venue_ids: Sequence[uuid.UUID]) -> Subquery:
    """Publish IDs and dates only; originals remain within inventory ownership."""
    return select(
        Photo.id.label("photo_id"), Photo.spa_id, Photo.visit_date,
    ).where(Photo.is_active.is_(True), Photo.spa_id.in_(venue_ids)).subquery(
        "public_active_photos"
    )


@dataclass(frozen=True, slots=True)
class PublicPhotoReference:
    photo_id: uuid.UUID
    spa_id: uuid.UUID
    visit_date: date


def read_public_active_photos(session: Session, photo_ids: Sequence[uuid.UUID]) -> tuple[PublicPhotoReference, ...]:
    return tuple(PublicPhotoReference(row.id, row.spa_id, row.visit_date) for row in session.execute(
        select(Photo.id, Photo.spa_id, Photo.visit_date).where(Photo.id.in_(photo_ids), Photo.is_active.is_(True))))


def read_public_active_original(session: Session, *, photo_id: uuid.UUID,
                                venue_ids: Sequence[uuid.UUID]) -> str | None:
    """Private reference for an already membership-authorized active Photo."""
    return session.scalar(select(Photo.original_object_key).where(
        Photo.id == photo_id, Photo.is_active.is_(True), Photo.spa_id.in_(venue_ids)))

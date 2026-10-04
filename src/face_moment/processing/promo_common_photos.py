"""Bounded all-date commons projection for an already successful Promo result."""
from __future__ import annotations

from collections.abc import Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.inventory.public_photo_projection import public_active_photo_scope
from face_moment.processing.initial_pending import PhotoPipelineState


def read_promo_common_photos(
    session: Session, *, spa_id: uuid.UUID, pipeline_revision_id: uuid.UUID,
    limit: int, excluded_photo_ids: Sequence[uuid.UUID] = (),
) -> tuple[uuid.UUID, ...]:
    """Read active same-venue no_faces in stable ID order, without date filtering."""
    if not 0 <= limit <= 8:
        raise ValueError("Promo commons capacity must be between zero and eight")
    if limit == 0:
        return ()
    photos = public_active_photo_scope((spa_id,))
    statement = (
        select(photos.c.photo_id)
        .join(PhotoPipelineState, PhotoPipelineState.photo_id == photos.c.photo_id)
        .where(
            PhotoPipelineState.pipeline_revision_id == pipeline_revision_id,
            PhotoPipelineState.status == "no_faces",
            photos.c.photo_id.not_in(excluded_photo_ids),
        )
        .order_by(photos.c.photo_id)
        .limit(limit)
    )
    return tuple(session.scalars(statement))

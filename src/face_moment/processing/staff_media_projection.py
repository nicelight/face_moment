"""Processing-owned admission-lineage reads for the staff media table."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from face_moment.processing.initial_pending import PhotoPipelineState


@dataclass(frozen=True, slots=True)
class StaffMediaProcessingProjection:
    status: str
    thumbnail_object_key: str | None
    pipeline_revision_id: UUID | None = None


def read_staff_media_projections(
    session: Session, *, photo_revisions: Sequence[tuple[UUID, UUID]],
    preferred_revision_id: UUID | None = None,
) -> dict[UUID, StaffMediaProcessingProjection]:
    """Prefer the venue's serving state when present, otherwise admission state."""
    if not photo_revisions:
        return {}
    pairs = set(photo_revisions)
    if preferred_revision_id is not None:
        pairs.update((photo_id, preferred_revision_id) for photo_id, _ in photo_revisions)
    rows = session.execute(
        select(PhotoPipelineState.photo_id, PhotoPipelineState.status,
               PhotoPipelineState.thumbnail_object_key, PhotoPipelineState.pipeline_revision_id).where(
            tuple_(PhotoPipelineState.photo_id, PhotoPipelineState.pipeline_revision_id)
            .in_(pairs)
        )
    )
    result: dict[UUID, StaffMediaProcessingProjection] = {}
    for photo_id, status, thumbnail_key, revision_id in rows:
        if photo_id not in result or revision_id == preferred_revision_id:
            result[photo_id] = StaffMediaProcessingProjection(status, thumbnail_key, revision_id)
    return result

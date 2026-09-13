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


def read_staff_media_projections(
    session: Session, *, photo_revisions: Sequence[tuple[UUID, UUID]]
) -> dict[UUID, StaffMediaProcessingProjection]:
    """Read only supplied Photo/revision pairs; never substitute newer states."""
    if not photo_revisions:
        return {}
    rows = session.execute(
        select(PhotoPipelineState.photo_id, PhotoPipelineState.status,
               PhotoPipelineState.thumbnail_object_key).where(
            tuple_(PhotoPipelineState.photo_id, PhotoPipelineState.pipeline_revision_id)
            .in_(photo_revisions)
        )
    )
    return {photo_id: StaffMediaProcessingProjection(status, thumbnail_key)
            for photo_id, status, thumbnail_key in rows}

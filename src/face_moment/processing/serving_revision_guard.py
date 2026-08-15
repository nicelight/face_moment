from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.initial_pending import PhotoPipelineState

_NON_TERMINAL_STATES = ("pending", "processing")


@dataclass(frozen=True, slots=True)
class ServingRevisionGuardProjection:
    """Read-only processing result for one exact serving revision."""

    spa_id: uuid.UUID
    pipeline_revision_id: uuid.UUID
    blocks_revision_change: bool


class ServingRevisionGuardRepository:
    """Processing-owned exact-A backlog projection."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(
        self,
        *,
        spa_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> ServingRevisionGuardProjection:
        """Report non-terminal work admitted under exactly this revision."""

        blocking_photo_id = self._session.scalar(
            select(PhotoPipelineState.photo_id)
            .join(Photo, Photo.id == PhotoPipelineState.photo_id)
            .where(
                Photo.spa_id == spa_id,
                Photo.admission_pipeline_revision_id == pipeline_revision_id,
                PhotoPipelineState.pipeline_revision_id == pipeline_revision_id,
                PhotoPipelineState.status.in_(_NON_TERMINAL_STATES),
            )
            .limit(1)
        )
        return ServingRevisionGuardProjection(
            spa_id=spa_id,
            pipeline_revision_id=pipeline_revision_id,
            blocks_revision_change=blocking_photo_id is not None,
        )


def read_serving_revision_guard(
    session: Session,
    *,
    spa_id: uuid.UUID,
    pipeline_revision_id: uuid.UUID,
) -> ServingRevisionGuardProjection:
    """Expose the processing-owned read-only serving-control boundary."""

    return ServingRevisionGuardRepository(session).resolve(
        spa_id=spa_id,
        pipeline_revision_id=pipeline_revision_id,
    )

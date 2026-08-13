from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace

_READY = "ready"
_TERMINAL_NON_SEARCHABLE = frozenset({"no_faces", "failed"})
_SLO_WINDOW = timedelta(minutes=15)
_SLO_TARGET = 0.95


@dataclass(frozen=True, slots=True)
class IngestToSearchableProjection:
    """One controlled-interval, full-population ingest SLO result."""

    population: int
    success_under_15_minutes: int
    breach: int
    open: int
    success_ratio: float | None
    meets_95_percent: bool | None


class IngestToSearchableProjectionRepository:
    """Read each accepted Photo's admission-state SLO without mutation."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(
        self,
        *,
        spa_id: uuid.UUID,
        accepted_from: datetime,
        accepted_before: datetime,
        evaluated_at: datetime,
    ) -> IngestToSearchableProjection:
        """Classify the half-open accepted population at the controlled clock."""

        has_valid_face = exists(
            select(1).where(
                PhotoFace.photo_id == PhotoPipelineState.photo_id,
                PhotoFace.pipeline_revision_id
                == PhotoPipelineState.pipeline_revision_id,
            )
        )
        rows = self._session.execute(
            select(
                Photo.accepted_at,
                PhotoPipelineState.status,
                PhotoPipelineState.searchable_at,
                PhotoPipelineState.preview_object_key,
                PhotoPipelineState.thumbnail_object_key,
                has_valid_face,
            )
            .join(Photo, Photo.id == PhotoPipelineState.photo_id)
            .where(
                Photo.spa_id == spa_id,
                Photo.accepted_at >= accepted_from,
                Photo.accepted_at < accepted_before,
            )
        )

        success = 0
        breach = 0
        open_count = 0
        for (
            accepted_at,
            status,
            searchable_at,
            preview_object_key,
            thumbnail_object_key,
            has_face,
        ) in rows:
            is_complete_ready = (
                status == _READY
                and searchable_at is not None
                and preview_object_key is not None
                and thumbnail_object_key is not None
                and has_face
            )
            if is_complete_ready and searchable_at - accepted_at < _SLO_WINDOW:
                success += 1
            elif status == _READY or status in _TERMINAL_NON_SEARCHABLE:
                breach += 1
            elif evaluated_at - accepted_at >= _SLO_WINDOW:
                breach += 1
            else:
                open_count += 1

        population = success + breach + open_count
        success_ratio = success / population if population else None
        meets_95_percent = (
            success_ratio >= _SLO_TARGET
            if success_ratio is not None and open_count == 0
            else None
        )
        return IngestToSearchableProjection(
            population=population,
            success_under_15_minutes=success,
            breach=breach,
            open=open_count,
            success_ratio=success_ratio,
            meets_95_percent=meets_95_percent,
        )

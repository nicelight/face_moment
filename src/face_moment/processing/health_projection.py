from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import ProcessingRuntimeStatus
from face_moment.serving_control.ingest_target import Spa

_PENDING = "pending"
_PROCESSING = "processing"
_READY = "ready"
_NO_FACES = "no_faces"
_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class QueueRecoveryHealthProjection:
    """Current processing-owned queue and singleton recovery facts."""

    pending: int
    processing: int
    ready: int
    no_faces: int
    failed: int
    oldest_pending_accepted_at: datetime | None
    current_operation: str
    operation_started_at: datetime | None
    worker_started_at: datetime | None
    last_recovery_at: datetime | None
    last_recovered_count: int


class ProcessingHealthProjectionRepository:
    """Read direct current health facts for one SPA's serving revision."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(self, *, spa_id: uuid.UUID) -> QueueRecoveryHealthProjection:
        """Return current queue facts without changing processing state."""

        counts = self._session.execute(
            select(
                func.count().filter(PhotoPipelineState.status == _PENDING),
                func.count().filter(PhotoPipelineState.status == _PROCESSING),
                func.count().filter(PhotoPipelineState.status == _READY),
                func.count().filter(PhotoPipelineState.status == _NO_FACES),
                func.count().filter(PhotoPipelineState.status == _FAILED),
                func.min(Photo.accepted_at).filter(
                    PhotoPipelineState.status == _PENDING
                ),
            )
            .join(Photo, Photo.id == PhotoPipelineState.photo_id)
            .join(Spa, Spa.id == Photo.spa_id)
            .where(
                Spa.id == spa_id,
                PhotoPipelineState.pipeline_revision_id
                == Spa.serving_pipeline_revision_id,
            )
        ).one()
        runtime = self._session.get(ProcessingRuntimeStatus, 1)
        if runtime is None:
            raise RuntimeError("processing runtime status is missing")

        (
            pending,
            processing,
            ready,
            no_faces,
            failed,
            oldest_pending_accepted_at,
        ) = counts
        return QueueRecoveryHealthProjection(
            pending=pending,
            processing=processing,
            ready=ready,
            no_faces=no_faces,
            failed=failed,
            oldest_pending_accepted_at=oldest_pending_accepted_at,
            current_operation=runtime.current_operation,
            operation_started_at=runtime.operation_started_at,
            worker_started_at=runtime.worker_started_at,
            last_recovery_at=runtime.last_recovery_at,
            last_recovered_count=runtime.last_recovered_count,
        )

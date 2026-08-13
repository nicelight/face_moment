from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import ProcessingRuntimeStatus
from face_moment.serving_control.ingest_target import Spa

_PENDING = "pending"
_PROCESSING = "processing"
_FAILED = "failed"
_IDLE = "idle"
_PHOTO_PROCESSING = "photo_processing"
_MAX_ATTEMPTS = 3
_SAFE_FAILURE_MESSAGE = "processing failed"


class WorkerClaimRepository:
    """Processing-owned atomic claim and bounded failure boundary."""

    def __init__(
        self, session: Session, *, bound_pipeline_revision_id: uuid.UUID
    ) -> None:
        self._session = session
        self._bound_pipeline_revision_id = bound_pipeline_revision_id

    def claim_oldest_pending(self) -> PhotoPipelineState | None:
        """Claim only work for this process's still-committed revision."""

        state = self._session.scalar(
            select(PhotoPipelineState)
            .join(Photo, Photo.id == PhotoPipelineState.photo_id)
            .join(Spa, Spa.id == Photo.spa_id)
            .where(
                PhotoPipelineState.status == _PENDING,
                PhotoPipelineState.pipeline_revision_id
                == self._bound_pipeline_revision_id,
                Spa.serving_pipeline_revision_id == self._bound_pipeline_revision_id,
                Photo.is_active.is_(True),
                Spa.active.is_(True),
            )
            .order_by(PhotoPipelineState.status_changed_at, PhotoPipelineState.photo_id)
            .limit(1)
            .with_for_update(of=PhotoPipelineState)
        )
        if state is None:
            return None

        runtime = self._runtime_status()
        now = datetime.now(timezone.utc)
        state.status = _PROCESSING
        state.attempt_count += 1
        state.status_changed_at = now
        runtime.current_operation = _PHOTO_PROCESSING
        runtime.operation_started_at = now
        self._session.flush()
        self._session.refresh(state)
        return state

    def record_failure(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> PhotoPipelineState:
        """Return a failed claim to pending or terminally fail its third claim."""

        state = self._session.scalar(
            select(PhotoPipelineState)
            .where(
                PhotoPipelineState.photo_id == photo_id,
                PhotoPipelineState.pipeline_revision_id == pipeline_revision_id,
                PhotoPipelineState.status == _PROCESSING,
            )
            .with_for_update()
        )
        if state is None:
            raise LookupError("processing claim is not active")

        runtime = self._runtime_status()
        state.status = _FAILED if state.attempt_count >= _MAX_ATTEMPTS else _PENDING
        state.status_changed_at = datetime.now(timezone.utc)
        state.last_error = _SAFE_FAILURE_MESSAGE
        runtime.current_operation = _IDLE
        runtime.operation_started_at = None
        self._session.flush()
        self._session.refresh(state)
        return state

    def _runtime_status(self) -> ProcessingRuntimeStatus:
        runtime = self._session.get(ProcessingRuntimeStatus, 1)
        if runtime is None:
            raise RuntimeError("processing runtime status is missing")
        return runtime

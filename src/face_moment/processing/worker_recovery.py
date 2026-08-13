from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import ProcessingRuntimeStatus

_PENDING = "pending"
_PROCESSING = "processing"
_IDLE = "idle"


class WorkerStartupRecoveryRepository:
    """Processing-owned startup recovery inside the caller's transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def recover(self) -> int:
        """Reset unfinished processing state and publish one recovery projection."""

        runtime = self._session.scalar(
            select(ProcessingRuntimeStatus)
            .where(ProcessingRuntimeStatus.singleton_id == 1)
            .with_for_update()
        )
        if runtime is None:
            raise RuntimeError("processing runtime status is missing")

        processing_states = list(
            self._session.scalars(
                select(PhotoPipelineState)
                .where(PhotoPipelineState.status == _PROCESSING)
                .with_for_update()
            )
        )
        now = datetime.now(timezone.utc)
        for state in processing_states:
            state.status = _PENDING
            state.status_changed_at = now

        runtime.worker_started_at = now
        runtime.last_recovery_at = now
        runtime.last_recovered_count = len(processing_states)
        runtime.current_operation = _IDLE
        runtime.operation_started_at = None
        self._session.flush()
        return len(processing_states)

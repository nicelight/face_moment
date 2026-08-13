from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from face_moment.processing.photo_orchestration import PhotoProcessingOrchestrator
from face_moment.processing.worker_claims import WorkerClaimRepository
from face_moment.processing.worker_recovery import WorkerStartupRecoveryRepository


class BackgroundPhotoWorker:
    """One sequential process loop over the processing-owned durable state."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        orchestrator: PhotoProcessingOrchestrator,
        bound_pipeline_revision_id: uuid.UUID,
    ) -> None:
        self._session_factory = session_factory
        self._orchestrator = orchestrator
        self._bound_pipeline_revision_id = bound_pipeline_revision_id

    def recover_startup(self) -> int:
        with self._session_factory() as session:
            recovered_count = WorkerStartupRecoveryRepository(session).recover()
            session.commit()
            return recovered_count

    def process_one(self) -> bool:
        with self._session_factory() as session:
            claim = WorkerClaimRepository(
                session,
                bound_pipeline_revision_id=self._bound_pipeline_revision_id,
            ).claim_oldest_pending()
            if claim is None:
                session.rollback()
                return False
            photo_id = claim.photo_id
            pipeline_revision_id = claim.pipeline_revision_id
            session.commit()

        self._orchestrator.process_claimed(
            photo_id=photo_id,
            pipeline_revision_id=pipeline_revision_id,
        )
        return True

    async def run_until_stopped(
        self,
        *,
        stop_event: asyncio.Event,
        idle_seconds: float,
    ) -> None:
        while not stop_event.is_set():
            processed = await asyncio.to_thread(self.process_one)
            if processed:
                continue
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=idle_seconds)
            except TimeoutError:
                continue

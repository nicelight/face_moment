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
        claim_requested_calibration: Callable[[], uuid.UUID | None] | None = None,
        execute_claimed_calibration: Callable[[uuid.UUID], object] | None = None,
        interrupt_running_calibrations: Callable[[], object] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._orchestrator = orchestrator
        self._bound_pipeline_revision_id = bound_pipeline_revision_id
        self._claim_requested_calibration = claim_requested_calibration
        self._execute_claimed_calibration = execute_claimed_calibration
        self._interrupt_running_calibrations = interrupt_running_calibrations

    def recover_startup(self) -> int:
        if self._interrupt_running_calibrations is not None:
            self._interrupt_running_calibrations()
        with self._session_factory() as session:
            recovered_count = WorkerStartupRecoveryRepository(session).recover()
            session.commit()
            return recovered_count

    def process_one(self) -> bool:
        execute_claimed_calibration = self._execute_claimed_calibration
        if (
            self._claim_requested_calibration is not None
            and execute_claimed_calibration is not None
        ):
            calibration_run_id = self._claim_requested_calibration()
            if calibration_run_id is not None:
                self.run_calibration(
                    lambda: execute_claimed_calibration(calibration_run_id)
                )
                return True

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

    def run_calibration(self, hold: Callable[[], object]) -> None:
        """Run one controlled Calibration hold on this same singleton worker."""

        with self._session_factory() as session:
            WorkerClaimRepository(
                session,
                bound_pipeline_revision_id=self._bound_pipeline_revision_id,
            ).begin_calibration()
            session.commit()

        try:
            hold()
        finally:
            with self._session_factory() as session:
                WorkerClaimRepository(
                    session,
                    bound_pipeline_revision_id=self._bound_pipeline_revision_id,
                ).finish_calibration()
                session.commit()

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

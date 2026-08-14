from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing.ingest_slo import IngestToSearchableProjectionRepository
from face_moment.processing.initial_pending import InitialPendingRepository, PhotoPipelineState
from face_moment.processing.persistence import ProcessingRuntimeStatus
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.processing.terminal_publication import TerminalPublicationRepository
from face_moment.processing.worker_runtime import BackgroundPhotoWorker
from face_moment.serving_control import IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY
from tests.processing.test_photo_orchestration import disposable_processing_state


class _NoFaceOrchestrator:
    """Controlled terminal outcome used only to prove worker release."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def process_claimed(
        self, *, photo_id: uuid.UUID, pipeline_revision_id: uuid.UUID
    ) -> None:
        with Session(self._engine) as session:
            TerminalPublicationRepository(session).publish_no_faces(
                photo_id=photo_id,
                pipeline_revision_id=pipeline_revision_id,
            )
            session.commit()


def _worker(engine: Engine, pipeline_revision_id: uuid.UUID) -> BackgroundPhotoWorker:
    return BackgroundPhotoWorker(
        session_factory=lambda: Session(engine),
        orchestrator=_NoFaceOrchestrator(engine),  # type: ignore[arg-type]
        bound_pipeline_revision_id=pipeline_revision_id,
    )


def test_controlled_calibration_hold_keeps_photo_backlog_in_slo_then_releases(
    disposable_processing_state: tuple[Engine, object, str, list[str]],
) -> None:
    engine, _, run_prefix, _ = disposable_processing_state
    accepted_at = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
    marker = uuid.uuid4().hex

    with Session(engine) as session:
        revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=accepted_at,
            **PIPELINE_COMPATIBILITY,
        )
        target = IngestTargetRepository(session).configure_spa(
            name=f"task-029-{marker}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=revision.id,
        )
        photo = Photo(
            spa_id=target.spa_id,
            visit_date=date(2026, 8, 14),
            captured_at=accepted_at,
            captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
            accepted_at=accepted_at,
            admission_pipeline_revision_id=revision.id,
            uploader_id=uuid.uuid4(),
            checksum_sha256=hashlib.sha256(marker.encode()).digest(),
            original_object_key=f"{run_prefix}{marker}/original.jpg",
            original_byte_size=123,
            width=20,
            height=12,
            is_active=True,
        )
        session.add(photo)
        session.flush()
        InitialPendingRepository(session).create_initial_pending(
            photo_id=photo.id,
            pipeline_revision_id=revision.id,
        )
        photo_id = photo.id
        pipeline_revision_id = revision.id
        spa_id = target.spa_id
        session.commit()

    worker = _worker(engine, pipeline_revision_id)

    def observe_held_worker() -> None:
        with Session(engine) as session:
            runtime = session.get(ProcessingRuntimeStatus, 1)
            state = session.get(PhotoPipelineState, (photo_id, pipeline_revision_id))
            projection = IngestToSearchableProjectionRepository(session).resolve(
                spa_id=spa_id,
                accepted_from=accepted_at,
                accepted_before=accepted_at + timedelta(hours=1),
                evaluated_at=accepted_at + timedelta(minutes=5),
            )

        assert runtime is not None
        assert (runtime.current_operation, runtime.operation_started_at is not None) == (
            "calibration",
            True,
        )
        assert state is not None
        assert (state.status, state.attempt_count) == ("pending", 0)
        assert (
            projection.population,
            projection.success_under_15_minutes,
            projection.breach,
            projection.open,
        ) == (1, 0, 0, 1)
        assert worker.process_one() is False

        with Session(engine) as session:
            held_state = session.get(PhotoPipelineState, (photo_id, pipeline_revision_id))
        assert held_state is not None
        assert (held_state.status, held_state.attempt_count) == ("pending", 0)

    worker.run_calibration(observe_held_worker)

    with Session(engine) as session:
        released_runtime = session.get(ProcessingRuntimeStatus, 1)
    assert released_runtime is not None
    assert (released_runtime.current_operation, released_runtime.operation_started_at) == (
        "idle",
        None,
    )

    assert worker.process_one() is True

    with Session(engine) as session:
        terminal_state = session.get(PhotoPipelineState, (photo_id, pipeline_revision_id))
        terminal_projection = IngestToSearchableProjectionRepository(session).resolve(
            spa_id=spa_id,
            accepted_from=accepted_at,
            accepted_before=accepted_at + timedelta(hours=1),
            evaluated_at=accepted_at + timedelta(minutes=16),
        )

    assert terminal_state is not None
    assert (terminal_state.status, terminal_state.attempt_count) == ("no_faces", 1)
    assert (
        terminal_projection.population,
        terminal_projection.success_under_15_minutes,
        terminal_projection.breach,
        terminal_projection.open,
    ) == (1, 0, 1, 0)

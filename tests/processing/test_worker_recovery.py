from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import uuid

from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing import (
    InitialPendingRepository,
    PipelineCode,
    PipelineRevisionRepository,
)
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import ProcessingRuntimeStatus
from face_moment.processing.worker_recovery import WorkerStartupRecoveryRepository
from face_moment.serving_control import IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


_CANONICAL_RUNTIME = (None, None, 0, "idle", None)


def _add_photo(
    session: Session,
    *,
    marker: str,
    spa_id: uuid.UUID,
) -> Photo:
    photo = Photo(
        spa_id=spa_id,
        visit_date=date(2026, 8, 13),
        captured_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        uploader_id=uuid.uuid4(),
        checksum_sha256=hashlib.sha256(marker.encode()).digest(),
        original_object_key=f"private/task-025-{marker}",
        original_byte_size=123,
        width=12,
        height=10,
    )
    session.add(photo)
    session.flush()
    return photo


def test_worker_startup_recovery_resets_only_processing_state() -> None:
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    marker = uuid.uuid4().hex
    photo_ids: list[uuid.UUID] = []
    state_photo_ids: dict[str, uuid.UUID] = {}
    revision_id: uuid.UUID | None = None
    spa_id: uuid.UUID | None = None

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        before_recovery = datetime.now(timezone.utc) - timedelta(minutes=5)

        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=before_recovery,
                **PIPELINE_COMPATIBILITY,
            )
            revision_id = revision.id
            target = IngestTargetRepository(session).configure_spa(
                name=f"task-025-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            spa_id = target.spa_id

            states: dict[str, PhotoPipelineState] = {}
            for status in ("processing", "pending", "ready", "no_faces", "failed"):
                photo = _add_photo(
                    session,
                    marker=f"{status}-{marker}",
                    spa_id=target.spa_id,
                )
                photo_ids.append(photo.id)
                state_photo_ids[status] = photo.id
                state = InitialPendingRepository(session).create_initial_pending(
                    photo_id=photo.id,
                    pipeline_revision_id=revision.id,
                )
                state.status = status
                state.attempt_count = 2 if status == "processing" else 1
                state.status_changed_at = before_recovery
                states[status] = state

            runtime = session.get(ProcessingRuntimeStatus, 1)
            assert runtime is not None
            runtime.worker_started_at = before_recovery
            runtime.last_recovery_at = before_recovery
            runtime.last_recovered_count = 7
            runtime.current_operation = "photo_processing"
            runtime.operation_started_at = before_recovery
            session.commit()

        with Session(engine) as session:
            recovered_count = WorkerStartupRecoveryRepository(session).recover()
            assert recovered_count == 1
            session.commit()

        with Session(engine) as session:
            processing_state = session.get(
                PhotoPipelineState, (state_photo_ids["processing"], revision_id)
            )
            pending_state = session.get(
                PhotoPipelineState, (state_photo_ids["pending"], revision_id)
            )
            ready_state = session.get(
                PhotoPipelineState, (state_photo_ids["ready"], revision_id)
            )
            no_faces_state = session.get(
                PhotoPipelineState, (state_photo_ids["no_faces"], revision_id)
            )
            failed_state = session.get(
                PhotoPipelineState, (state_photo_ids["failed"], revision_id)
            )
            assert processing_state is not None
            assert pending_state is not None
            assert ready_state is not None
            assert no_faces_state is not None
            assert failed_state is not None
            assert processing_state.status == "pending"
            assert processing_state.attempt_count == 2
            assert processing_state.status_changed_at > before_recovery
            assert pending_state.status == "pending"
            assert pending_state.attempt_count == 1
            assert pending_state.status_changed_at == before_recovery
            assert ready_state.status == "ready"
            assert ready_state.status_changed_at == before_recovery
            assert no_faces_state.status == "no_faces"
            assert no_faces_state.status_changed_at == before_recovery
            assert failed_state.status == "failed"
            assert failed_state.status_changed_at == before_recovery

            runtime = session.get(ProcessingRuntimeStatus, 1)
            assert runtime is not None
            assert runtime.worker_started_at is not None
            assert runtime.worker_started_at > before_recovery
            assert runtime.last_recovery_at == runtime.worker_started_at
            assert runtime.last_recovered_count == 1
            assert runtime.current_operation == "idle"
            assert runtime.operation_started_at is None

        with Session(engine) as session:
            repeated_count = WorkerStartupRecoveryRepository(session).recover()
            assert repeated_count == 0
            session.commit()

        with Session(engine) as session:
            runtime = session.get(ProcessingRuntimeStatus, 1)
            assert runtime is not None
            assert runtime.last_recovered_count == 0
            assert runtime.last_recovery_at is not None
            assert runtime.worker_started_at == runtime.last_recovery_at
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE face_moment.processing_runtime_status "
                "SET worker_started_at = %s, last_recovery_at = %s, "
                "last_recovered_count = %s, current_operation = %s, "
                "operation_started_at = %s WHERE singleton_id = 1",
                _CANONICAL_RUNTIME,
            )
            for photo_id in photo_ids:
                connection.exec_driver_sql(
                    "DELETE FROM face_moment.photo_pipeline_states WHERE photo_id = %s",
                    (photo_id,),
                )
                connection.exec_driver_sql(
                    "DELETE FROM face_moment.photos WHERE id = %s",
                    (photo_id,),
                )
            if spa_id is not None:
                connection.exec_driver_sql(
                    "DELETE FROM face_moment.spas WHERE id = %s", (spa_id,)
                )
            if revision_id is not None:
                connection.exec_driver_sql(
                    "DELETE FROM face_moment.pipeline_revisions WHERE id = %s",
                    (revision_id,),
                )
        engine.dispose()

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import uuid

from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, select
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
from face_moment.processing.worker_claims import WorkerClaimRepository
from face_moment.serving_control import IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


def _add_photo(
    session: Session,
    *,
    marker: str,
    spa_id: uuid.UUID,
    is_active: bool = True,
) -> Photo:
    photo = Photo(
        spa_id=spa_id,
        visit_date=date(2026, 8, 12),
        captured_at=datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc),
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        uploader_id=uuid.uuid4(),
        checksum_sha256=hashlib.sha256(marker.encode()).digest(),
        original_object_key=f"private/task-022-{marker}",
        original_byte_size=123,
        width=12,
        height=10,
        is_active=is_active,
    )
    session.add(photo)
    session.flush()
    return photo


def _state(
    session: Session,
    *,
    photo: Photo,
    pipeline_revision_id: uuid.UUID,
    status_changed_at: datetime,
) -> PhotoPipelineState:
    state = InitialPendingRepository(session).create_initial_pending(
        photo_id=photo.id,
        pipeline_revision_id=pipeline_revision_id,
    )
    state.status_changed_at = status_changed_at
    session.flush()
    return state


def test_worker_claims_oldest_eligible_row_and_bounds_failures() -> None:
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    marker = uuid.uuid4().hex
    revision_ids: list[uuid.UUID] = []
    photo_ids: list[uuid.UUID] = []
    spa_id: uuid.UUID | None = None
    non_serving_id: uuid.UUID | None = None
    oldest_id: uuid.UUID | None = None
    later_id: uuid.UUID | None = None

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        base_time = datetime.now(timezone.utc) + timedelta(days=1)

        with Session(engine) as session:
            serving_revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=base_time,
                **PIPELINE_COMPATIBILITY,
            )
            other_revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
                validated_at=base_time,
                **PIPELINE_COMPATIBILITY,
            )
            revision_ids.extend((serving_revision.id, other_revision.id))
            target = IngestTargetRepository(session).configure_spa(
                name=f"task-022-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=serving_revision.id,
            )
            spa_id = target.spa_id

            non_serving = _add_photo(
                session, marker=f"non-serving-{marker}", spa_id=target.spa_id
            )
            oldest = _add_photo(
                session, marker=f"oldest-{marker}", spa_id=target.spa_id
            )
            later = _add_photo(
                session, marker=f"later-{marker}", spa_id=target.spa_id
            )
            photo_ids.extend((non_serving.id, oldest.id, later.id))
            non_serving_id = non_serving.id
            oldest_id = oldest.id
            later_id = later.id
            _state(
                session,
                photo=non_serving,
                pipeline_revision_id=other_revision.id,
                status_changed_at=base_time,
            )
            _state(
                session,
                photo=oldest,
                pipeline_revision_id=serving_revision.id,
                status_changed_at=base_time + timedelta(seconds=1),
            )
            _state(
                session,
                photo=later,
                pipeline_revision_id=serving_revision.id,
                status_changed_at=base_time + timedelta(seconds=2),
            )
            session.commit()

        assert non_serving_id is not None
        assert oldest_id is not None
        assert later_id is not None

        with Session(engine) as session:
            claim = WorkerClaimRepository(
                session, bound_pipeline_revision_id=serving_revision.id
            ).claim_oldest_pending()
            assert claim is not None
            assert claim.photo_id == oldest_id
            assert claim.pipeline_revision_id == serving_revision.id
            assert claim.status == "processing"
            assert claim.attempt_count == 1
            runtime = session.get(ProcessingRuntimeStatus, 1)
            assert runtime is not None
            assert runtime.current_operation == "photo_processing"
            assert runtime.operation_started_at is not None
            session.rollback()

        with Session(engine) as session:
            rolled_back = session.get(
                PhotoPipelineState, (oldest_id, serving_revision.id)
            )
            runtime = session.get(ProcessingRuntimeStatus, 1)
            assert rolled_back is not None
            assert rolled_back.status == "pending"
            assert rolled_back.attempt_count == 0
            assert runtime is not None
            assert runtime.current_operation == "idle"
            assert runtime.operation_started_at is None

        for attempt in range(1, 4):
            with Session(engine) as session:
                claims = WorkerClaimRepository(
                    session, bound_pipeline_revision_id=serving_revision.id
                )
                claim = claims.claim_oldest_pending()
                assert claim is not None
                assert claim.photo_id == oldest_id
                assert claim.attempt_count == attempt
                session.commit()

            with Session(engine) as session:
                state = WorkerClaimRepository(
                    session, bound_pipeline_revision_id=serving_revision.id
                ).record_failure(
                    photo_id=oldest_id,
                    pipeline_revision_id=serving_revision.id,
                )
                assert state.attempt_count == attempt
                assert state.last_error == "processing failed"
                assert len(state.last_error) <= 512
                assert state.status == ("failed" if attempt == 3 else "pending")
                runtime = session.get(ProcessingRuntimeStatus, 1)
                assert runtime is not None
                assert runtime.current_operation == "idle"
                assert runtime.operation_started_at is None
                session.commit()

        with Session(engine) as session:
            non_serving_state = session.get(
                PhotoPipelineState, (non_serving_id, other_revision.id)
            )
            later_state = session.get(
                PhotoPipelineState, (later_id, serving_revision.id)
            )
            assert non_serving_state is not None
            assert non_serving_state.status == "pending"
            assert non_serving_state.attempt_count == 0
            assert later_state is not None
            assert later_state.status == "pending"
            assert later_state.attempt_count == 0
    finally:
        with engine.begin() as connection:
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
            for revision_id in revision_ids:
                connection.exec_driver_sql(
                    "DELETE FROM face_moment.pipeline_revisions WHERE id = %s",
                    (revision_id,),
                )
        engine.dispose()

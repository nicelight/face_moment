from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import uuid

from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing import (
    InitialPendingRepository,
    PipelineCode,
    PipelineRevisionRepository,
)
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.serving_control import IngestTargetRepository


def _migration_round_trip(engine: object) -> None:
    alembic_config = Config("alembic.ini")
    alembic_command.upgrade(alembic_config, "head")
    alembic_command.downgrade(alembic_config, "0006_photo_identity_persistence")
    assert "photo_pipeline_states" not in inspect(engine).get_table_names(
        schema=APP_SCHEMA
    )
    alembic_command.upgrade(alembic_config, "head")
    assert "photo_pipeline_states" in inspect(engine).get_table_names(
        schema=APP_SCHEMA
    )


def _add_photo(
    session: Session,
    *,
    marker: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    revision = PipelineRevisionRepository(session).publish_eligible(
        pipeline_code=PipelineCode.OPENCV_SFACE,
        validated_at=datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc),
    )
    target = IngestTargetRepository(session).configure_spa(
        name=f"task009-spa-{marker}",
        timezone="Asia/Dushanbe",
        serving_pipeline_revision_id=revision.id,
    )
    photo = Photo(
        spa_id=target.spa_id,
        visit_date=date(2026, 8, 11),
        captured_at=datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc),
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        uploader_id=uuid.uuid4(),
        checksum_sha256=hashlib.sha256(marker.encode()).digest(),
        original_object_key=f"private/task-009-{marker}",
        original_byte_size=123,
        width=12,
        height=10,
    )
    session.add(photo)
    session.flush()
    return photo.id, revision.id, target.spa_id


def test_processing_creates_initial_pending_inside_the_caller_transaction() -> None:
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    committed: tuple[uuid.UUID, uuid.UUID, uuid.UUID] | None = None
    marker = uuid.uuid4().hex

    try:
        _migration_round_trip(engine)

        table = PhotoPipelineState.__table__
        assert set(table.columns.keys()) == {
            "photo_id",
            "pipeline_revision_id",
            "status",
            "attempt_count",
            "status_changed_at",
        }

        with Session(engine) as session:
            rolled_back_photo_id, rolled_back_revision_id, _ = _add_photo(
                session, marker=f"rollback-{marker}"
            )
            rolled_back_state = InitialPendingRepository(session).create_initial_pending(
                photo_id=rolled_back_photo_id,
                pipeline_revision_id=rolled_back_revision_id,
            )
            assert rolled_back_state.status == "pending"
            assert rolled_back_state.attempt_count == 0
            assert rolled_back_state.status_changed_at is not None
            session.rollback()

        with Session(engine) as session:
            assert (
                session.scalar(
                    select(PhotoPipelineState).where(
                        PhotoPipelineState.photo_id == rolled_back_photo_id,
                        PhotoPipelineState.pipeline_revision_id == rolled_back_revision_id,
                    )
                )
                is None
            )

        with Session(engine) as session:
            committed = _add_photo(session, marker=f"commit-{marker}")
            committed_photo_id, committed_revision_id, _ = committed
            committed_state = InitialPendingRepository(session).create_initial_pending(
                photo_id=committed_photo_id,
                pipeline_revision_id=committed_revision_id,
            )
            assert committed_state.status == "pending"
            assert committed_state.attempt_count == 0
            assert committed_state.status_changed_at is not None
            session.commit()

        assert committed is not None
        committed_photo_id, committed_revision_id, _ = committed
        with Session(engine) as session:
            persisted = session.scalar(
                select(PhotoPipelineState).where(
                    PhotoPipelineState.photo_id == committed_photo_id,
                    PhotoPipelineState.pipeline_revision_id == committed_revision_id,
                )
            )
            assert persisted is not None
            assert persisted.status == "pending"
            assert persisted.attempt_count == 0
            assert persisted.status_changed_at is not None

        schema = inspect(engine)
        primary_key = schema.get_pk_constraint(
            "photo_pipeline_states", schema=APP_SCHEMA
        )
        assert primary_key["constrained_columns"] == ["photo_id", "pipeline_revision_id"]
        foreign_keys = schema.get_foreign_keys(
            "photo_pipeline_states", schema=APP_SCHEMA
        )
        assert all(
            foreign_key["options"].get("ondelete") == "RESTRICT"
            for foreign_key in foreign_keys
        )
    finally:
        if committed is not None:
            committed_photo_id, committed_revision_id, committed_spa_id = committed
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "DELETE FROM face_moment.photo_pipeline_states "
                    "WHERE photo_id = %s AND pipeline_revision_id = %s",
                    (committed_photo_id, committed_revision_id),
                )
                connection.exec_driver_sql(
                    "DELETE FROM face_moment.photos WHERE id = %s",
                    (committed_photo_id,),
                )
                connection.exec_driver_sql(
                    "DELETE FROM face_moment.spas WHERE id = %s",
                    (committed_spa_id,),
                )
                connection.exec_driver_sql(
                    "DELETE FROM face_moment.pipeline_revisions WHERE id = %s",
                    (committed_revision_id,),
                )
        _migration_round_trip(engine)
        engine.dispose()

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing.health_projection import ProcessingHealthProjectionRepository
from face_moment.processing.initial_pending import (
    InitialPendingRepository,
    PhotoPipelineState,
)
from face_moment.processing.persistence import ProcessingRuntimeStatus
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control.ingest_target import IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY

_CANONICAL_RUNTIME = (None, None, 0, "idle", None)


@dataclass(frozen=True, slots=True)
class _Fixture:
    database_name: str
    spa_id: uuid.UUID
    spa_ids: tuple[uuid.UUID, ...]
    photo_ids: tuple[uuid.UUID, ...]
    revision_ids: tuple[uuid.UUID, ...]
    expected_oldest_pending: datetime
    expected_runtime: tuple[object, ...]


def _runtime_snapshot(engine: Engine) -> tuple[object, ...]:
    with Session(engine) as session:
        runtime = session.get(ProcessingRuntimeStatus, 1)
        assert runtime is not None
        return (
            runtime.worker_started_at,
            runtime.last_recovery_at,
            runtime.last_recovered_count,
            runtime.current_operation,
            runtime.operation_started_at,
        )


def _add_state(
    session: Session,
    *,
    marker: str,
    spa_id: uuid.UUID,
    pipeline_revision_id: uuid.UUID,
    status: str,
    accepted_at: datetime,
    is_active: bool = True,
) -> uuid.UUID:
    photo = Photo(
        spa_id=spa_id,
        visit_date=date(2026, 8, 13),
        captured_at=accepted_at,
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        accepted_at=accepted_at,
        uploader_id=uuid.uuid4(),
        checksum_sha256=hashlib.sha256(marker.encode()).digest(),
        original_object_key=f"private/task-032-{marker}",
        original_byte_size=123,
        width=12,
        height=10,
        is_active=is_active,
    )
    session.add(photo)
    session.flush()
    state = InitialPendingRepository(session).create_initial_pending(
        photo_id=photo.id,
        pipeline_revision_id=pipeline_revision_id,
    )
    state.status = status
    state.status_changed_at = accepted_at
    return photo.id


def _fixture(engine: Engine, database_name: str) -> _Fixture:
    marker = uuid.uuid4().hex
    accepted_from = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)
    worker_started_at = accepted_from + timedelta(hours=1)
    last_recovery_at = worker_started_at + timedelta(minutes=2)
    operation_started_at = last_recovery_at + timedelta(minutes=3)

    with Session(engine) as session:
        current_revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=accepted_from,
            **PIPELINE_COMPATIBILITY,
        )
        other_revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
            validated_at=accepted_from,
            **PIPELINE_COMPATIBILITY,
        )
        target = IngestTargetRepository(session).configure_spa(
            name=f"task-032-{marker}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=current_revision.id,
        )
        other_target = IngestTargetRepository(session).configure_spa(
            name=f"task-032-other-{marker}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=current_revision.id,
        )
        photo_ids = tuple(
            _add_state(
                session,
                marker=f"{status}-{index}-{marker}",
                spa_id=target.spa_id,
                pipeline_revision_id=current_revision.id,
                status=status,
                accepted_at=accepted_from + timedelta(minutes=index * 5),
                is_active=status != "failed",
            )
            for index, status in enumerate(
                ("pending", "pending", "processing", "ready", "no_faces", "failed")
            )
        )
        excluded_other_revision = _add_state(
            session,
            marker=f"other-revision-{marker}",
            spa_id=target.spa_id,
            pipeline_revision_id=other_revision.id,
            status="failed",
            accepted_at=accepted_from,
        )
        excluded_other_spa = _add_state(
            session,
            marker=f"other-spa-{marker}",
            spa_id=other_target.spa_id,
            pipeline_revision_id=current_revision.id,
            status="pending",
            accepted_at=accepted_from - timedelta(hours=1),
        )
        runtime = session.get(ProcessingRuntimeStatus, 1)
        assert runtime is not None
        runtime.worker_started_at = worker_started_at
        runtime.last_recovery_at = last_recovery_at
        runtime.last_recovered_count = 4
        runtime.current_operation = "calibration"
        runtime.operation_started_at = operation_started_at
        session.commit()

    return _Fixture(
        database_name=database_name,
        spa_id=target.spa_id,
        spa_ids=(target.spa_id, other_target.spa_id),
        photo_ids=photo_ids + (excluded_other_revision, excluded_other_spa),
        revision_ids=(current_revision.id, other_revision.id),
        expected_oldest_pending=accepted_from,
        expected_runtime=(
            worker_started_at,
            last_recovery_at,
            4,
            "calibration",
            operation_started_at,
        ),
    )


def _cleanup(engine: Engine, fixture: _Fixture) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE face_moment.processing_runtime_status "
            "SET worker_started_at = %s, last_recovery_at = %s, "
            "last_recovered_count = %s, current_operation = %s, "
            "operation_started_at = %s WHERE singleton_id = 1",
            _CANONICAL_RUNTIME,
        )
        for photo_id in fixture.photo_ids:
            connection.exec_driver_sql(
                "DELETE FROM face_moment.photo_pipeline_states WHERE photo_id = %s",
                (photo_id,),
            )
            connection.exec_driver_sql(
                "DELETE FROM face_moment.photos WHERE id = %s", (photo_id,)
            )
        for spa_id in fixture.spa_ids:
            connection.exec_driver_sql(
                "DELETE FROM face_moment.spas WHERE id = %s", (spa_id,)
            )
        for revision_id in fixture.revision_ids:
            connection.exec_driver_sql(
                "DELETE FROM face_moment.pipeline_revisions WHERE id = %s",
                (revision_id,),
            )


def test_queue_and_recovery_health_projection_is_exact_read_only_and_repeatable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_settings = Settings.from_env()
    database_name = f"task032_{uuid.uuid4().hex}"
    probe_url = make_url(base_settings.database_url).set(database=database_name)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {database_name}"))
    monkeypatch.setenv("DATABASE_URL", probe_url.render_as_string(hide_password=False))
    engine = create_engine(probe_url, pool_pre_ping=True)
    fixture: _Fixture | None = None

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        assert _runtime_snapshot(engine) == _CANONICAL_RUNTIME
        fixture = _fixture(engine, database_name)

        with Session(engine) as session:
            direct_rows = tuple(
                session.execute(
                    select(PhotoPipelineState.status, Photo.accepted_at)
                    .join(Photo, Photo.id == PhotoPipelineState.photo_id)
                    .where(
                        Photo.spa_id == fixture.spa_id,
                        PhotoPipelineState.pipeline_revision_id
                        == fixture.revision_ids[0],
                    )
                )
            )
        direct_counts = Counter(status for status, _accepted_at in direct_rows)
        direct_oldest_pending = min(
            accepted_at
            for status, accepted_at in direct_rows
            if status == "pending"
        )

        statements: list[str] = []

        def capture_sql(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", capture_sql)
        try:
            with Session(engine) as session:
                repository = ProcessingHealthProjectionRepository(session)
                first = repository.resolve(spa_id=fixture.spa_id)
                second = repository.resolve(spa_id=fixture.spa_id)
        finally:
            event.remove(engine, "before_cursor_execute", capture_sql)

        assert first == second
        assert (
            first.pending,
            first.processing,
            first.ready,
            first.no_faces,
            first.failed,
            first.oldest_pending_accepted_at,
        ) == (
            direct_counts["pending"],
            direct_counts["processing"],
            direct_counts["ready"],
            direct_counts["no_faces"],
            direct_counts["failed"],
            direct_oldest_pending,
        )
        assert first.oldest_pending_accepted_at == fixture.expected_oldest_pending
        assert (
            first.worker_started_at,
            first.last_recovery_at,
            first.last_recovered_count,
            first.current_operation,
            first.operation_started_at,
        ) == fixture.expected_runtime
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
        assert _runtime_snapshot(engine) == fixture.expected_runtime
    finally:
        if fixture is not None:
            _cleanup(engine, fixture)
            assert _runtime_snapshot(engine) == _CANONICAL_RUNTIME
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)"))
        admin_engine.dispose()

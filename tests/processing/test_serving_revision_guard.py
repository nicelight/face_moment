from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
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
from face_moment.processing import (
    InitialPendingRepository,
    PipelineCode,
    PipelineRevisionRepository,
    read_serving_revision_guard,
)
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.revisions import PipelineRevision
from face_moment.serving_control.ingest_target import (
    IngestTargetRepository,
    Spa,
)
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY

_FIXTURE_TIME = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)
_MATRIX = (
    ("pending", True),
    ("processing", True),
    ("ready", False),
    ("no_faces", False),
    ("failed", False),
)


@dataclass(frozen=True, slots=True)
class _Fixture:
    database_name: str
    spa_id: uuid.UUID
    admission_revision_id: uuid.UUID
    target_revision_id: uuid.UUID
    matrix_photo_ids: tuple[uuid.UUID, ...]
    all_photo_ids: tuple[uuid.UUID, ...]


def _add_photo(
    session: Session,
    *,
    marker: str,
    spa_id: uuid.UUID,
    admission_revision_id: uuid.UUID,
    state_revision_id: uuid.UUID,
    status: str,
) -> uuid.UUID:
    photo = Photo(
        spa_id=spa_id,
        visit_date=date(2026, 8, 14),
        captured_at=_FIXTURE_TIME,
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        accepted_at=_FIXTURE_TIME,
        admission_pipeline_revision_id=admission_revision_id,
        uploader_id=uuid.uuid4(),
        checksum_sha256=hashlib.sha256(marker.encode()).digest(),
        original_object_key=f"private/task-039/{marker}/original.jpg",
        original_byte_size=123,
        width=12,
        height=10,
        is_active=True,
    )
    session.add(photo)
    session.flush()
    state = InitialPendingRepository(session).create_initial_pending(
        photo_id=photo.id,
        pipeline_revision_id=state_revision_id,
    )
    state.status = status
    state.status_changed_at = _FIXTURE_TIME
    session.flush()
    return photo.id


def _fixture(engine: Engine, database_name: str) -> _Fixture:
    marker = uuid.uuid4().hex
    with Session(engine) as session:
        admission_revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=_FIXTURE_TIME,
            **PIPELINE_COMPATIBILITY,
        )
        target_revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
            validated_at=_FIXTURE_TIME,
            **PIPELINE_COMPATIBILITY,
        )
        target = IngestTargetRepository(session).configure_spa(
            name=f"task-039-{marker}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=admission_revision.id,
        )

        matrix_photo_ids = tuple(
            _add_photo(
                session,
                marker=f"matrix-{status}-{marker}",
                spa_id=target.spa_id,
                admission_revision_id=admission_revision.id,
                state_revision_id=admission_revision.id,
                status="ready",
            )
            for status, _expected_block in _MATRIX
        )
        # A later B row exists for each A-admitted Photo. It must never replace
        # the exact (photo_id, A) state selected by this guard.
        for photo_id in matrix_photo_ids:
            session.add(
                PhotoPipelineState(
                    photo_id=photo_id,
                    pipeline_revision_id=target_revision.id,
                    status="processing",
                    status_changed_at=_FIXTURE_TIME,
                )
            )
        b_admitted_photo_id = _add_photo(
            session,
            marker=f"b-admitted-{marker}",
            spa_id=target.spa_id,
            admission_revision_id=target_revision.id,
            state_revision_id=target_revision.id,
            status="processing",
        )
        session.commit()

    return _Fixture(
        database_name=database_name,
        spa_id=target.spa_id,
        admission_revision_id=admission_revision.id,
        target_revision_id=target_revision.id,
        matrix_photo_ids=matrix_photo_ids,
        all_photo_ids=matrix_photo_ids + (b_admitted_photo_id,),
    )


def _snapshot(session: Session, fixture: _Fixture) -> tuple[object, ...]:
    photo_rows = tuple(
        session.execute(
            select(
                Photo.id,
                Photo.spa_id,
                Photo.admission_pipeline_revision_id,
                Photo.is_active,
            )
            .where(Photo.id.in_(fixture.all_photo_ids))
            .order_by(Photo.id)
        )
    )
    state_rows = tuple(
        session.execute(
            select(
                PhotoPipelineState.photo_id,
                PhotoPipelineState.pipeline_revision_id,
                PhotoPipelineState.status,
                PhotoPipelineState.attempt_count,
                PhotoPipelineState.status_changed_at,
                PhotoPipelineState.searchable_at,
                PhotoPipelineState.last_error,
                PhotoPipelineState.preview_object_key,
                PhotoPipelineState.thumbnail_object_key,
            )
            .where(PhotoPipelineState.photo_id.in_(fixture.all_photo_ids))
            .order_by(
                PhotoPipelineState.photo_id,
                PhotoPipelineState.pipeline_revision_id,
            )
        )
    )
    spa_row = tuple(
        session.execute(
            select(Spa.id, Spa.active, Spa.serving_pipeline_revision_id).where(
                Spa.id == fixture.spa_id
            )
        )
    )
    revision_rows = tuple(
        session.execute(
            select(PipelineRevision.id, PipelineRevision.validated_at)
            .where(
                PipelineRevision.id.in_(
                    (fixture.admission_revision_id, fixture.target_revision_id)
                )
            )
            .order_by(PipelineRevision.id)
        )
    )
    return photo_rows, state_rows, spa_row, revision_rows


def test_exact_a_guard_is_read_only_and_ignores_non_admission_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_settings = Settings.from_env()
    database_name = f"task039_{uuid.uuid4().hex}"
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
        fixture = _fixture(engine, database_name)
        observed: dict[str, bool] = {}

        for index, (status, expected_block) in enumerate(_MATRIX):
            photo_id = fixture.matrix_photo_ids[index]
            with Session(engine) as session:
                state = session.get(
                    PhotoPipelineState,
                    (photo_id, fixture.admission_revision_id),
                )
                assert state is not None
                state.status = status
                session.commit()

            with Session(engine) as session:
                before = _snapshot(session, fixture)

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
                    result = read_serving_revision_guard(
                        session,
                        spa_id=fixture.spa_id,
                        pipeline_revision_id=fixture.admission_revision_id,
                    )
            finally:
                event.remove(engine, "before_cursor_execute", capture_sql)

            with Session(engine) as session:
                after = _snapshot(session, fixture)

            assert statements
            assert all(
                statement.lstrip().upper().startswith("SELECT")
                for statement in statements
            )
            assert result.spa_id == fixture.spa_id
            assert result.pipeline_revision_id == fixture.admission_revision_id
            assert result.blocks_revision_change is expected_block
            assert before == after
            observed[status] = result.blocks_revision_change

            # Reset only the disposable fixture so the next matrix case is
            # isolated; the guard itself has no write path.
            with Session(engine) as session:
                for matrix_photo_id in fixture.matrix_photo_ids:
                    matrix_state = session.get(
                        PhotoPipelineState,
                        (matrix_photo_id, fixture.admission_revision_id),
                    )
                    assert matrix_state is not None
                    matrix_state.status = "ready"
                session.commit()

        assert observed == dict(_MATRIX)
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(
                text(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)")
            )
        admin_engine.dispose()

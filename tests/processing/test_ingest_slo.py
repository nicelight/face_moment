from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing.ingest_slo import IngestToSearchableProjectionRepository
from face_moment.processing.initial_pending import InitialPendingRepository
from face_moment.processing.persistence import PhotoFace
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control.ingest_target import IngestTargetRepository, Spa
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY

_ACCEPTED_FROM = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
_ACCEPTED_BEFORE = _ACCEPTED_FROM + timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class _Fixture:
    spa_id: uuid.UUID


def _add_photo(
    session: Session,
    *,
    marker: str,
    spa_id: uuid.UUID,
    pipeline_revision_id: uuid.UUID,
    accepted_at: datetime,
    status: str,
    searchable_at: datetime | None = None,
    complete: bool = False,
) -> uuid.UUID:
    photo = Photo(
        spa_id=spa_id,
        visit_date=date(2026, 8, 14),
        captured_at=accepted_at,
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        accepted_at=accepted_at,
        admission_pipeline_revision_id=pipeline_revision_id,
        uploader_id=uuid.uuid4(),
        checksum_sha256=hashlib.sha256(marker.encode()).digest(),
        original_object_key=f"private/task-028/{marker}/original.jpg",
        original_byte_size=123,
        width=12,
        height=10,
        is_active=True,
    )
    session.add(photo)
    session.flush()
    state = InitialPendingRepository(session).create_initial_pending(
        photo_id=photo.id,
        pipeline_revision_id=pipeline_revision_id,
    )
    state.status = status
    state.status_changed_at = searchable_at or accepted_at
    state.searchable_at = searchable_at
    if complete:
        state.preview_object_key = f"private/task-028/{marker}/preview.jpg"
        state.thumbnail_object_key = f"private/task-028/{marker}/thumbnail.jpg"
        session.add(
            PhotoFace(
                photo_id=photo.id,
                pipeline_revision_id=pipeline_revision_id,
                face_index=0,
                bbox_x=1.0,
                bbox_y=1.0,
                bbox_w=4.0,
                bbox_h=4.0,
                landmarks_json=[[1.0, 1.0]] * 5,
                detection_confidence=0.9,
                embedding=[1.0] + [0.0] * 127,
            )
        )
    return photo.id


def _fixture(engine: Engine) -> _Fixture:
    marker = uuid.uuid4().hex
    with Session(engine) as session:
        serving_revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=_ACCEPTED_FROM,
            **PIPELINE_COMPATIBILITY,
        )
        target = IngestTargetRepository(session).configure_spa(
            name=f"task-028-{marker}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=serving_revision.id,
        )
        _add_photo(
            session,
            marker=f"lower-success-{marker}",
            spa_id=target.spa_id,
            pipeline_revision_id=serving_revision.id,
            accepted_at=_ACCEPTED_FROM,
            status="ready",
            searchable_at=_ACCEPTED_FROM + timedelta(minutes=14),
            complete=True,
        )
        _add_photo(
            session,
            marker=f"early-success-{marker}",
            spa_id=target.spa_id,
            pipeline_revision_id=serving_revision.id,
            accepted_at=_ACCEPTED_FROM + timedelta(minutes=1),
            status="ready",
            searchable_at=_ACCEPTED_FROM + timedelta(minutes=6),
            complete=True,
        )
        _add_photo(
            session,
            marker=f"late-ready-{marker}",
            spa_id=target.spa_id,
            pipeline_revision_id=serving_revision.id,
            accepted_at=_ACCEPTED_FROM + timedelta(minutes=2),
            status="ready",
            searchable_at=_ACCEPTED_FROM + timedelta(minutes=17),
            complete=True,
        )
        for offset, status in (
            (3, "no_faces"),
            (4, "failed"),
            (5, "pending"),
            (5, "processing"),
        ):
            _add_photo(
                session,
                marker=f"{status}-{marker}",
                spa_id=target.spa_id,
                pipeline_revision_id=serving_revision.id,
                accepted_at=_ACCEPTED_FROM + timedelta(minutes=offset),
                status=status,
            )
        for offset, status in ((15, "pending"), (16, "processing")):
            _add_photo(
                session,
                marker=f"young-{status}-{marker}",
                spa_id=target.spa_id,
                pipeline_revision_id=serving_revision.id,
                accepted_at=_ACCEPTED_FROM + timedelta(minutes=offset),
                status=status,
            )
        _add_photo(
            session,
            marker=f"upper-bound-{marker}",
            spa_id=target.spa_id,
            pipeline_revision_id=serving_revision.id,
            accepted_at=_ACCEPTED_BEFORE,
            status="ready",
            searchable_at=_ACCEPTED_BEFORE + timedelta(minutes=1),
            complete=True,
        )
        session.commit()
    return _Fixture(spa_id=target.spa_id)


def test_ingest_slo_reconciles_complete_population_and_nullable_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_settings = Settings.from_env()
    database_name = f"task028_{uuid.uuid4().hex}"
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

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        fixture = _fixture(engine)
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
                repository = IngestToSearchableProjectionRepository(session)
                open_population = repository.resolve(
                    spa_id=fixture.spa_id,
                    accepted_from=_ACCEPTED_FROM,
                    accepted_before=_ACCEPTED_BEFORE,
                    evaluated_at=_ACCEPTED_FROM + timedelta(minutes=20),
                )
                closed_population = repository.resolve(
                    spa_id=fixture.spa_id,
                    accepted_from=_ACCEPTED_FROM,
                    accepted_before=_ACCEPTED_BEFORE,
                    evaluated_at=_ACCEPTED_FROM + timedelta(hours=2),
                )
                passing_population = repository.resolve(
                    spa_id=fixture.spa_id,
                    accepted_from=_ACCEPTED_FROM,
                    accepted_before=_ACCEPTED_FROM + timedelta(seconds=30),
                    evaluated_at=_ACCEPTED_FROM + timedelta(minutes=20),
                )
                empty_population = repository.resolve(
                    spa_id=fixture.spa_id,
                    accepted_from=_ACCEPTED_BEFORE + timedelta(hours=1),
                    accepted_before=_ACCEPTED_BEFORE + timedelta(hours=2),
                    evaluated_at=_ACCEPTED_BEFORE + timedelta(hours=2),
                )
        finally:
            event.remove(engine, "before_cursor_execute", capture_sql)

        assert (
            open_population.population,
            open_population.success_under_15_minutes,
            open_population.breach,
            open_population.open,
            open_population.success_ratio,
            open_population.meets_95_percent,
        ) == (9, 2, 5, 2, 2 / 9, None)
        assert open_population.population == (
            open_population.success_under_15_minutes
            + open_population.breach
            + open_population.open
        )
        assert (
            closed_population.population,
            closed_population.success_under_15_minutes,
            closed_population.breach,
            closed_population.open,
            closed_population.success_ratio,
            closed_population.meets_95_percent,
        ) == (9, 2, 7, 0, 2 / 9, False)
        assert (
            passing_population.population,
            passing_population.success_under_15_minutes,
            passing_population.breach,
            passing_population.open,
            passing_population.success_ratio,
            passing_population.meets_95_percent,
        ) == (1, 1, 0, 0, 1.0, True)
        assert (
            empty_population.population,
            empty_population.success_under_15_minutes,
            empty_population.breach,
            empty_population.open,
            empty_population.success_ratio,
            empty_population.meets_95_percent,
        ) == (0, 0, 0, 0, None, None)
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)"))
        admin_engine.dispose()


def test_ingest_slo_keeps_admission_revision_after_serving_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_settings = Settings.from_env()
    database_name = f"task028_{uuid.uuid4().hex}"
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

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        marker = uuid.uuid4().hex
        with Session(engine) as session:
            admission_revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=_ACCEPTED_FROM,
                **PIPELINE_COMPATIBILITY,
            )
            later_serving_revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
                validated_at=_ACCEPTED_FROM,
                **PIPELINE_COMPATIBILITY,
            )
            target = IngestTargetRepository(session).configure_spa(
                name=f"task-028-switch-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=admission_revision.id,
            )
            photo_id = _add_photo(
                session,
                marker=f"admission-a-{marker}",
                spa_id=target.spa_id,
                pipeline_revision_id=admission_revision.id,
                accepted_at=_ACCEPTED_FROM,
                status="ready",
                searchable_at=_ACCEPTED_FROM + timedelta(minutes=10),
                complete=True,
            )
            session.commit()

        with Session(engine) as session:
            spa = session.get(Spa, target.spa_id)
            assert spa is not None
            spa.serving_pipeline_revision_id = later_serving_revision.id
            later_state = InitialPendingRepository(session).create_initial_pending(
                photo_id=photo_id,
                pipeline_revision_id=later_serving_revision.id,
            )
            later_state.status = "ready"
            later_state.status_changed_at = _ACCEPTED_FROM + timedelta(minutes=5)
            later_state.searchable_at = _ACCEPTED_FROM + timedelta(minutes=5)
            later_state.preview_object_key = (
                f"private/task-028/admission-b-{marker}/preview.jpg"
            )
            later_state.thumbnail_object_key = (
                f"private/task-028/admission-b-{marker}/thumbnail.jpg"
            )
            session.add(
                PhotoFace(
                    photo_id=photo_id,
                    pipeline_revision_id=later_serving_revision.id,
                    face_index=0,
                    bbox_x=1.0,
                    bbox_y=1.0,
                    bbox_w=4.0,
                    bbox_h=4.0,
                    landmarks_json=[[1.0, 1.0]] * 5,
                    detection_confidence=0.9,
                    embedding=[1.0] + [0.0] * 127,
                )
            )
            session.commit()

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
                projection = IngestToSearchableProjectionRepository(session).resolve(
                    spa_id=target.spa_id,
                    accepted_from=_ACCEPTED_FROM,
                    accepted_before=_ACCEPTED_BEFORE,
                    evaluated_at=_ACCEPTED_FROM + timedelta(minutes=20),
                )
        finally:
            event.remove(engine, "before_cursor_execute", capture_sql)

        assert (
            projection.population,
            projection.success_under_15_minutes,
            projection.breach,
            projection.open,
            projection.success_ratio,
            projection.meets_95_percent,
        ) == (1, 1, 0, 0, 1.0, True)
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)"))
        admin_engine.dispose()

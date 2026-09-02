"""FT-009-AC-002 structured server-event persistence and isolation proof."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
import os
import threading
import time
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.diagnostics.server_events import (
    EVENT_CATALOG,
    EVENT_QUEUE_CAPACITY,
    ServerEvent,
    ServerEventCode,
    ServerEventEmitter,
    ServerEventEnvelope,
    ServerEventRepository,
)
from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings
from face_moment.promo.realtime_orchestration import emit_attempt_admitted


_REVISION = "0018_structured_server_events"
_PREDECESSOR = "0017_retention_cleanup_latest"
_RELEASE = "task-090-synthetic"


@pytest.fixture(scope="module")
def disposable_event_engine() -> Iterator[Engine]:
    base_url = Settings.from_env().database_url
    probe_database = f"task090_{uuid.uuid4().hex}"
    probe_url = make_url(base_url).set(database=probe_database)
    admin_engine = create_engine(
        base_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {probe_database}")
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = probe_url.render_as_string(hide_password=False)
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    try:
        alembic_command.upgrade(Config("alembic.ini"), _PREDECESSOR)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO face_moment.staff_users "
                    "(id, username, password_hash, role) "
                    "VALUES (:id, 'task090-predecessor', 'synthetic-hash', 'developer')"
                ),
                {"id": uuid.uuid4()},
            )
        alembic_command.upgrade(Config("alembic.ini"), _REVISION)
        yield engine
    finally:
        engine.dispose()
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)"
            )
        admin_engine.dispose()


def test_next_linear_migration_shape_downgrade_and_data_preservation(
    disposable_event_engine: Engine,
) -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert scripts.get_revision(_REVISION).down_revision == _PREDECESSOR
    assert len(scripts.get_heads()) == 1

    inspector = inspect(disposable_event_engine)
    assert {
        column["name"]
        for column in inspector.get_columns("server_events", schema=APP_SCHEMA)
    } == {
        "event_id",
        "occurred_at",
        "severity",
        "component",
        "event_code",
        "release_id",
        "attempt_id",
        "correlation_id",
    }
    assert not inspector.get_foreign_keys("server_events", schema=APP_SCHEMA)
    assert {
        index["name"]
        for index in inspector.get_indexes("server_events", schema=APP_SCHEMA)
    } == {
        "ix_server_events_attempt_id",
        "ix_server_events_correlation_id",
        "ix_server_events_occurred_at",
        "ix_server_events_severity_component_code",
    }
    assert {
        constraint["name"]
        for constraint in inspector.get_check_constraints(
            "server_events", schema=APP_SCHEMA
        )
    } == {
        "ck_server_events_catalog_shape",
        "ck_server_events_component",
        "ck_server_events_correlation_shape",
        "ck_server_events_release_id_length",
        "ck_server_events_severity",
    }

    alembic_command.downgrade(Config("alembic.ini"), _PREDECESSOR)
    assert "server_events" not in inspect(disposable_event_engine).get_table_names(
        schema=APP_SCHEMA
    )
    with disposable_event_engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT count(*) FROM face_moment.staff_users "
                "WHERE username = 'task090-predecessor'"
            )
        ) == 1
    alembic_command.upgrade(Config("alembic.ini"), _REVISION)


def test_every_fixed_code_persists_exact_redacted_immutable_row_and_survives_restart(
    disposable_event_engine: Engine,
) -> None:
    attempt_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    emitter = ServerEventEmitter(
        lambda: Session(disposable_event_engine),
        release_id=_RELEASE,
        utc_now=lambda: datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc),
    )
    emitter.start()
    try:
        for code in EVENT_CATALOG:
            identities = (
                {}
                if code is ServerEventCode.RUNTIME_READINESS_CLOSED
                else {"attempt_id": attempt_id, "correlation_id": correlation_id}
            )
            assert emitter.emit(code, **identities)
        _wait_for_count(disposable_event_engine, len(EVENT_CATALOG))
    finally:
        emitter.stop()

    restarted_engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    try:
        with Session(restarted_engine) as session:
            rows = tuple(
                session.scalars(select(ServerEvent).order_by(ServerEvent.event_code))
            )
            assert {row.event_code for row in rows} == {
                code.value for code in EVENT_CATALOG
            }
            assert all(row.release_id == _RELEASE for row in rows)
            assert {column.name for column in ServerEvent.__table__.columns} == {
                "event_id",
                "occurred_at",
                "severity",
                "component",
                "event_code",
                "release_id",
                "attempt_id",
                "correlation_id",
            }
            projection = ServerEventRepository(session).get(rows[0].event_id)
            assert projection is not None
            with pytest.raises(FrozenInstanceError):
                projection.release_id = "mutated"  # type: ignore[misc]
    finally:
        restarted_engine.dispose()


def test_fixed_envelope_rejects_arbitrary_or_forbidden_context_before_enqueue(
    disposable_event_engine: Engine,
) -> None:
    forbidden = {
        "message",
        "payload",
        "traceback",
        "request_body",
        "authorization",
        "cookie",
        "token",
        "participant_name",
        "session_id",
        "image",
        "embedding",
        "object_key",
        "url",
    }
    assert {field.name for field in fields(ServerEventEnvelope)} == {
        "occurred_at",
        "event_code",
        "release_id",
        "attempt_id",
        "correlation_id",
    }
    assert forbidden.isdisjoint(column.name for column in ServerEvent.__table__.columns)

    emitter = ServerEventEmitter(
        lambda: Session(disposable_event_engine), release_id=_RELEASE
    )
    emitter.start()
    try:
        assert not emitter.emit("attempt.admitted")  # type: ignore[arg-type]
        assert not emitter.emit(ServerEventCode.ATTEMPT_ADMITTED)
        assert not emitter.emit(
            ServerEventCode.RUNTIME_READINESS_CLOSED,
            attempt_id=uuid.uuid4(),
            correlation_id=uuid.uuid4(),
        )
        assert not emitter.emit(
            ServerEventCode.QR_SESSION_EXPIRED,
            attempt_id=uuid.uuid4(),
        )
    finally:
        emitter.stop()


def test_held_sink_and_full_capacity_never_wait_or_mutate_owner_state(
    disposable_event_engine: Engine,
) -> None:
    entered = threading.Event()
    release = threading.Event()

    class HeldCommitSession(Session):
        def commit(self) -> None:
            entered.set()
            release.wait(timeout=5)
            super().commit()

    emitter = ServerEventEmitter(
        lambda: HeldCommitSession(bind=disposable_event_engine), release_id=_RELEASE
    )
    emitter.start()
    attempt = _Attempt("accepted")
    before = vars(attempt).copy()
    emit_attempt_admitted(
        emitter,
        attempt_id=attempt.id,
        correlation_id=attempt.client_attempt_id,
    )
    assert entered.wait(timeout=2)
    assert not release.is_set()
    assert vars(attempt) == before

    accepted = [
        emitter.emit(
            ServerEventCode.ATTEMPT_ADMITTED,
            attempt_id=attempt.id,
            correlation_id=attempt.client_attempt_id,
        )
        for _ in range(EVENT_QUEUE_CAPACITY)
    ]
    assert all(accepted)
    assert not emitter.emit(
        ServerEventCode.ATTEMPT_ADMITTED,
        attempt_id=attempt.id,
        correlation_id=attempt.client_attempt_id,
    )
    assert vars(attempt) == before
    release.set()
    emitter.stop()


def test_failed_writer_transaction_is_lost_without_retry_and_later_event_continues(
    disposable_event_engine: Engine,
) -> None:
    calls = 0

    class FailedCommitSession(Session):
        def commit(self) -> None:
            raise RuntimeError("synthetic redacted sink failure")

    def session_factory() -> Session:
        nonlocal calls
        calls += 1
        session_type = FailedCommitSession if calls == 1 else Session
        return session_type(bind=disposable_event_engine)

    attempt_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    emitter = ServerEventEmitter(session_factory, release_id=_RELEASE)
    emitter.start()
    try:
        assert emitter.emit(
            ServerEventCode.ATTEMPT_FAILED,
            attempt_id=attempt_id,
            correlation_id=correlation_id,
        )
        assert emitter.emit(
            ServerEventCode.PROMO_RESULT_ISSUED,
            attempt_id=attempt_id,
            correlation_id=correlation_id,
        )
        _wait_for_code(
            disposable_event_engine,
            ServerEventCode.PROMO_RESULT_ISSUED,
            attempt_id,
        )
        with Session(disposable_event_engine) as session:
            assert session.scalar(
                select(func.count())
                .select_from(ServerEvent)
                .where(
                    ServerEvent.event_code == ServerEventCode.ATTEMPT_FAILED.value,
                    ServerEvent.attempt_id == attempt_id,
                )
            ) == 0
    finally:
        emitter.stop()


class _Attempt:
    def __init__(self, processing_status: str) -> None:
        self.id = uuid.uuid4()
        self.client_attempt_id = uuid.uuid4()
        self.processing_status = processing_status


def _wait_for_count(engine: Engine, minimum: int) -> None:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        with Session(engine) as session:
            count = session.scalar(select(func.count()).select_from(ServerEvent)) or 0
        if count >= minimum:
            return
        time.sleep(0.02)
    raise AssertionError(f"server-event count did not reach {minimum}")


def _wait_for_code(
    engine: Engine, code: ServerEventCode, attempt_id: uuid.UUID
) -> None:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        with Session(engine) as session:
            found = session.scalar(
                select(ServerEvent.event_id).where(
                    ServerEvent.event_code == code.value,
                    ServerEvent.attempt_id == attempt_id,
                )
            )
        if found is not None:
            return
        time.sleep(0.02)
    raise AssertionError(f"server event {code.value} was not persisted")

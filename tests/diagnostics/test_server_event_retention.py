from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.diagnostics.retention import (
    DiagnosticRetentionProvider,
    DiagnosticRetentionResult,
    RetentionObjectStore,
)
from face_moment.diagnostics.server_events import ServerEvent
from face_moment.infrastructure.settings import Settings
from face_moment.promo.retention import (
    RetentionCleanupLatest,
    run_retention_cleanup,
)


NOW = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)
TECHNICAL_CUTOFF = NOW - timedelta(days=30)


@pytest.fixture
def disposable_server_event_retention_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Engine]:
    base_settings = Settings.from_env()
    probe_database = f"task093_{uuid.uuid4().hex}"
    probe_url = make_url(base_settings.database_url).set(database=probe_database)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {probe_database}")
    monkeypatch.setenv("DATABASE_URL", probe_url.render_as_string(hide_password=False))
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)"
            )
        admin_engine.dispose()


def test_cleanup_expires_only_server_events_strictly_before_technical_cutoff(
    disposable_server_event_retention_engine: Engine,
) -> None:
    engine = disposable_server_event_retention_engine
    attempt_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    old_correlated = _event(
        occurred_at=TECHNICAL_CUTOFF - timedelta(microseconds=1),
        event_code="attempt.admitted",
        severity="info",
        component="realtime",
        attempt_id=attempt_id,
        correlation_id=correlation_id,
    )
    old_uncorrelated = _event(
        occurred_at=TECHNICAL_CUTOFF - timedelta(days=1),
        event_code="runtime.readiness_closed",
        severity="warning",
        component="runtime",
    )
    equal_cutoff = _event(
        occurred_at=TECHNICAL_CUTOFF,
        event_code="runtime.readiness_closed",
        severity="warning",
        component="runtime",
    )
    newer = _event(
        occurred_at=TECHNICAL_CUTOFF + timedelta(microseconds=1),
        event_code="attempt.failed",
        severity="error",
        component="realtime",
        attempt_id=attempt_id,
        correlation_id=correlation_id,
    )
    old_ids = {old_correlated.event_id, old_uncorrelated.event_id}
    retained_ids = {equal_cutoff.event_id, newer.event_id}

    with Session(engine) as session:
        session.add_all([old_correlated, old_uncorrelated, equal_cutoff, newer])
        session.commit()

        outcome = run_retention_cleanup(session, now=NOW)

        assert outcome.exit_code == 0
        assert outcome.counts[2] == 2
        assert set(session.scalars(select(ServerEvent.event_id)).all()) == retained_ids
        latest = session.get(RetentionCleanupLatest, 1)
        assert latest is not None
        assert latest.technical_logs_deleted == 2

        rerun = run_retention_cleanup(session, now=NOW)
        assert rerun.exit_code == 0
        assert rerun.counts[2] == 0
        assert set(session.scalars(select(ServerEvent.event_id)).all()) == retained_ids
        assert old_ids.isdisjoint(retained_ids)


def test_partial_owner_failure_keeps_deleted_events_gone_and_rerun_truthful(
    disposable_server_event_retention_engine: Engine,
) -> None:
    engine = disposable_server_event_retention_engine
    old_event = _event(
        occurred_at=TECHNICAL_CUTOFF - timedelta(days=1),
        event_code="runtime.readiness_closed",
        severity="warning",
        component="runtime",
    )
    old_event_id = old_event.event_id

    with Session(engine) as session:
        session.add(old_event)
        session.commit()
        failed = run_retention_cleanup(
            session,
            now=NOW,
            diagnostics=FailAfterServerEventDeletion(session),
        )

        assert failed.exit_code == 1
        assert failed.error == "owner cleanup failed"
        assert session.get(ServerEvent, old_event_id) is None
        latest = session.get(RetentionCleanupLatest, 1)
        assert latest is not None
        assert latest.status == "failed"
        assert latest.technical_logs_deleted == 0

        rerun = run_retention_cleanup(session, now=NOW)
        assert rerun.exit_code == 0
        assert rerun.technical_logs_deleted == 0
        assert session.get(ServerEvent, old_event_id) is None


class FailAfterServerEventDeletion(DiagnosticRetentionProvider):
    def expire(
        self,
        attempt_ids: Iterable[uuid.UUID],
        *,
        cutoff: datetime,
        now: datetime | None = None,
        object_store: RetentionObjectStore | None = None,
    ) -> DiagnosticRetentionResult:
        del attempt_ids, cutoff, now, object_store
        raise RuntimeError("protected task093 failure detail")


def _event(
    *,
    occurred_at: datetime,
    event_code: str,
    severity: str,
    component: str,
    attempt_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
) -> ServerEvent:
    return ServerEvent(
        event_id=uuid.uuid4(),
        occurred_at=occurred_at,
        severity=severity,
        component=component,
        event_code=event_code,
        release_id="task093-synthetic-release",
        attempt_id=attempt_id,
        correlation_id=correlation_id,
    )

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date, datetime, timezone
from types import SimpleNamespace
import uuid

from alembic import command as alembic_command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints import realtime
from face_moment.infrastructure.settings import Settings
from face_moment.processing import PipelineCode
from face_moment.promo import PromoAttempt, PromoAttemptRepository
from face_moment.promo.startup_recovery import RealtimeStartupRecoveryRepository


@pytest.fixture
def disposable_realtime_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    base_settings = Settings.from_env()
    probe_database = f"task074_{uuid.uuid4().hex}"
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


def _attempt_values() -> dict[str, object]:
    return {
        "spa_id": uuid.uuid4(),
        "client_attempt_id": uuid.uuid4(),
        "trigger_source": "test",
        "client_release": "task074-test",
        "detector_id": "task074-detector",
        "model_version": "task074-model",
        "jpeg_quality": 85,
        "camera_device_id": "task074-camera",
        "reference_series_ready_at": datetime(
            2026, 8, 22, 10, 0, tzinfo=timezone.utc
        ),
        "local_detection_completed_ms": 10,
        "request_started_ms": 20,
        "proposal_count": 1,
        "settings_revision": 1,
        "visit_date": date(2026, 8, 22),
        "pipeline_revision_id": uuid.uuid4(),
        "pipeline_code": PipelineCode.OPENCV_SFACE,
        "query_source": "reference",
        "threshold": 0.7,
        "quality_settings": {"minimum_edge": 48},
        "release_id": "task074-server",
        "deadline_ms": 3000,
    }


def _seed_attempts(engine: Engine) -> dict[str, uuid.UUID]:
    attempt_ids: dict[str, uuid.UUID] = {}
    with Session(engine) as session:
        for status in (
            "accepted",
            "searching",
            "result_issued",
            "no_success",
            "interrupted",
            "deadline",
            "internal_failure",
        ):
            values = _attempt_values()
            attempt = PromoAttemptRepository(session).create_or_get(**values)
            attempt.processing_status = status
            if status == "result_issued":
                attempt.domain_outcome = "result"
            elif status == "no_success":
                attempt.domain_outcome = "busy"
            elif status in {"interrupted", "deadline"}:
                attempt.domain_outcome = status
            attempt_ids[status] = attempt.id
        session.commit()
    return attempt_ids


def _run_realtime_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
) -> list[int]:
    inference_calls: list[str] = []

    class FakeAdapter:
        pipeline_revision_id = uuid.uuid4()

        def search(self) -> None:
            inference_calls.append("search")

    binding = SimpleNamespace(
        session_factory=lambda: Session(engine),
        adapter=FakeAdapter(),
        close=lambda: None,
    )
    monkeypatch.setattr(realtime, "bind_model_consumer", lambda _settings: binding)
    state: dict[str, object] = {"ready": False}

    async def enter_and_exit() -> None:
        async with realtime._realtime_lifecycle(  # noqa: SLF001
            SimpleNamespace(
                realtime_result_display_ms=15_000,
                realtime_success_cooldown_ms=30_000,
            ),
            state,
        ):
            assert state["ready"] is False

    asyncio.run(enter_and_exit())
    return inference_calls


def test_realtime_startup_interrupts_only_stale_attempts_and_is_idempotent(
    disposable_realtime_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt_ids = _seed_attempts(disposable_realtime_engine)
    stale_session = Session(disposable_realtime_engine)
    stale_values = _attempt_values()
    stale_attempt = PromoAttemptRepository(stale_session).create_or_get(**stale_values)
    stale_session.commit()
    stale_attempt = PromoAttemptRepository(stale_session).get(stale_attempt.id)

    try:
        assert _run_realtime_lifecycle(monkeypatch, disposable_realtime_engine) == []

        with Session(disposable_realtime_engine) as session:
            rows = {
                row.id: row
                for row in session.scalars(
                    select(PromoAttempt).where(
                        PromoAttempt.id.in_(attempt_ids.values())
                    )
                )
            }
            accepted = rows[attempt_ids["accepted"]]
            searching = rows[attempt_ids["searching"]]
            assert accepted.processing_status == "interrupted"
            assert searching.processing_status == "interrupted"
            assert accepted.domain_outcome == "interrupted"
            assert searching.domain_outcome == "interrupted"
            assert accepted.search_finished_at is not None
            assert searching.search_finished_at is not None
            assert accepted.updated_at >= accepted.search_finished_at
            assert searching.updated_at >= searching.search_finished_at
            assert rows[attempt_ids["result_issued"]].domain_outcome == "result"
            assert rows[attempt_ids["no_success"]].domain_outcome == "busy"
            assert rows[attempt_ids["deadline"]].domain_outcome == "deadline"
            assert rows[attempt_ids["internal_failure"]].domain_outcome is None
            assert rows[attempt_ids["result_issued"]].search_finished_at is None
            assert rows[attempt_ids["no_success"]].search_finished_at is None

        with pytest.raises(ValueError, match="only an accepted Attempt"):
            PromoAttemptRepository(stale_session).mark_internal_failure(stale_attempt)
        stale_session.rollback()

        with Session(disposable_realtime_engine) as session:
            assert RealtimeStartupRecoveryRepository(session).recover() == 0
            session.commit()

        fresh_id: uuid.UUID
        with Session(disposable_realtime_engine) as session:
            fresh_values = _attempt_values()
            fresh = PromoAttemptRepository(session).create_or_get(**fresh_values)
            assert fresh.processing_status == "accepted"

            interrupted = session.get(PromoAttempt, attempt_ids["accepted"])
            assert interrupted is not None
            with pytest.raises(ValueError, match="only an accepted Attempt"):
                PromoAttemptRepository(session).mark_no_proposals(interrupted)
            with pytest.raises(ValueError, match="only an accepted Attempt"):
                PromoAttemptRepository(session).mark_internal_failure(interrupted)
            session.commit()
            fresh_id = fresh.id

        with Session(disposable_realtime_engine) as session:
            fresh = session.get(PromoAttempt, fresh_id)
            assert fresh is not None
            assert fresh.processing_status == "accepted"
            assert fresh.domain_outcome is None
    finally:
        stale_session.close()

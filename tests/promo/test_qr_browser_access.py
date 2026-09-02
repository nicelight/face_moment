from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Barrier
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings
from face_moment.processing import PipelineCode
from face_moment.promo import (
    BROWSER_IDLE_TTL,
    PromoAttempt,
    PromoAttemptRepository,
    PromoBrowserAccessExpiredError,
    PromoSession,
    PromoSessionRepository,
    ResultAssembly,
)


QR_SECRET = b"task080-disposable-qr-secret"


@pytest.fixture
def disposable_qr_engine(monkeypatch: pytest.MonkeyPatch) -> Engine:
    base_settings = Settings.from_env()
    probe_database = f"task080_{uuid.uuid4().hex}"
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


def _attempt_values(client_attempt_id: uuid.UUID) -> dict[str, object]:
    return {
        "spa_id": uuid.uuid4(),
        "client_attempt_id": client_attempt_id,
        "trigger_source": "test",
        "client_release": "task080-qr-access",
        "detector_id": "task080-detector",
        "model_version": "task080-model",
        "jpeg_quality": 82,
        "camera_device_id": "task080-camera",
        "reference_series_ready_at": datetime(
            2026, 8, 28, 12, 0, tzinfo=timezone.utc
        ),
        "local_detection_completed_ms": 140,
        "request_started_ms": 220,
        "proposal_count": 4,
        "settings_revision": 4,
        "visit_date": date(2026, 8, 28),
        "pipeline_revision_id": uuid.uuid4(),
        "pipeline_code": PipelineCode.OPENCV_SFACE,
        "query_source": "reference",
        "threshold": 0.71,
        "quality_settings": {"version": 1},
        "release_id": "task080-server",
        "deadline_ms": 3000,
        "calibration_id": uuid.uuid4(),
    }


def _assembly() -> ResultAssembly:
    union = tuple(uuid.uuid4() for _ in range(6))
    return ResultAssembly(
        outcome="result",
        session_result_photo_ids=union,
        teaser_photo_ids=(union[2], union[0], union[5], union[1]),
        n=len(union),
    )


def _seed_result_session(
    engine: Engine, *, issued_at: datetime
) -> tuple[str, uuid.UUID, dict[str, object]]:
    values = _attempt_values(uuid.uuid4())
    with Session(engine) as session:
        attempts = PromoAttemptRepository(session)
        attempt = attempts.create_or_get(**values)
        attempts.mark_search_started(attempt, now=issued_at - timedelta(seconds=1))
        response = attempts.publish_result(
            attempt,
            _assembly(),
            qr_ticket_secret=QR_SECRET,
            qr_issued_at=issued_at,
            display_expires_at=issued_at + timedelta(minutes=5),
        )
        session.commit()
        return response.qr_url.removeprefix("/q?ticket="), attempt.id, values


def test_migration_round_trip_preserves_issued_session_truth(
    disposable_qr_engine: Engine,
) -> None:
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("0014_promo_browser_access")
    assert revision is not None
    assert revision.down_revision == "0013_promo_sessions"

    alembic_command.downgrade(config, "0013_promo_sessions")
    attempt_id = uuid.uuid4()
    session_id = uuid.uuid4()
    spa_id = uuid.uuid4()
    photo_ids = [uuid.uuid4() for _ in range(6)]
    issued_at = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    ticket_digest = b"t" * 32
    attempt_values = _attempt_values(uuid.uuid4())
    attempt_values.update(
        id=attempt_id,
        spa_id=spa_id,
        processing_status="result_issued",
        domain_outcome="result",
        display_status="pending",
        display_expires_at=issued_at + timedelta(minutes=5),
    )
    with disposable_qr_engine.begin() as connection:
        connection.execute(PromoAttempt.__table__.insert().values(**attempt_values))
        connection.execute(
            PromoSession.__table__.insert().values(
                id=session_id,
                attempt_id=attempt_id,
                spa_id=spa_id,
                visit_date=date(2026, 8, 28),
                session_result_photo_ids=photo_ids,
                teaser_photo_ids=photo_ids[:4],
                n=len(photo_ids),
                qr_ticket_hash_sha256=ticket_digest,
                qr_issued_at=issued_at,
                qr_first_open_expires_at=issued_at + timedelta(minutes=30),
            )
        )

    alembic_command.upgrade(config, "head")
    alembic_command.downgrade(config, "0013_promo_sessions")
    with disposable_qr_engine.connect() as connection:
        preserved = connection.execute(
            text(
                "SELECT id, attempt_id, spa_id, session_result_photo_ids, "
                "teaser_photo_ids, n, qr_ticket_hash_sha256 "
                "FROM face_moment.promo_sessions WHERE id = :session_id"
            ),
            {"session_id": session_id},
        ).one()
    assert preserved.id == session_id
    assert preserved.attempt_id == attempt_id
    assert preserved.spa_id == spa_id
    assert preserved.session_result_photo_ids == photo_ids
    assert preserved.teaser_photo_ids == photo_ids[:4]
    assert preserved.n == len(photo_ids)
    assert bytes(preserved.qr_ticket_hash_sha256) == ticket_digest

    alembic_command.upgrade(config, "head")
    columns = {
        column["name"] for column in inspect(disposable_qr_engine).get_columns(
            "promo_sessions", schema=APP_SCHEMA
        )
    }
    assert {"browser_first_opened_at", "browser_last_seen_at"} <= columns
    check_names = {
        check["name"]
        for check in inspect(disposable_qr_engine).get_check_constraints(
            "promo_sessions", schema=APP_SCHEMA
        )
    }
    assert "ck_promo_sessions_browser_access_timestamp_pair" in check_names
    with disposable_qr_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT session_result_photo_ids, teaser_photo_ids, n, "
                "qr_ticket_hash_sha256, qr_issued_at, "
                "qr_first_open_expires_at, browser_first_opened_at, "
                "browser_last_seen_at FROM face_moment.promo_sessions "
                "WHERE id = :session_id"
            ),
            {"session_id": session_id},
        ).one()
    assert row.session_result_photo_ids == photo_ids
    assert row.teaser_photo_ids == photo_ids[:4]
    assert row.n == len(photo_ids)
    assert bytes(row.qr_ticket_hash_sha256) == ticket_digest
    assert row.qr_issued_at == issued_at
    assert row.qr_first_open_expires_at == issued_at + timedelta(minutes=30)
    assert row.browser_first_opened_at is None
    assert row.browser_last_seen_at is None


def test_browser_access_has_strict_boundaries_passive_reads_and_restart_persistence(
    disposable_qr_engine: Engine,
) -> None:
    issued_at = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    ticket, attempt_id, immutable_values = _seed_result_session(
        disposable_qr_engine, issued_at=issued_at
    )
    first_open_at = issued_at + timedelta(minutes=1)

    with Session(disposable_qr_engine) as session:
        opened, first_open = PromoSessionRepository(
            session, qr_ticket_secret=QR_SECRET
        ).open_browser_access(ticket, now=first_open_at)
        assert first_open
        assert opened.browser_first_opened_at == first_open_at
        assert opened.browser_last_seen_at == first_open_at
        assert opened.browser_idle_expires_at == first_open_at + BROWSER_IDLE_TTL
        session.commit()

    repeated_scan_at = issued_at + timedelta(minutes=5)
    with Session(disposable_qr_engine) as session:
        repository = PromoSessionRepository(session, qr_ticket_secret=QR_SECRET)
        repeated, first_open = repository.open_browser_access(
            ticket, now=repeated_scan_at
        )
        assert not first_open
        session.commit()
        assert repeated.browser_last_seen_at == repeated_scan_at

    with Session(disposable_qr_engine) as session:
        repository = PromoSessionRepository(session, qr_ticket_secret=QR_SECRET)
        passive = repository.read_browser_access(
            ticket, now=issued_at + timedelta(minutes=10)
        )
        assert passive.browser_last_seen_at == repeated_scan_at
        session.rollback()

    activity_at = issued_at + timedelta(minutes=31)
    with Session(disposable_qr_engine) as session:
        active = PromoSessionRepository(
            session, qr_ticket_secret=QR_SECRET
        ).record_browser_activity(ticket, now=activity_at)
        session.commit()
        assert active.browser_last_seen_at == activity_at

    with Session(disposable_qr_engine) as session:
        repository = PromoSessionRepository(session, qr_ticket_secret=QR_SECRET)
        with pytest.raises(PromoBrowserAccessExpiredError):
            repository.open_browser_access(
                ticket, now=issued_at + timedelta(minutes=30)
            )
        session.rollback()

    idle_boundary = activity_at + BROWSER_IDLE_TTL
    with Session(disposable_qr_engine) as session:
        repository = PromoSessionRepository(session, qr_ticket_secret=QR_SECRET)
        with pytest.raises(PromoBrowserAccessExpiredError):
            repository.read_browser_access(ticket, now=idle_boundary)
        session.rollback()

    with Session(disposable_qr_engine) as session:
        row = session.get(PromoSession, session.scalar(select(PromoSession.id).where(PromoSession.attempt_id == attempt_id)))
        assert row is not None
        assert row.browser_first_opened_at == first_open_at
        assert row.browser_last_seen_at == activity_at
        assert row.session_result_photo_ids
        assert row.n == len(row.session_result_photo_ids)
        attempt = session.get(PromoAttempt, attempt_id)
        assert attempt is not None
        assert attempt.spa_id == immutable_values["spa_id"]
        assert attempt.visit_date == immutable_values["visit_date"]
        assert row.browser_idle_expires_at == idle_boundary


def _open_concurrently(
    engine: Engine,
    ticket: str,
    now: datetime,
    barrier: Barrier,
) -> tuple[uuid.UUID, datetime | None, datetime | None]:
    barrier.wait()
    with Session(engine) as session:
        row, _first_open = PromoSessionRepository(
            session, qr_ticket_secret=QR_SECRET
        ).open_browser_access(ticket, now=now)
        result = (row.id, row.browser_first_opened_at, row.browser_last_seen_at)
        session.commit()
        return result


def _record_activity_concurrently(
    engine: Engine,
    ticket: str,
    now: datetime,
    barrier: Barrier,
) -> tuple[uuid.UUID, datetime | None]:
    barrier.wait()
    with Session(engine) as session:
        row = PromoSessionRepository(
            session, qr_ticket_secret=QR_SECRET
        ).record_browser_activity(ticket, now=now)
        result = (row.id, row.browser_last_seen_at)
        session.commit()
        return result


def test_concurrent_phones_share_one_monotonic_state_row(
    disposable_qr_engine: Engine,
) -> None:
    issued_at = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    ticket, attempt_id, _ = _seed_result_session(
        disposable_qr_engine, issued_at=issued_at
    )
    first_open_at = issued_at + timedelta(minutes=2)
    open_barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        opened = list(
            executor.map(
                lambda _: _open_concurrently(
                    disposable_qr_engine, ticket, first_open_at, open_barrier
                ),
                range(2),
            )
        )
    assert {result[0] for result in opened} == {
        opened[0][0]
    }
    assert {result[1] for result in opened} == {first_open_at}
    assert {result[2] for result in opened} == {first_open_at}

    activity_times = [
        issued_at + timedelta(minutes=9),
        issued_at + timedelta(minutes=12),
    ]
    activity_barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        activity_results = list(
            executor.map(
                lambda current: _record_activity_concurrently(
                    disposable_qr_engine, ticket, current, activity_barrier
                ),
                activity_times,
            )
        )
    assert {result[0] for result in activity_results} == {opened[0][0]}
    assert {result[1] for result in activity_results} <= set(activity_times)

    with Session(disposable_qr_engine) as session:
        row = session.scalar(
            select(PromoSession).where(PromoSession.attempt_id == attempt_id)
        )
        assert row is not None
        assert row.browser_first_opened_at == first_open_at
        assert row.browser_last_seen_at == max(activity_times)
        assert session.scalar(
            text(
                "SELECT count(*) FROM face_moment.promo_sessions "
                "WHERE attempt_id = :attempt_id"
            ),
            {"attempt_id": attempt_id},
        ) == 1
        table_names = set(
            inspect(disposable_qr_engine).get_table_names(schema=APP_SCHEMA)
        )
        assert not table_names & {
            "promo_browser_access",
            "promo_access_grants",
            "promo_access_scheduler",
        }

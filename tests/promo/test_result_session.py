from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
import hashlib
import secrets
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings
from face_moment.processing import PipelineCode
from face_moment.promo import (
    PromoAttempt,
    PromoAttemptRepository,
    PromoSession,
    PromoSessionRepository,
    ResultAssembly,
)


@pytest.fixture
def disposable_result_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    base_settings = Settings.from_env()
    probe_database = f"task072_{uuid.uuid4().hex}"
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
        "client_release": "kiosk-result-session",
        "detector_id": "mediapipe_blazeface_full_range",
        "model_version": "model-result-session",
        "jpeg_quality": 82,
        "camera_device_id": "camera-result-session",
        "reference_series_ready_at": datetime(
            2026, 8, 22, 12, 0, tzinfo=timezone.utc
        ),
        "local_detection_completed_ms": 140,
        "request_started_ms": 220,
        "proposal_count": 4,
        "settings_revision": 4,
        "visit_date": date(2026, 8, 22),
        "pipeline_revision_id": uuid.uuid4(),
        "pipeline_code": PipelineCode.OPENCV_SFACE,
        "query_source": "reference",
        "threshold": 0.71,
        "quality_settings": {"version": 1},
        "release_id": "server-result-session",
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


def _admit_searching(session: Session) -> PromoAttempt:
    attempt = PromoAttemptRepository(session).create_or_get(
        **_attempt_values(uuid.uuid4())
    )
    PromoAttemptRepository(session).mark_search_started(
        attempt,
        now=datetime(2026, 8, 22, 12, 0, 1, tzinfo=timezone.utc),
    )
    session.commit()
    return attempt


def test_result_session_publication_is_immutable_digest_only_and_idempotent(
    disposable_result_engine: Engine,
) -> None:
    secret = secrets.token_bytes(32)
    assembly = _assembly()
    issued_at = datetime(2026, 8, 22, 12, 1, tzinfo=timezone.utc)
    display_expires_at = issued_at + timedelta(seconds=20)
    with Session(disposable_result_engine) as session:
        attempt = _admit_searching(session)
        repository = PromoAttemptRepository(session)
        first = repository.publish_result(
            attempt,
            assembly,
            qr_ticket_secret=secret,
            qr_issued_at=issued_at,
            display_expires_at=display_expires_at,
        )
        session.commit()
        attempt_id = attempt.id

        assert first.teasers == assembly.teaser_photo_ids
        assert first.n == len(assembly.session_result_photo_ids)
        assert first.qr_url.startswith("/q?ticket=")
        assert first.qr_first_open_expires_at == issued_at + timedelta(minutes=30)
        assert attempt.processing_status == "result_issued"
        assert attempt.domain_outcome == "result"
        assert attempt.display_status == "pending"
        assert attempt.display_expires_at == display_expires_at

        persisted = PromoSessionRepository(
            session, qr_ticket_secret=secret
        ).get_for_attempt(attempt_id)
        ticket = first.qr_url.removeprefix("/q?ticket=")
        assert persisted.spa_id == attempt.spa_id
        assert persisted.visit_date == attempt.visit_date
        assert persisted.session_result_photo_ids == list(
            assembly.session_result_photo_ids
        )
        assert persisted.teaser_photo_ids == list(assembly.teaser_photo_ids)
        assert persisted.n == len(assembly.session_result_photo_ids)
        assert persisted.qr_ticket_hash_sha256 == hashlib.sha256(
            ticket.encode("ascii")
        ).digest()
        assert not hasattr(persisted, "qr_ticket")

        second = repository.publish_result(
            attempt,
            assembly,
            qr_ticket_secret=secret,
            display_expires_at=display_expires_at,
        )
        assert second == first
        assert session.scalar(
            text(
                "SELECT count(*) FROM face_moment.promo_sessions "
                "WHERE attempt_id = :attempt_id"
            ),
            {"attempt_id": attempt_id},
        ) == 1


@pytest.mark.parametrize("failure_point", ["session_inserted", "attempt_transitioned"])
def test_result_publication_failure_rolls_back_both_halves(
    disposable_result_engine: Engine,
    failure_point: str,
) -> None:
    assembly = _assembly()
    with Session(disposable_result_engine) as session:
        attempt = _admit_searching(session)

        def fail(point: str) -> None:
            if point == failure_point:
                raise RuntimeError("injected publication write failure")

        with pytest.raises(RuntimeError, match="injected publication"):
            PromoAttemptRepository(session).publish_result(
                attempt,
                assembly,
                qr_ticket_secret=secrets.token_bytes(32),
                qr_issued_at=datetime(2026, 8, 22, 12, 1, tzinfo=timezone.utc),
                display_expires_at=datetime(
                    2026, 8, 22, 12, 1, 20, tzinfo=timezone.utc
                ),
                failure_hook=fail,
            )
        session.commit()

        state = session.get(PromoAttempt, attempt.id)
        assert state is not None
        assert state.processing_status == "searching"
        assert session.scalar(
            text(
                "SELECT count(*) FROM face_moment.promo_sessions "
                "WHERE attempt_id = :attempt_id"
            ),
            {"attempt_id": attempt.id},
        ) == 0


def test_session_migration_round_trip_and_owner_local_foreign_key(
    disposable_result_engine: Engine,
) -> None:
    inspector = inspect(disposable_result_engine)
    assert "promo_attempts" in inspector.get_table_names(schema=APP_SCHEMA)
    assert "promo_sessions" in inspector.get_table_names(schema=APP_SCHEMA)
    foreign_keys = inspector.get_foreign_keys(
        "promo_sessions", schema=APP_SCHEMA
    )
    assert [key["referred_table"] for key in foreign_keys] == ["promo_attempts"]

    alembic_config = Config("alembic.ini")
    alembic_command.downgrade(alembic_config, "0012_promo_attempts")
    downgraded = inspect(disposable_result_engine)
    assert "promo_sessions" not in downgraded.get_table_names(schema=APP_SCHEMA)
    assert "promo_attempts" in downgraded.get_table_names(schema=APP_SCHEMA)
    alembic_command.upgrade(alembic_config, "head")
    upgraded = inspect(disposable_result_engine)
    assert "promo_sessions" in upgraded.get_table_names(schema=APP_SCHEMA)

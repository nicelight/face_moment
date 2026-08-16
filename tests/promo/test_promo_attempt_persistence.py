from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Barrier
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
from face_moment.promo import PromoAttempt, PromoAttemptRepository


@pytest.fixture
def disposable_attempt_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    base_settings = Settings.from_env()
    probe_database = f"task043_{uuid.uuid4().hex}"
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
        "client_release": "kiosk-1.2.3",
        "detector_id": "yunet",
        "model_version": "sface-2021",
        "jpeg_quality": 82,
        "camera_device_id": "camera-task043",
        "reference_series_ready_at": datetime(2026, 8, 16, 0, 1, tzinfo=timezone.utc),
        "local_detection_completed_ms": 140,
        "request_started_ms": 220,
        "proposal_count": 3,
        "settings_revision": 4,
        "visit_date": date(2026, 8, 16),
        "pipeline_revision_id": uuid.uuid4(),
        "pipeline_code": PipelineCode.OPENCV_SFACE,
        "query_source": "reference",
        "threshold": 0.71,
        "quality_settings": {"version": 1, "minimum_edge": 48},
        "release_id": "server-2026.08.16",
        "deadline_ms": 3000,
        "calibration_id": uuid.uuid4(),
    }


def _cleanup(engine: Engine, attempt_id: uuid.UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM face_moment.promo_attempts WHERE id = :id"),
            {"id": attempt_id},
        )


def test_promo_attempt_create_read_restart_and_idempotent_duplicate(
    disposable_attempt_engine: Engine,
) -> None:
    client_attempt_id = uuid.uuid4()
    values = _attempt_values(client_attempt_id)
    with Session(disposable_attempt_engine) as session:
        repository = PromoAttemptRepository(session)
        attempt = repository.create_or_get(**values)
        session.commit()
        attempt_id = attempt.id
        assert attempt.processing_status == "accepted"
        assert attempt.display_status == "not_applicable"
        assert attempt.proposal_count == 3

    try:
        changed_values = {
            **values,
            "client_release": "must-not-overwrite",
            "proposal_count": 20,
        }
        with Session(disposable_attempt_engine) as session:
            repeated = PromoAttemptRepository(session).create_or_get(**changed_values)
            assert repeated.id == attempt_id
            session.commit()

        restarted_engine = create_engine(disposable_attempt_engine.url, pool_pre_ping=True)
        try:
            with Session(restarted_engine) as session:
                persisted = PromoAttemptRepository(session).get(attempt_id)
                assert persisted.client_release == "kiosk-1.2.3"
                assert persisted.proposal_count == 3
                assert persisted.pipeline_code == PipelineCode.OPENCV_SFACE.value
                assert persisted.quality_settings == {"version": 1, "minimum_edge": 48}
        finally:
            restarted_engine.dispose()
    finally:
        _cleanup(disposable_attempt_engine, attempt_id)


def test_promo_attempt_concurrent_duplicate_admission_has_one_row(
    disposable_attempt_engine: Engine,
) -> None:
    client_attempt_id = uuid.uuid4()
    values = _attempt_values(client_attempt_id)
    barrier = Barrier(2)

    def admit_once() -> uuid.UUID:
        with Session(disposable_attempt_engine) as session:
            barrier.wait()
            attempt = PromoAttemptRepository(session).create_or_get(**values)
            session.commit()
            return attempt.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(lambda _index: admit_once(), range(2)))
    assert ids[0] == ids[1]
    try:
        with disposable_attempt_engine.connect() as connection:
            count = connection.scalar(
                text(
                    "SELECT count(*) FROM face_moment.promo_attempts "
                    "WHERE spa_id = :spa_id AND client_attempt_id = :client_attempt_id"
                ),
                {
                    "spa_id": values["spa_id"],
                    "client_attempt_id": client_attempt_id,
                },
            )
            assert count == 1
    finally:
        _cleanup(disposable_attempt_engine, ids[0])


def test_promo_attempt_shape_has_no_photo_or_diagnostic_cascade(
    disposable_attempt_engine: Engine,
) -> None:
    assert not PromoAttempt.__table__.foreign_keys
    assert "promo_attempts" in inspect(disposable_attempt_engine).get_table_names(
        schema=APP_SCHEMA
    )


def test_promo_attempt_migration_round_trip(
    disposable_attempt_engine: Engine,
) -> None:
    alembic_config = Config("alembic.ini")
    alembic_command.downgrade(alembic_config, "0011_active_search_context")
    assert "promo_attempts" not in inspect(
        disposable_attempt_engine
    ).get_table_names(schema=APP_SCHEMA)
    alembic_command.upgrade(alembic_config, "head")
    assert "promo_attempts" in inspect(
        disposable_attempt_engine
    ).get_table_names(schema=APP_SCHEMA)

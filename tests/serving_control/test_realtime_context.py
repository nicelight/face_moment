from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timezone
import importlib
import math
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control import (
    ReferenceSearchSettingsAlreadyExistsError,
    ReferenceSearchSettingsNotFoundError,
    RealtimeContextRepository,
)
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@pytest.fixture
def disposable_context_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    base_settings = Settings.from_env()
    probe_database = f"task042_{uuid.uuid4().hex}"
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


def _create_spa(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    from face_moment.serving_control.ingest_target import Spa

    with Session(engine) as session:
        revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
            **PIPELINE_COMPATIBILITY,
        )
        spa = Spa(
            name=f"task042-spa-{uuid.uuid4().hex}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=revision.id,
        )
        session.add(spa)
        session.commit()
        return spa.id, revision.id


def _cleanup(engine: Engine, spa_id: uuid.UUID, revision_id: uuid.UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM face_moment.reference_search_settings WHERE spa_id = :id"),
            {"id": spa_id},
        )
        connection.execute(
            text("DELETE FROM face_moment.spas WHERE id = :id"), {"id": spa_id}
        )
        connection.execute(
            text("DELETE FROM face_moment.pipeline_revisions WHERE id = :id"),
            {"id": revision_id},
        )


def test_realtime_context_persistence_is_owner_scoped_and_revisioned(
    disposable_context_engine: Engine,
) -> None:
    serving_control = importlib.import_module("face_moment.serving_control")
    assert hasattr(serving_control, "RealtimeContextRepository")
    spa_id, revision_id = _create_spa(disposable_context_engine)
    provisioned_at = datetime(2026, 8, 16, 0, 1, tzinfo=timezone.utc)
    updated_at = datetime(2026, 8, 16, 0, 2, tzinfo=timezone.utc)
    try:
        with Session(disposable_context_engine) as session:
            repository = RealtimeContextRepository(session)
            settings = repository.provision_reference_settings(
                spa_id=spa_id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
                reference_threshold=0.71,
                min_query_face_quality=0.42,
                quality_settings={"version": 1, "minimum_edge": 48},
                calibration_id=uuid.uuid4(),
                now=provisioned_at,
            )
            spa = repository.update_active_visit_date(
                spa_id=spa_id,
                active_visit_date=date(2026, 8, 16),
                now=provisioned_at,
            )
            assert settings.query_source == "reference"
            assert settings.reference_threshold == 0.71
            assert settings.min_query_face_quality == 0.42
            assert settings.quality_settings == {"version": 1, "minimum_edge": 48}
            assert spa.active_visit_date == date(2026, 8, 16)
            assert spa.settings_revision == 3
            session.commit()

        with Session(disposable_context_engine) as session:
            settings = RealtimeContextRepository(session).update_reference_settings(
                spa_id=spa_id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
                reference_threshold=0.81,
                min_query_face_quality=0.55,
                quality_settings={"version": 2, "minimum_edge": 64},
                now=updated_at,
            )
            assert settings.updated_at == updated_at
            session.commit()

        restarted_engine = create_engine(disposable_context_engine.url, pool_pre_ping=True)
        try:
            from face_moment.serving_control.ingest_target import Spa

            with Session(restarted_engine) as session:
                repository = RealtimeContextRepository(session)
                settings = repository.get_reference_settings(
                    spa_id=spa_id, pipeline_code=PipelineCode.OPENCV_SFACE
                )
                spa = session.get(Spa, spa_id)
                assert settings.reference_threshold == 0.81
                assert settings.min_query_face_quality == 0.55
                assert settings.quality_settings == {"version": 2, "minimum_edge": 64}
                assert spa is not None
                assert spa.settings_revision == 4
                assert spa.active_visit_date == date(2026, 8, 16)
        finally:
            restarted_engine.dispose()
    finally:
        _cleanup(disposable_context_engine, spa_id, revision_id)


def test_realtime_context_rejects_invalid_values_and_duplicate_keys(
    disposable_context_engine: Engine,
) -> None:
    spa_id, revision_id = _create_spa(disposable_context_engine)
    try:
        with Session(disposable_context_engine) as session:
            repository = RealtimeContextRepository(session)
            with pytest.raises(ValueError):
                repository.provision_reference_settings(
                    spa_id=spa_id,
                    pipeline_code=PipelineCode.OPENCV_SFACE,
                    reference_threshold=math.nan,
                    min_query_face_quality=0.4,
                    quality_settings={},
                )
            with pytest.raises(ValueError):
                repository.provision_reference_settings(
                    spa_id=spa_id,
                    pipeline_code=PipelineCode.OPENCV_SFACE,
                    reference_threshold=0.7,
                    min_query_face_quality=0.4,
                    quality_settings={str(index): index for index in range(17)},
                )
            repository.provision_reference_settings(
                spa_id=spa_id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
                reference_threshold=0.7,
                min_query_face_quality=0.4,
                quality_settings={},
            )
            session.commit()
            with pytest.raises(ValueError):
                repository.update_reference_settings(
                    spa_id=spa_id,
                    pipeline_code=PipelineCode.OPENCV_SFACE,
                    reference_threshold=0.91,
                    min_query_face_quality=0.77,
                    quality_settings={"invalid": object()},
                )
            session.commit()
            unchanged = repository.get_reference_settings(
                spa_id=spa_id, pipeline_code=PipelineCode.OPENCV_SFACE
            )
            from face_moment.serving_control.ingest_target import Spa

            unchanged_spa = session.get(Spa, spa_id)
            assert unchanged.reference_threshold == 0.7
            assert unchanged.min_query_face_quality == 0.4
            assert unchanged_spa is not None
            assert unchanged_spa.settings_revision == 2
            with pytest.raises(ValueError):
                repository.update_reference_settings(
                    spa_id=spa_id,
                    pipeline_code=PipelineCode.OPENCV_SFACE,
                    reference_threshold=0.91,
                    min_query_face_quality=0.77,
                    quality_settings={},
                    now=datetime(2026, 8, 16, 0, 3),
                )
            session.commit()
            unchanged_after_timestamp = repository.get_reference_settings(
                spa_id=spa_id, pipeline_code=PipelineCode.OPENCV_SFACE
            )
            unchanged_spa_after_timestamp = session.get(Spa, spa_id)
            assert unchanged_after_timestamp.reference_threshold == 0.7
            assert unchanged_after_timestamp.min_query_face_quality == 0.4
            assert unchanged_spa_after_timestamp is not None
            assert unchanged_spa_after_timestamp.settings_revision == 2
            with pytest.raises(ValueError):
                repository.update_active_visit_date(
                    spa_id=spa_id,
                    active_visit_date=datetime(2026, 8, 16, 0, 4),
                    now=datetime(2026, 8, 16, 0, 4),
                )
            session.commit()
            unchanged_spa_after_date = session.get(Spa, spa_id)
            assert unchanged_spa_after_date is not None
            assert unchanged_spa_after_date.active_visit_date is None
            assert unchanged_spa_after_date.settings_revision == 2
            with pytest.raises(ValueError):
                repository.update_active_visit_date(
                    spa_id=spa_id,
                    active_visit_date=date(2026, 8, 16),
                    now=datetime(2026, 8, 16, 0, 5),
                )
            session.commit()
            unchanged_spa_after_date_timestamp = session.get(Spa, spa_id)
            assert unchanged_spa_after_date_timestamp is not None
            assert unchanged_spa_after_date_timestamp.active_visit_date is None
            assert unchanged_spa_after_date_timestamp.settings_revision == 2
            with pytest.raises(ReferenceSearchSettingsAlreadyExistsError):
                repository.provision_reference_settings(
                    spa_id=spa_id,
                    pipeline_code=PipelineCode.OPENCV_SFACE,
                    reference_threshold=0.7,
                    min_query_face_quality=0.4,
                    quality_settings={},
                )
            with pytest.raises(ReferenceSearchSettingsNotFoundError):
                repository.update_reference_settings(
                    spa_id=spa_id,
                    pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
                    reference_threshold=0.7,
                    min_query_face_quality=0.4,
                    quality_settings={},
                )
    finally:
        _cleanup(disposable_context_engine, spa_id, revision_id)


def test_realtime_context_migration_round_trip(
    disposable_context_engine: Engine,
) -> None:
    alembic_config = Config("alembic.ini")
    alembic_command.downgrade(alembic_config, "0010_display_clients")
    assert "reference_search_settings" not in inspect(
        disposable_context_engine
    ).get_table_names(schema=APP_SCHEMA)
    alembic_command.upgrade(alembic_config, "head")
    assert "reference_search_settings" in inspect(
        disposable_context_engine
    ).get_table_names(schema=APP_SCHEMA)

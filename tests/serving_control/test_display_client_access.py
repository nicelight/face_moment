from __future__ import annotations

from datetime import datetime, timezone
import importlib
import uuid
from collections.abc import Iterator

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
    DisplayClientRepository,
    IngestTargetRepository,
    hash_display_client_token,
)
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


def _migration_to_head(engine: Engine) -> None:
    config = Config("alembic.ini")
    alembic_command.downgrade(config, "0009_photo_admission_lineage")
    assert "display_clients" not in inspect(engine).get_table_names(schema=APP_SCHEMA)
    alembic_command.upgrade(config, "head")
    assert "display_clients" in inspect(engine).get_table_names(schema=APP_SCHEMA)


@pytest.fixture
def disposable_display_client_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Engine]:
    base_settings = Settings.from_env()
    probe_database = f"task041_{uuid.uuid4().hex}"
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


def test_display_client_credentials_have_owner_lifecycle_and_restart_persistence(
    disposable_display_client_engine: Engine,
) -> None:
    serving_control = importlib.import_module("face_moment.serving_control")
    assert hasattr(serving_control, "DisplayClientRepository")

    engine = disposable_display_client_engine
    marker = uuid.uuid4().hex
    spa_id: uuid.UUID | None = None
    revision_id: uuid.UUID | None = None
    display_client_id: uuid.UUID | None = None
    first_token: str | None = None
    reset_token: str | None = None
    try:
        _migration_to_head(engine)
        provisioned_at = datetime(2026, 8, 16, 0, 0, tzinfo=timezone.utc)
        reset_at = datetime(2026, 8, 16, 0, 1, tzinfo=timezone.utc)
        deactivate_at = datetime(2026, 8, 16, 0, 2, tzinfo=timezone.utc)

        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=provisioned_at,
                **PIPELINE_COMPATIBILITY,
            )
            revision_id = revision.id
            target = IngestTargetRepository(session).configure_spa(
                name=f"task041-spa-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            spa_id = target.spa_id
            client = DisplayClientRepository(session).provision(
                spa_id=spa_id,
                name=f"task041-kiosk-{marker}",
                now=provisioned_at,
            )
            display_client_id = client.id
            first_token = client.token_value
            assert len(first_token) >= 43
            assert len(client.token_hash_sha256) == 32
            assert client.token_hash_sha256 == hash_display_client_token(first_token)
            assert client.active is True
            assert client.deactivated_at is None
            session.commit()

        with Session(engine) as session:
            client = DisplayClientRepository(session).reset(
                display_client_id=display_client_id,
                now=reset_at,
            )
            reset_token = client.token_value
            assert reset_token != first_token
            assert client.token_hash_sha256 == hash_display_client_token(reset_token)
            assert client.active is True
            assert client.rotated_at == reset_at
            assert client.deactivated_at is None
            session.commit()

        with Session(engine) as session:
            repository = DisplayClientRepository(session)
            client = repository.deactivate(
                display_client_id=display_client_id,
                now=deactivate_at,
            )
            deactivated_at = client.deactivated_at
            assert client.active is False
            assert deactivated_at == deactivate_at
            assert client.token_value == reset_token
            assert client.token_hash_sha256 == hash_display_client_token(reset_token)
            session.commit()

        with Session(engine) as session:
            client = DisplayClientRepository(session).deactivate(
                display_client_id=display_client_id,
                now=datetime(2026, 8, 16, 0, 3, tzinfo=timezone.utc),
            )
            assert client.active is False
            assert client.deactivated_at == deactivate_at
            session.commit()

        restarted_engine = create_engine(engine.url, pool_pre_ping=True)
        try:
            with Session(restarted_engine) as session:
                client = DisplayClientRepository(session).get(display_client_id)
                assert client.token_value == reset_token
                assert client.token_hash_sha256 == hash_display_client_token(reset_token)
                assert client.active is False
                assert client.deactivated_at == deactivate_at
                assert repr(client).find(reset_token) == -1
        finally:
            restarted_engine.dispose()
    finally:
        if display_client_id is not None:
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM face_moment.display_clients WHERE id = :id"),
                    {"id": display_client_id},
                )
        if spa_id is not None:
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM face_moment.spas WHERE id = :id"),
                    {"id": spa_id},
                )
        if revision_id is not None:
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM face_moment.pipeline_revisions WHERE id = :id"),
                    {"id": revision_id},
                )

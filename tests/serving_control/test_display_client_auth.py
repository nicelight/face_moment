from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, fields
from datetime import datetime, timezone
import hashlib
import logging
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control import (
    DisplayClientRateLimitError,
    DisplayClientRateLimiter,
    DisplayClientPrincipal,
    DisplayClientRepository,
    InvalidDisplayClientCredentials,
    authenticate_display_client,
)
from face_moment.serving_control.ingest_target import IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@dataclass(frozen=True, slots=True)
class _AuthFixture:
    engine: Engine
    active_client_id: uuid.UUID
    active_spa_id: uuid.UUID
    active_token: str
    second_token: str
    reset_old_token: str
    inactive_token: str


@pytest.fixture
def display_auth_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[_AuthFixture]:
    base_settings = Settings.from_env()
    database_name = f"task057_{uuid.uuid4().hex}"
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
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc),
                **PIPELINE_COMPATIBILITY,
            )
            active_target = IngestTargetRepository(session).configure_spa(
                name=f"task057-spa-{database_name}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            active_client = DisplayClientRepository(session).provision(
                spa_id=active_target.spa_id,
                name=f"task057-active-{database_name}",
                now=datetime(2026, 8, 16, 10, 1, tzinfo=timezone.utc),
            )
            second_client = DisplayClientRepository(session).provision(
                spa_id=active_target.spa_id,
                name=f"task057-second-{database_name}",
                now=datetime(2026, 8, 16, 10, 2, tzinfo=timezone.utc),
            )
            reset_client = DisplayClientRepository(session).provision(
                spa_id=active_target.spa_id,
                name=f"task057-reset-{database_name}",
                now=datetime(2026, 8, 16, 10, 3, tzinfo=timezone.utc),
            )
            reset_old_token = reset_client.token_value
            DisplayClientRepository(session).reset(
                display_client_id=reset_client.id,
                now=datetime(2026, 8, 16, 10, 4, tzinfo=timezone.utc),
            )
            inactive_client = DisplayClientRepository(session).provision(
                spa_id=active_target.spa_id,
                name=f"task057-inactive-{database_name}",
                now=datetime(2026, 8, 16, 10, 5, tzinfo=timezone.utc),
            )
            inactive_token = inactive_client.token_value
            DisplayClientRepository(session).deactivate(
                display_client_id=inactive_client.id,
                now=datetime(2026, 8, 16, 10, 6, tzinfo=timezone.utc),
            )
            session.commit()
            fixture = _AuthFixture(
                engine=engine,
                active_client_id=active_client.id,
                active_spa_id=active_target.spa_id,
                active_token=active_client.token_value,
                second_token=second_client.token_value,
                reset_old_token=reset_old_token,
                inactive_token=inactive_token,
            )
        yield fixture
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(
                text(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)")
            )
        admin_engine.dispose()


def _authenticate(
    fixture: _AuthFixture,
    *,
    authorization: str | None,
    ip_address: str = "198.18.0.10",
    limiter: DisplayClientRateLimiter | None = None,
    now: datetime | None = None,
) -> DisplayClientPrincipal:
    selected_limiter = limiter or DisplayClientRateLimiter(
        limit=100, window_seconds=60
    )
    with Session(fixture.engine) as session:
        return authenticate_display_client(
            session,
            authorization=authorization,
            ip_address=ip_address,
            rate_limiter=selected_limiter,
            now=now or datetime(2026, 8, 16, 11, 0, tzinfo=timezone.utc),
        )


def test_active_token_returns_only_authoritative_principal(
    display_auth_fixture: _AuthFixture,
) -> None:
    fixture = display_auth_fixture

    principal = _authenticate(
        fixture,
        authorization=f"Bearer {fixture.active_token}",
    )

    assert principal.display_client_id == fixture.active_client_id
    assert principal.spa_id == fixture.active_spa_id
    assert {field.name for field in fields(principal)} == {
        "display_client_id",
        "spa_id",
    }
    assert not hasattr(principal, "token_value")
    assert not hasattr(principal, "token_hash_sha256")


@pytest.mark.parametrize(
    "authorization_name",
    ("missing", "malformed", "unknown", "reset", "inactive"),
)
def test_invalid_credential_states_are_uniform(
    display_auth_fixture: _AuthFixture,
    authorization_name: str,
) -> None:
    fixture = display_auth_fixture
    authorization = {
        "missing": None,
        "malformed": "Basic not-a-bearer",
        "unknown": "Bearer unknown-display-token",
        "reset": f"Bearer {fixture.reset_old_token}",
        "inactive": f"Bearer {fixture.inactive_token}",
    }[authorization_name]

    with pytest.raises(InvalidDisplayClientCredentials) as error:
        _authenticate(fixture, authorization=authorization)

    assert str(error.value) == ""


def test_token_and_ip_limits_are_positive_and_deterministic(
    display_auth_fixture: _AuthFixture,
) -> None:
    fixture = display_auth_fixture
    limiter = DisplayClientRateLimiter(limit=2, window_seconds=60)
    first = datetime(2026, 8, 16, 11, 0, tzinfo=timezone.utc)

    for offset in (0, 1):
        principal = _authenticate(
            fixture,
            authorization=f"Bearer {fixture.active_token}",
            limiter=limiter,
            now=first.replace(second=offset),
        )
        assert principal.spa_id == fixture.active_spa_id
    with pytest.raises(DisplayClientRateLimitError):
        _authenticate(
            fixture,
            authorization=f"Bearer {fixture.active_token}",
            limiter=limiter,
            now=first.replace(second=2),
        )

    with pytest.raises(DisplayClientRateLimitError):
        _authenticate(
            fixture,
            authorization=f"Bearer {fixture.second_token}",
            limiter=limiter,
            ip_address="198.18.0.10",
            now=first.replace(second=3),
        )


def test_authentication_does_not_log_credential_material(
    display_auth_fixture: _AuthFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fixture = display_auth_fixture
    authorization = f"Bearer {fixture.active_token}"
    digest = hashlib.sha256(fixture.active_token.encode("ascii")).hexdigest()
    caplog.set_level(logging.DEBUG)

    _authenticate(fixture, authorization=authorization)
    with pytest.raises(InvalidDisplayClientCredentials):
        _authenticate(fixture, authorization="Bearer definitely-unknown")

    assert authorization not in caplog.text
    assert fixture.active_token not in caplog.text
    assert digest not in caplog.text
    assert "198.18.0.10" not in caplog.text

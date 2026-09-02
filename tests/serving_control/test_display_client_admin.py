from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.platform.auth.sessions import (
    LoginRateLimiter,
    create_browser_session,
)
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control import DisplayClientRepository, IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@dataclass(frozen=True, slots=True)
class _AdminFixture:
    app: FastAPI
    engine: Engine
    database_url: str
    display_clients: tuple[tuple[uuid.UUID, str, uuid.UUID, bool, str], ...]
    operator_cookies: dict[str, str]
    developer_cookies: dict[str, str]
    photographer_cookies: dict[str, str]


def test_admin_page_has_exact_same_origin_edge_handler() -> None:
    caddyfile = Path("deploy/Caddyfile").read_text()

    assert (
        "\t\thandle /staff/display-clients {\n"
        "\t\t\treverse_proxy backend:8000 {\n"
        "\t\t\t\theader_up X-Forwarded-For {remote_host}\n"
        "\t\t\t}\n"
        "\t\t}"
    ) in caddyfile
    assert "handle_path /staff/display-clients" not in caddyfile


@pytest.fixture
def display_client_admin_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_AdminFixture]:
    base_settings = Settings.from_env()
    database_name = f"task058_{uuid.uuid4().hex}"
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
            first_target = IngestTargetRepository(session).configure_spa(
                name=f"task058-spa-a-{database_name}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            second_target = IngestTargetRepository(session).configure_spa(
                name=f"task058-spa-b-{database_name}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            first_client = DisplayClientRepository(session).provision(
                spa_id=first_target.spa_id,
                name=f"task058-kiosk-a-{database_name}",
                now=datetime(2026, 8, 16, 10, 1, tzinfo=timezone.utc),
            )
            second_client = DisplayClientRepository(session).provision(
                spa_id=second_target.spa_id,
                name=f"task058-kiosk-b-{database_name}",
                now=datetime(2026, 8, 16, 10, 2, tzinfo=timezone.utc),
            )
            DisplayClientRepository(session).deactivate(
                display_client_id=second_client.id,
                now=datetime(2026, 8, 16, 10, 3, tzinfo=timezone.utc),
            )
            display_clients = (
                (
                    first_client.id,
                    first_client.name,
                    first_client.spa_id,
                    first_client.active,
                    first_client.token_value,
                ),
                (
                    second_client.id,
                    second_client.name,
                    second_client.spa_id,
                    False,
                    second_client.token_value,
                ),
            )
            accounts = {
                "operator": StaffRole.OPERATOR,
                "developer": StaffRole.DEVELOPER,
                "photographer": StaffRole.PHOTOGRAPHER,
            }
            cookies: dict[str, dict[str, str]] = {}
            for account_name, role in accounts.items():
                username = f"task058-{account_name}-{database_name}"
                password = f"task058-password-{database_name}"
                provision_staff_user(
                    session,
                    username=username,
                    password=password,
                    role=role,
                )
                browser_session = create_browser_session(
                    session,
                    username=username,
                    password=password,
                    ip_address="198.18.0.58",
                    ttl_seconds=3600,
                    limiter=LoginRateLimiter(limit=20, window_seconds=60),
                )
                cookies[account_name] = {
                    "fm_staff_session": browser_session.session_token,
                }

        app = create_app()
        app.state.role_state["session_factory"] = lambda: Session(engine)
        yield _AdminFixture(
            app=app,
            engine=engine,
            database_url=probe_url.render_as_string(hide_password=False),
            display_clients=display_clients,
            operator_cookies=cookies["operator"],
            developer_cookies=cookies["developer"],
            photographer_cookies=cookies["photographer"],
        )
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(
                text(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)")
            )
        admin_engine.dispose()


def test_admin_page_lists_current_tokens_and_survives_reload_and_restart(
    display_client_admin_fixture: _AdminFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fixture = display_client_admin_fixture
    status, headers, first_body = _get_page(
        fixture.app,
        cookies=fixture.operator_cookies,
    )

    assert status == 200
    assert headers["cache-control"] == "no-store"
    assert '<h1>Display client settings</h1>' in first_body
    assert "token_hash_sha256" not in first_body
    for display_client_id, name, spa_id, active, token in fixture.display_clients:
        assert str(display_client_id) in first_body
        assert name in first_body
        assert str(spa_id) in first_body
        assert f'data-field="active">{str(active).lower()}</td>' in first_body
        assert token in first_body

    fixture.engine.dispose()
    restarted_engine = create_engine(fixture.database_url, pool_pre_ping=True)
    try:
        with restarted_engine.connect() as connection:
            persisted_tokens = tuple(
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT token_value FROM face_moment.display_clients "
                        "ORDER BY name, id"
                    )
                )
            )
        assert persisted_tokens == tuple(client[4] for client in fixture.display_clients)
    finally:
        restarted_engine.dispose()

    status, second_headers, second_body = _get_page(
        fixture.app,
        cookies=fixture.operator_cookies,
    )
    assert status == 200
    assert second_headers["cache-control"] == "no-store"
    assert second_body == first_body

    developer_status, _, developer_body = _get_page(
        fixture.app,
        cookies=fixture.developer_cookies,
    )
    assert developer_status == 200
    assert developer_body == first_body
    assert caplog.text == ""


def test_admin_page_rejects_invalid_staff_and_photographer_without_tokens(
    display_client_admin_fixture: _AdminFixture,
) -> None:
    fixture = display_client_admin_fixture
    tokens = tuple(client[4] for client in fixture.display_clients)

    for cookies in (None, {"fm_staff_session": "invalid-task058-session"}):
        status, _, body = _get_page(fixture.app, cookies=cookies)
        assert status == 401
        assert all(token not in body for token in tokens)

    status, _, body = _get_page(
        fixture.app,
        cookies=fixture.photographer_cookies,
    )
    assert status == 403
    assert all(token not in body for token in tokens)


def _get_page(
    app: FastAPI,
    *,
    cookies: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], str]:
    request_headers = [(b"host", b"testserver")]
    if cookies:
        request_headers.append(
            (
                b"cookie",
                "; ".join(f"{name}={value}" for name, value in cookies.items()).encode(),
            )
        )
    messages: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, object]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "https",
                "path": "/staff/display-clients",
                "raw_path": b"/staff/display-clients",
                "query_string": b"",
                "headers": request_headers,
                "client": ("127.0.0.1", 51515),
                "server": ("testserver", 443),
            },
            receive,
            send,
        )
    )
    start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    response_headers = {
        name.decode().lower(): value.decode()
        for name, value in start["headers"]
    }
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return int(start["status"]), response_headers, response_body.decode()

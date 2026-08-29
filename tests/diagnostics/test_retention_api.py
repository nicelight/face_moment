from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import datetime, timezone
import uuid
from typing import Any

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.platform.auth.sessions import LoginRateLimiter, create_browser_session
from face_moment.promo.retention import RetentionCleanupLatest


@pytest.fixture
def disposable_retention_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[FastAPI, Engine, dict[str, str], dict[str, str], dict[str, str]]]:
    base_settings = Settings.from_env()
    probe_database = f"task086api_{uuid.uuid4().hex}"
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
    marker = uuid.uuid4().hex
    password = f"task086-password-{marker}"
    credentials = {
        role: {
            "username": f"task086-{role}-{marker}",
            "password": password,
        }
        for role in ("operator", "developer", "photographer")
    }
    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        with Session(engine) as session:
            for role_name, role in (
                ("operator", StaffRole.OPERATOR),
                ("developer", StaffRole.DEVELOPER),
                ("photographer", StaffRole.PHOTOGRAPHER),
            ):
                provision_staff_user(
                    session,
                    username=credentials[role_name]["username"],
                    password=password,
                    role=role,
                )

        app = create_app()
        yield (
            app,
            engine,
            _login_token(engine, credentials["operator"]),
            _login_token(engine, credentials["developer"]),
            _login_token(engine, credentials["photographer"]),
        )
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)"
            )
        admin_engine.dispose()


def test_retention_read_is_role_limited_no_store_and_never_run(
    disposable_retention_api: tuple[
        FastAPI, Engine, dict[str, str], dict[str, str], dict[str, str]
    ],
) -> None:
    app, _engine, operator, developer, photographer = disposable_retention_api
    for cookies in (operator, developer):
        status, headers, body = _request(
            app, "GET", "/api/diagnostics/retention", cookies=cookies
        )
        assert status == 200
        assert body == {"schema_version": 1, "status": "never_run", "result": None}
        assert headers["cache-control"] == "no-store"

    status, headers, _ = _request(
        app, "GET", "/api/diagnostics/retention", cookies=photographer
    )
    assert status == 403
    assert headers["cache-control"] == "no-store"
    status, headers, _ = _request(app, "GET", "/api/diagnostics/retention")
    assert status == 401
    assert headers["cache-control"] == "no-store"


def test_retention_read_projects_one_sanitized_latest_result_and_html(
    disposable_retention_api: tuple[
        FastAPI, Engine, dict[str, str], dict[str, str], dict[str, str]
    ],
) -> None:
    app, engine, operator, _developer, _photographer = disposable_retention_api
    started = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(
            RetentionCleanupLatest(
                singleton_key=1,
                run_id=uuid.uuid4(),
                status="failed",
                started_at=started,
                finished_at=started,
                technical_logs_before=started,
                attempts_and_evidence_before=started,
                error="owner cleanup failed",
            )
        )
        session.commit()

    status, headers, body = _request(
        app, "GET", "/api/diagnostics/retention", cookies=operator
    )
    assert status == 200
    assert headers["cache-control"] == "no-store"
    assert body["status"] == "available"
    assert body["result"]["state"] == "failed"
    assert body["result"]["error"] == "owner cleanup failed"
    assert "traceback" not in json.dumps(body).casefold()
    assert "participant" not in json.dumps(body).casefold()

    status, headers, raw_body = _raw_request(
        app, "GET", "/staff/diagnostics-retention", cookies=operator
    )
    assert status == 200
    assert headers["cache-control"] == "no-store"
    assert "Diagnostics retention" in raw_body
    assert "owner cleanup failed" in raw_body


def _login_token(engine: Engine, credentials: dict[str, str]) -> dict[str, str]:
    with Session(engine) as session:
        browser_session = create_browser_session(
            session,
            username=credentials["username"],
            password=credentials["password"],
            ip_address="127.0.0.1",
            ttl_seconds=3600,
            limiter=LoginRateLimiter(limit=10, window_seconds=60),
        )
        return {"fm_staff_session": browser_session.session_token}


def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    cookies: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    status, headers, body = _raw_request(app, method, path, cookies=cookies)
    return status, headers, json.loads(body or "{}")


def _raw_request(
    app: FastAPI,
    method: str,
    path: str,
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

    async def receive() -> dict[str, Any]:
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
                "method": method,
                "scheme": "https",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": request_headers,
                "client": ("127.0.0.1", 51515),
                "server": ("testserver", 443),
            },
            receive,
            send,
        )
    )
    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    headers = {
        name.decode().lower(): value.decode()
        for name, value in start["headers"]
    }
    return start["status"], headers, response_body.decode()

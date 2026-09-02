from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.principals import StaffRole, provision_staff_user


@pytest.fixture
def disposable_staff_session_state(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[FastAPI, str, str, str]:
    base_settings = Settings.from_env()
    probe_database = f"task004_{uuid.uuid4().hex}"
    probe_url = make_url(base_settings.database_url).set(database=probe_database)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {probe_database}"))
    monkeypatch.setenv("DATABASE_URL", probe_url.render_as_string(hide_password=False))
    monkeypatch.setenv("STAFF_SESSION_TTL_SECONDS", "60")
    monkeypatch.setenv("STAFF_LOGIN_RATE_LIMIT", "2")
    monkeypatch.setenv("STAFF_LOGIN_RATE_WINDOW_SECONDS", "60")
    settings = Settings.from_env()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    username = f"task004-{uuid.uuid4().hex}"
    password = f"task004-password-{uuid.uuid4().hex}"
    rate_username = f"task004-rate-{uuid.uuid4().hex}"

    try:
        alembic_config = Config("alembic.ini")
        alembic_command.upgrade(alembic_config, "head")
        assert "staff_sessions" in inspect(engine).get_table_names(
            schema="face_moment"
        )
        alembic_command.downgrade(alembic_config, "0003_pipeline_revisions")
        assert "staff_sessions" not in inspect(engine).get_table_names(
            schema="face_moment"
        )
        alembic_command.upgrade(alembic_config, "head")
        with Session(engine) as database_session:
            provision_staff_user(
                database_session,
                username=username,
                password=password,
                role=StaffRole.PHOTOGRAPHER,
            )
        app = create_app()
        app.state.role_state["session_factory"] = lambda: Session(engine)
        yield app, username, password, rate_username
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)"))
        admin_engine.dispose()


def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    body: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, list[str], dict[str, Any]]:
    raw_body = b"" if body is None else json.dumps(body).encode()
    request_headers = [(b"host", b"testserver")]
    if body is not None:
        request_headers.append((b"content-type", b"application/json"))
    if cookies:
        request_headers.append(
            (
                b"cookie",
                "; ".join(f"{name}={value}" for name, value in cookies.items()).encode(),
            )
        )
    if headers:
        request_headers.extend(
            (name.lower().encode(), value.encode()) for name, value in headers.items()
        )
    messages: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": raw_body, "more_body": False}

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
    set_cookies = [
        value.decode()
        for name, value in start["headers"]
        if name.lower() == b"set-cookie"
    ]
    return start["status"], set_cookies, json.loads(response_body or b"{}")


def _set_cookies(cookies: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for header in cookies:
        parsed = SimpleCookie()
        parsed.load(header)
        values.update({name: morsel.value for name, morsel in parsed.items()})
    return values


def test_staff_session_root_paths_preserve_https_edge_routing() -> None:
    caddyfile = Path("deploy/Caddyfile").read_text()

    assert (
        "\thandle /api/staff/* {\n"
        "\t\treverse_proxy backend:8000 {\n"
        "\t\t\theader_up X-Forwarded-For {remote_host}\n"
        "\t\t}\n"
        "\t}"
    ) in caddyfile
    assert (
        "\thandle /staff/login {\n"
        "\t\treverse_proxy backend:8000 {\n"
        "\t\t\theader_up X-Forwarded-For {remote_host}\n"
        "\t\t}\n"
        "\t}"
    ) in caddyfile
    assert "handle_path /api/staff/" not in caddyfile
    assert "handle_path /staff/login" not in caddyfile


def test_login_limit_separates_caddy_forwarded_clients(
    disposable_staff_session_state: tuple[FastAPI, str, str, str],
) -> None:
    app, _, _, rate_username = disposable_staff_session_state

    def failed_login(originating_ip: str) -> int:
        return _request(
            app,
            "POST",
            "/api/staff/sessions",
            body={"username": rate_username, "password": "wrong-password"},
            headers={"X-Forwarded-For": originating_ip},
        )[0]

    assert failed_login("198.18.0.10") == 401
    assert failed_login("198.18.0.10") == 401
    assert failed_login("198.18.0.11") == 401
    assert failed_login("198.18.0.10") == 429


def test_staff_browser_session_contract(
    disposable_staff_session_state: tuple[FastAPI, str, str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, username, password, rate_username = disposable_staff_session_state

    login_status, set_cookies, _ = _request(
        app,
        "POST",
        "/api/staff/sessions",
        body={"username": f"  {username.upper()}  ", "password": password},
    )
    assert login_status == 204

    assert len(set_cookies) == 2
    session_cookie = next(
        cookie for cookie in set_cookies if cookie.startswith("fm_staff_session=")
    )
    csrf_cookie = next(
        cookie for cookie in set_cookies if cookie.startswith("fm_staff_csrf=")
    )
    for cookie in (session_cookie, csrf_cookie):
        assert "Path=/" in cookie
        assert "Secure" in cookie
        assert "SameSite=lax" in cookie
        assert "Max-Age=60" in cookie
        assert "expires=" in cookie.lower()
    assert "HttpOnly" in session_cookie
    assert "HttpOnly" not in csrf_cookie

    cookie_values = _set_cookies(set_cookies)
    session_token = cookie_values["fm_staff_session"]
    csrf_token = cookie_values["fm_staff_csrf"]
    assert session_token != csrf_token

    current_status, _, current_body = _request(
        app, "GET", "/api/staff/session", cookies=cookie_values
    )
    assert current_status == 200
    assert current_body == {
        "staff_user_id": current_body["staff_user_id"],
        "username": username,
        "role": "photographer",
    }

    settings = Settings.from_env()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            session_row = (
                connection.execute(
                    text(
                        "SELECT token_hash_sha256, csrf_token_hash_sha256 "
                        "FROM face_moment.staff_sessions "
                        "WHERE staff_user_id = ("
                        "SELECT id FROM face_moment.staff_users "
                        "WHERE username = :username)"
                    ),
                    {"username": username},
                )
                .mappings()
                .one()
            )
        assert len(session_row["token_hash_sha256"]) == 32
        assert len(session_row["csrf_token_hash_sha256"]) == 32
        assert session_token.encode() != session_row["token_hash_sha256"]
        assert csrf_token.encode() != session_row["csrf_token_hash_sha256"]

        assert _request(
            app, "DELETE", "/api/staff/session", cookies=cookie_values
        )[0] == 403
        assert _request(
            app,
            "DELETE",
            "/api/staff/session",
            cookies={"fm_staff_session": session_token},
            headers={"X-CSRF-Token": csrf_token},
        )[0] == 403
        assert _request(
            app,
            "DELETE",
            "/api/staff/session",
            cookies=cookie_values,
            headers={"X-CSRF-Token": "mismatched"},
        )[0] == 403
        logout_status, logout_cookies, _ = _request(
            app,
            "DELETE",
            "/api/staff/session",
            cookies=cookie_values,
            headers={"X-CSRF-Token": csrf_token},
        )
        assert logout_status == 204
        assert len(logout_cookies) == 2
        assert _request(app, "GET", "/api/staff/session", cookies=cookie_values)[0] == 401
        assert _request(app, "DELETE", "/api/staff/session", cookies=cookie_values)[0] == 401

        restarted_app = create_app()
        restarted_app.state.role_state["session_factory"] = lambda: Session(engine)
        assert _request(
            restarted_app,
            "GET",
            "/api/staff/session",
            cookies={"fm_staff_session": "malformed"},
        )[0] == 401

        for expected_status in (401, 401, 429):
            response_status, _, _ = _request(
                app,
                "POST",
                "/api/staff/sessions",
                body={"username": rate_username, "password": "wrong-password"},
            )
            assert response_status == expected_status

        second_login_status, second_set_cookies, _ = _request(
            app,
            "POST",
            "/api/staff/sessions",
            body={"username": username, "password": password},
        )
        assert second_login_status == 204
        second_cookie_values = _set_cookies(second_set_cookies)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE face_moment.staff_sessions SET expires_at = :expired "
                    "WHERE token_hash_sha256 = ("
                    "SELECT token_hash_sha256 FROM face_moment.staff_sessions "
                    "ORDER BY created_at DESC LIMIT 1)"
                ),
                {"expired": datetime.now(timezone.utc) - timedelta(seconds=1)},
            )
        assert _request(
            app, "GET", "/api/staff/session", cookies=second_cookie_values
        )[0] == 401
    finally:
        engine.dispose()

    retained_logs = caplog.text
    for protected_marker in (password, session_token, csrf_token):
        assert protected_marker not in retained_logs

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import threading
import uuid
from collections.abc import Generator
from http.cookies import SimpleCookie
from typing import Any

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.platform.auth.sessions import (
    InvalidCredentialsError,
    InvalidSessionError,
    LoginRateLimiter,
    create_browser_session,
    get_current_principal,
    reset_staff_password_and_revoke_sessions,
)


@pytest.fixture
def disposable_credential_lifecycle_state(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[FastAPI, Engine, str, str], None, None]:
    base_settings = Settings.from_env()
    probe_database = f"task005_{uuid.uuid4().hex}"
    probe_url = make_url(base_settings.database_url).set(database=probe_database)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {probe_database}"))
    monkeypatch.setenv("DATABASE_URL", probe_url.render_as_string(hide_password=False))
    monkeypatch.setenv("STAFF_LOGIN_RATE_LIMIT", "20")
    settings = Settings.from_env()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    username = f"task005-{uuid.uuid4().hex}"
    password = f"task005-password-{uuid.uuid4().hex}"

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        assert "staff_users" in inspect(engine).get_table_names(schema="face_moment")
        with Session(engine) as database_session:
            provision_staff_user(
                database_session,
                username=username,
                password=password,
                role=StaffRole.PHOTOGRAPHER,
            )
        yield create_app(), engine, username, password
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


def _login(app: FastAPI, username: str, password: str) -> dict[str, str]:
    status_code, set_cookies, _ = _request(
        app,
        "POST",
        "/api/staff/sessions",
        body={"username": username, "password": password},
    )
    assert status_code == 204
    cookie_values: dict[str, str] = {}
    for header in set_cookies:
        parsed = SimpleCookie()
        parsed.load(header)
        cookie_values.update({name: morsel.value for name, morsel in parsed.items()})
    return cookie_values


def _lifecycle_command(*args: str, password: str | None = None) -> subprocess.CompletedProcess[str]:
    command = shutil.which("face-moment-provision-staff")
    assert command is not None, "the owner-backed staff command is not installed"
    return subprocess.run(
        [command, *args],
        input=None if password is None else f"{password}\n",
        capture_output=True,
        check=False,
        text=True,
    )


def _session_projection(engine: Engine, username: str) -> tuple[dict[str, Any], int]:
    with engine.connect() as connection:
        staff_user = (
            connection.execute(
                text(
                    "SELECT password_hash, active, password_changed_at, deactivated_at "
                    "FROM face_moment.staff_users WHERE username = :username"
                ),
                {"username": username},
            )
            .mappings()
            .one()
        )
        active_sessions = connection.execute(
            text(
                "SELECT count(*) FROM face_moment.staff_sessions "
                "WHERE staff_user_id = (SELECT id FROM face_moment.staff_users "
                "WHERE username = :username) AND revoked_at IS NULL"
            ),
            {"username": username},
        ).scalar_one()
    return dict(staff_user), active_sessions


def test_password_reset_revokes_every_current_session_and_redacts(
    disposable_credential_lifecycle_state: tuple[FastAPI, Engine, str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, engine, username, password = disposable_credential_lifecycle_state
    reset_password = f"task005-reset-{uuid.uuid4().hex}"
    first_session = _login(app, username, password)
    second_session = _login(app, username, password)
    assert _request(app, "GET", "/api/staff/session", cookies=first_session)[0] == 200
    assert _request(app, "GET", "/api/staff/session", cookies=second_session)[0] == 200
    before, active_before = _session_projection(engine, username)
    assert active_before == 2

    reset = _lifecycle_command(
        "--username",
        username,
        "--reset-password",
        "--password-stdin",
        password=reset_password,
    )
    assert reset.returncode == 0, reset.stderr

    assert _request(app, "GET", "/api/staff/session", cookies=first_session)[0] == 401
    assert _request(app, "GET", "/api/staff/session", cookies=second_session)[0] == 401
    assert _request(
        app,
        "POST",
        "/api/staff/sessions",
        body={"username": username, "password": password},
    )[0] == 401
    assert _login(app, username, reset_password)["fm_staff_session"]

    after, active_after = _session_projection(engine, username)
    assert after["active"] is True
    assert after["password_hash"].startswith("$argon2id$")
    assert after["password_hash"] != password
    assert after["password_hash"] != reset_password
    assert after["password_changed_at"] > before["password_changed_at"]
    assert active_after == 1

    retained_output = "\n".join((reset.stdout, reset.stderr, caplog.text))
    for protected_marker in (
        password,
        reset_password,
        first_session["fm_staff_session"],
        first_session["fm_staff_csrf"],
        second_session["fm_staff_session"],
        second_session["fm_staff_csrf"],
        after["password_hash"],
    ):
        assert protected_marker not in retained_output
    print(
        "credential_lifecycle_projection="
        "action=password_reset pre_sessions=2 old_sessions=401 "
        "old_login=401 new_login=204 active=true "
        "password_hash_kind=argon2id redaction=clean"
    )


def test_deactivation_revokes_every_current_session_is_idempotent_and_redacts(
    disposable_credential_lifecycle_state: tuple[FastAPI, Engine, str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, engine, username, password = disposable_credential_lifecycle_state
    first_session = _login(app, username, password)
    second_session = _login(app, username, password)
    assert _request(app, "GET", "/api/staff/session", cookies=first_session)[0] == 200
    assert _request(app, "GET", "/api/staff/session", cookies=second_session)[0] == 200
    before, active_before = _session_projection(engine, username)
    assert active_before == 2

    deactivation = _lifecycle_command("--username", username, "--deactivate")
    assert deactivation.returncode == 0, deactivation.stderr
    after_first, active_after_first = _session_projection(engine, username)

    assert _request(app, "GET", "/api/staff/session", cookies=first_session)[0] == 401
    assert _request(app, "GET", "/api/staff/session", cookies=second_session)[0] == 401
    assert _request(
        app,
        "POST",
        "/api/staff/sessions",
        body={"username": username, "password": password},
    )[0] == 401
    assert after_first["active"] is False
    assert after_first["deactivated_at"] is not None
    assert active_after_first == 0

    repeated_deactivation = _lifecycle_command("--username", username, "--deactivate")
    assert repeated_deactivation.returncode == 0, repeated_deactivation.stderr
    after_repeat, active_after_repeat = _session_projection(engine, username)
    assert after_repeat["active"] is False
    assert after_repeat["deactivated_at"] == after_first["deactivated_at"]
    assert after_repeat["password_hash"] == before["password_hash"]
    assert active_after_repeat == 0

    retained_output = "\n".join(
        (deactivation.stdout, deactivation.stderr, repeated_deactivation.stdout,
         repeated_deactivation.stderr, caplog.text)
    )
    for protected_marker in (
        password,
        first_session["fm_staff_session"],
        first_session["fm_staff_csrf"],
        second_session["fm_staff_session"],
        second_session["fm_staff_csrf"],
        after_repeat["password_hash"],
    ):
        assert protected_marker not in retained_output
    print(
        "credential_lifecycle_projection="
        "action=deactivation pre_sessions=2 old_sessions=401 inactive_login=401 "
        "repeat=safe active=false password_hash_unchanged=true redaction=clean"
    )


def test_concurrent_old_password_login_cannot_outlive_reset(
    disposable_credential_lifecycle_state: tuple[FastAPI, Engine, str, str],
) -> None:
    _, engine, username, old_password = disposable_credential_lifecycle_state
    new_password = f"task005-reset-{uuid.uuid4().hex}"
    limiter = LoginRateLimiter(limit=20, window_seconds=60)
    with Session(engine) as database_session:
        initial_session = create_browser_session(
            database_session,
            username=username,
            password=old_password,
            ip_address="127.0.0.1",
            ttl_seconds=3600,
            limiter=limiter,
        )

    reset_engine = create_engine(engine.url, pool_pre_ping=True)
    login_engine = create_engine(engine.url, pool_pre_ping=True)
    reset_bulk_done = threading.Event()
    login_principal_query_started = threading.Event()
    allow_reset_commit = threading.Event()
    reset_errors: list[BaseException] = []
    login_result: list[str] = []

    def pause_reset_after_bulk_update(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        normalized = " ".join(statement.casefold().split())
        if normalized.startswith("update face_moment.staff_sessions"):
            reset_bulk_done.set()
            if not allow_reset_commit.wait(20):
                raise TimeoutError("concurrent login did not begin principal lookup")

    def release_reset_for_login_lookup(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        normalized = " ".join(statement.casefold().split())
        if (
            "from face_moment.staff_users" in normalized
            and "face_moment.staff_users.username" in normalized
            and "for update" in normalized
        ):
            login_principal_query_started.set()
            allow_reset_commit.set()

    def release_reset_after_unlocked_lookup(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        normalized = " ".join(statement.casefold().split())
        if (
            "from face_moment.staff_users" in normalized
            and "face_moment.staff_users.username" in normalized
            and "for update" not in normalized
        ):
            login_principal_query_started.set()
            allow_reset_commit.set()

    event.listen(reset_engine, "after_cursor_execute", pause_reset_after_bulk_update)
    event.listen(login_engine, "before_cursor_execute", release_reset_for_login_lookup)
    event.listen(login_engine, "after_cursor_execute", release_reset_after_unlocked_lookup)

    def run_reset() -> None:
        try:
            with Session(reset_engine) as database_session:
                reset_staff_password_and_revoke_sessions(
                    database_session,
                    username=username,
                    password=new_password,
                )
        except BaseException as error:
            reset_errors.append(error)

    def run_old_password_login() -> None:
        with Session(login_engine) as database_session:
            try:
                create_browser_session(
                    database_session,
                    username=username,
                    password=old_password,
                    ip_address="127.0.0.2",
                    ttl_seconds=3600,
                    limiter=limiter,
                )
            except InvalidCredentialsError:
                login_result.append("rejected")
            else:
                login_result.append("accepted")

    reset_thread: threading.Thread | None = None
    login_thread: threading.Thread | None = None
    try:
        reset_thread = threading.Thread(target=run_reset, daemon=True)
        reset_thread.start()
        assert reset_bulk_done.wait(20), "reset did not reach session revocation"

        login_thread = threading.Thread(target=run_old_password_login, daemon=True)
        login_thread.start()
        assert login_principal_query_started.wait(20), "concurrent login did not query principal"
        allow_reset_commit.set()

        reset_thread.join(20)
        login_thread.join(20)
        assert not reset_thread.is_alive()
        assert not login_thread.is_alive()
        assert not reset_errors, reset_errors
        assert login_result == ["rejected"]

        with Session(engine) as database_session:
            with pytest.raises(InvalidSessionError):
                get_current_principal(
                    database_session,
                    session_token=initial_session.session_token,
                )
        with engine.connect() as connection:
            current_sessions = connection.execute(
                text(
                    "SELECT count(*) FROM face_moment.staff_sessions "
                    "WHERE staff_user_id = (SELECT id FROM face_moment.staff_users "
                    "WHERE username = :username) AND revoked_at IS NULL"
                ),
                {"username": username},
            ).scalar_one()
        assert current_sessions == 0
    finally:
        allow_reset_commit.set()
        if reset_thread is not None:
            reset_thread.join(5)
        if login_thread is not None:
            login_thread.join(5)
        reset_engine.dispose()
        login_engine.dispose()

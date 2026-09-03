"""FT-009-AC-001/004 bounded developer server-event search proof."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any
import uuid

from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

import face_moment.diagnostics.http as diagnostics_http
from face_moment.diagnostics.http import register_server_event_search_routes
from face_moment.diagnostics.server_events import (
    EVENT_CATALOG,
    SERVER_EVENT_SEARCH_LIMIT,
    ServerEvent,
    ServerEventCode,
    ServerEventProjection,
)
from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.principals import (
    StaffRole,
    StaffUser,
    provision_staff_user,
)
from face_moment.platform.auth.sessions import (
    BrowserSession,
    LoginRateLimiter,
    create_browser_session,
    revoke_current_browser_session,
)


_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class ServerEventSearchFixture:
    app: FastAPI
    engine: Engine
    cookies: dict[str, dict[str, str]]
    event_ids: dict[str, uuid.UUID]
    attempt_id: uuid.UUID
    correlation_id: uuid.UUID


@pytest.fixture
def disposable_server_event_search(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[ServerEventSearchFixture]:
    base_settings = Settings.from_env()
    database_name = f"task091_{uuid.uuid4().hex}"
    probe_url = make_url(base_settings.database_url).set(database=database_name)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {database_name}")
    monkeypatch.setenv("DATABASE_URL", probe_url.render_as_string(hide_password=False))
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    marker = uuid.uuid4().hex
    password = f"task091-password-{marker}"
    roles = {
        "developer": StaffRole.DEVELOPER,
        "operator": StaffRole.OPERATOR,
        "photographer": StaffRole.PHOTOGRAPHER,
        "revoked": StaffRole.DEVELOPER,
        "downgraded": StaffRole.DEVELOPER,
    }
    usernames = {name: f"task091-{name}-{marker}" for name in roles}
    attempt_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    event_ids: dict[str, uuid.UUID] = {}
    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        with Session(engine) as session:
            for name, role in roles.items():
                provision_staff_user(
                    session,
                    username=usernames[name],
                    password=password,
                    role=role,
                )

            catalog_start = _NOW - timedelta(hours=10)
            catalog_rows: list[ServerEvent] = []
            for index, code in enumerate(EVENT_CATALOG):
                identities = (
                    (None, None)
                    if code
                    in {
                        ServerEventCode.RUNTIME_READINESS_CLOSED,
                        ServerEventCode.QR_SESSION_EXPIRED,
                    }
                    else (
                        attempt_id if code is ServerEventCode.ATTEMPT_FAILED else uuid.uuid4(),
                        correlation_id
                        if code is ServerEventCode.ATTEMPT_FAILED
                        else uuid.uuid4(),
                    )
                )
                event_id = uuid.uuid4()
                event_ids[code.value] = event_id
                catalog_rows.append(
                    _event(
                        event_id=event_id,
                        code=code,
                        occurred_at=catalog_start + timedelta(minutes=index),
                        release_id=(
                            "task091-<not-preescaped>"
                            if code is ServerEventCode.ATTEMPT_FAILED
                            else f"task091-{index}"
                        ),
                        attempt_id=identities[0],
                        correlation_id=identities[1],
                    )
                )

            cap_rows = [
                _event(
                    event_id=uuid.UUID(int=1_000 + index),
                    code=ServerEventCode.QR_SESSION_EXPIRED,
                    occurred_at=_NOW - timedelta(hours=1),
                    release_id=f"cap-{index:03d}",
                )
                for index in range(SERVER_EVENT_SEARCH_LIMIT + 5)
            ]
            event_ids["outside"] = uuid.uuid4()
            outside = _event(
                event_id=event_ids["outside"],
                code=ServerEventCode.RUNTIME_READINESS_CLOSED,
                occurred_at=_NOW - timedelta(hours=25),
                release_id="outside-default-window",
            )
            event_ids["tie-low"] = uuid.UUID(int=10)
            event_ids["tie-high"] = uuid.UUID(int=11)
            tie_rows = [
                _event(
                    event_id=event_ids[name],
                    code=ServerEventCode.QR_SESSION_EXPIRED,
                    occurred_at=_NOW - timedelta(hours=5),
                    release_id=name,
                )
                for name in ("tie-low", "tie-high")
            ]
            session.add_all([*catalog_rows, *cap_rows, outside, *tie_rows])
            session.commit()

            sessions = {
                name: create_browser_session(
                    session,
                    username=username,
                    password=password,
                    ip_address="127.0.0.1",
                    ttl_seconds=3600,
                    limiter=LoginRateLimiter(limit=10, window_seconds=60),
                )
                for name, username in usernames.items()
            }
            revoked = sessions["revoked"]
            revoke_current_browser_session(
                session,
                session_token=revoked.session_token,
                csrf_cookie_token=revoked.csrf_token,
                csrf_header_token=revoked.csrf_token,
            )
            downgraded = session.scalar(
                select(StaffUser).where(StaffUser.username == usernames["downgraded"])
            )
            assert downgraded is not None
            downgraded.role = StaffRole.PHOTOGRAPHER
            session.commit()

        app = FastAPI()
        register_server_event_search_routes(
            app,
            session_factory=lambda: Session(engine),
            utc_now=lambda: _NOW,
        )
        yield ServerEventSearchFixture(
            app=app,
            engine=engine,
            cookies={name: _cookies(value) for name, value in sessions.items()},
            event_ids=event_ids,
            attempt_id=attempt_id,
            correlation_id=correlation_id,
        )
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)"
            )
        admin_engine.dispose()


def test_backend_registers_the_single_exact_route() -> None:
    app = create_app()
    routes = [route for route in app.routes if route.path == "/staff/server-events"]
    assert len(routes) == 1
    assert routes[0].methods == {"GET"}


def test_release_edge_routes_server_event_and_existing_ft008_paths() -> None:
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")
    assert (
        "@staff_diagnostics path /staff/server-events /staff/attempts "
        "/staff/attempts/*"
    ) in caddyfile
    assert (
        "handle @staff_diagnostics {\n"
        "\t\t\treverse_proxy backend:8000 {\n"
        "\t\t\t\theader_up X-Forwarded-For {remote_host}\n"
        "\t\t\t}\n"
        "\t\t}"
    ) in caddyfile


def test_default_and_custom_filters_apply_fixed_projection_order_and_cap(
    disposable_server_event_search: ServerEventSearchFixture,
) -> None:
    fixture = disposable_server_event_search
    status_code, headers, body = _request(
        fixture.app,
        "/staff/server-events",
        cookies=fixture.cookies["developer"],
    )
    assert status_code == 200
    assert headers["cache-control"] == "no-store"
    assert 'id="server-event-search"' in body
    assert _rendered_row_count(body) == SERVER_EVENT_SEARCH_LIMIT
    assert "data-event-id" not in body
    assert "cap-104" in body
    assert "cap-004" not in body
    assert "outside-default-window" not in body
    assert body.index("cap-104") < body.index("cap-103")
    for column in (
        "Event time",
        "Severity",
        "Component",
        "Event code",
        "Release ID",
        "Attempt ID",
        "Correlation ID",
    ):
        assert f"<th>{column}</th>" in body

    target_id = fixture.event_ids[ServerEventCode.ATTEMPT_FAILED.value]
    queries = (
        "from=2026-09-02T01%3A00%3A00Z&to=2026-09-02T03%3A00%3A00Z",
        (
            "from=2026-09-02T01%3A00%3A00%2B00%3A00"
            "&to=2026-09-02T03%3A00%3A00%2B00%3A00"
        ),
        "from=2026-09-02t01%3A00%3A00z&to=2026-09-02t03%3A00%3A00z",
        "severity=error",
        "component=realtime",
        "event_code=attempt.failed",
        f"attempt_id={fixture.attempt_id}",
        f"correlation_id={fixture.correlation_id}",
        (
            "from=2026-09-02T01%3A00%3A00Z&to=2026-09-02T03%3A00%3A00Z"
            f"&severity=error&component=realtime&event_code=attempt.failed"
            f"&attempt_id={fixture.attempt_id}"
            f"&correlation_id={fixture.correlation_id}"
        ),
    )
    for query in queries:
        response_status, response_headers, response_body = _request(
            fixture.app,
            f"/staff/server-events?{query}",
            cookies=fixture.cookies["developer"],
        )
        assert response_status == 200
        assert response_headers["cache-control"] == "no-store"
        assert "task091-&lt;not-preescaped&gt;" in response_body
        assert str(target_id) not in response_body

    tie_status, _tie_headers, tie_body = _request(
        fixture.app,
        (
            "/staff/server-events?from=2026-09-02T06%3A59%3A00Z"
            "&to=2026-09-02T07%3A01%3A00Z"
        ),
        cookies=fixture.cookies["developer"],
    )
    assert tie_status == 200
    assert tie_body.index("tie-high") < tie_body.index("tie-low")
    assert "&lt;not-preescaped&gt;" in _row(
        body=_request(
            fixture.app,
            "/staff/server-events?event_code=attempt.failed",
            cookies=fixture.cookies["developer"],
        )[2],
        release_id="task091-<not-preescaped>",
    )


def test_developer_only_current_authorization_and_no_store(
    disposable_server_event_search: ServerEventSearchFixture,
) -> None:
    fixture = disposable_server_event_search
    cases = (
        (fixture.cookies["developer"], 200),
        (fixture.cookies["operator"], 403),
        (fixture.cookies["photographer"], 403),
        (None, 401),
        (fixture.cookies["revoked"], 401),
        (fixture.cookies["downgraded"], 403),
    )
    for cookies, expected_status in cases:
        status_code, headers, body = _request(
            fixture.app,
            "/staff/server-events?event_code=attempt.failed",
            cookies=cookies,
        )
        assert status_code == expected_status
        assert headers["cache-control"] == "no-store"
        if expected_status != 200:
            assert body == ""
            assert str(fixture.attempt_id) not in body

    for role in ("operator", "photographer", "downgraded"):
        status_code, headers, body = _request(
            fixture.app,
            "/staff/server-events?unknown=value",
            cookies=fixture.cookies[role],
        )
        assert status_code == 403
        assert headers["cache-control"] == "no-store"
        assert body == ""


def test_paired_rows_link_to_ft008_and_uncorrelated_rows_have_no_link_or_promo_read(
    disposable_server_event_search: ServerEventSearchFixture,
) -> None:
    fixture = disposable_server_event_search
    statements: list[str] = []

    def capture_sql(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(fixture.engine, "before_cursor_execute", capture_sql)
    try:
        paired_body = _request(
            fixture.app,
            "/staff/server-events?event_code=attempt.failed",
            cookies=fixture.cookies["developer"],
        )[2]
        uncorrelated_body = _request(
            fixture.app,
            "/staff/server-events?event_code=runtime.readiness_closed",
            cookies=fixture.cookies["developer"],
        )[2]
    finally:
        event.remove(fixture.engine, "before_cursor_execute", capture_sql)

    paired_row = _row(paired_body, release_id="task091-<not-preescaped>")
    assert f'href="/staff/attempts/{fixture.attempt_id}"' in paired_row
    assert str(fixture.correlation_id) in paired_row
    uncorrelated_release = (
        f"task091-{list(EVENT_CATALOG).index(ServerEventCode.RUNTIME_READINESS_CLOSED)}"
    )
    uncorrelated_row = _row(uncorrelated_body, release_id=uncorrelated_release)
    assert "/staff/attempts/" not in uncorrelated_row
    assert "data-event-id" not in paired_row
    assert "data-event-id" not in uncorrelated_row
    assert (
        str(fixture.event_ids[ServerEventCode.ATTEMPT_FAILED.value])
        not in paired_row
    )
    assert (
        str(fixture.event_ids[ServerEventCode.RUNTIME_READINESS_CLOSED.value])
        not in uncorrelated_row
    )
    assert "promo_attempts" not in "\n".join(statements).casefold()
    assert any("server_events" in statement.casefold() for statement in statements)


def test_every_invalid_filter_returns_422_before_event_search(
    disposable_server_event_search: ServerEventSearchFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def forbidden_search(*args: object, **kwargs: object) -> tuple[()]:
        nonlocal calls
        calls += 1
        return ()

    monkeypatch.setattr(diagnostics_http, "search_server_events", forbidden_search)
    queries = (
        "unknown=value",
        "severity=error&severity=warning",
        "from=2026-09-02T01%3A00%3A00Z",
        "to=2026-09-02T02%3A00%3A00Z",
        "from=not-a-time&to=2026-09-02T02%3A00%3A00Z",
        "from=20260902T010000Z&to=2026-09-02T02%3A00%3A00Z",
        "from=2026-W36-3T01%3A00%3A00Z&to=2026-09-02T02%3A00%3A00Z",
        "from=2026-09-02T01%3A00Z&to=2026-09-02T02%3A00%3A00Z",
        "from=2026-09-02%2001%3A00%3A00Z&to=2026-09-02T02%3A00%3A00Z",
        "from=2026-09-02T01%3A00%3A00%2C123Z&to=2026-09-02T02%3A00%3A00Z",
        "from=2026-09-02T01%3A00%3A00%2B0000&to=2026-09-02T02%3A00%3A00Z",
        "from=2026-09-02T01%3A00%3A00-00%3A00&to=2026-09-02T02%3A00%3A00Z",
        "from=2026-09-02T02%3A00%3A00Z&to=2026-09-02T01%3A00%3A00Z",
        "from=2026-08-01T00%3A00%3A00Z&to=2026-09-02T00%3A00%3A00Z",
        "from=2026-09-02T01%3A00%3A00%2B03%3A00&to=2026-09-02T02%3A00%3A00Z",
        "severity=debug",
        "component=diagnostics",
        "event_code=unknown.code",
        "attempt_id=not-a-uuid",
        "correlation_id=",
    )
    for query in queries:
        status_code, headers, body = _request(
            disposable_server_event_search.app,
            f"/staff/server-events?{query}",
            cookies=disposable_server_event_search.cookies["developer"],
        )
        assert status_code == 422
        assert headers["cache-control"] == "no-store"
        assert body == ""
    assert calls == 0


def test_repository_render_and_one_sided_failures_are_sanitized(
    disposable_server_event_search: ServerEventSearchFixture,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = disposable_server_event_search
    protected = "traceback cookie=forbidden participant=forbidden"

    def fail(*args: object, **kwargs: object) -> Any:
        raise RuntimeError(protected)

    one_sided = ServerEventProjection(
        event_id=uuid.uuid4(),
        occurred_at=_NOW,
        severity="warning",
        component="qr",
        event_code=ServerEventCode.QR_SESSION_EXPIRED,
        release_id="synthetic",
        attempt_id=uuid.uuid4(),
        correlation_id=None,
    )
    for branch in ("repository", "render", "one-sided"):
        with monkeypatch.context() as patcher:
            if branch == "repository":
                patcher.setattr(diagnostics_http, "search_server_events", fail)
            elif branch == "render":
                patcher.setattr(diagnostics_http, "_render_server_event_page", fail)
            else:
                patcher.setattr(
                    diagnostics_http,
                    "search_server_events",
                    lambda *args, **kwargs: (one_sided,),
                )
            status_code, headers, body = _request(
                fixture.app,
                "/staff/server-events",
                cookies=fixture.cookies["developer"],
            )
            assert status_code == 500
            assert headers["cache-control"] == "no-store"
            assert body == ""
            assert protected not in body
            assert "traceback" not in body.casefold()
    captured = capsys.readouterr()
    assert protected not in captured.out
    assert protected not in captured.err


def _event(
    *,
    event_id: uuid.UUID,
    code: ServerEventCode,
    occurred_at: datetime,
    release_id: str,
    attempt_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
) -> ServerEvent:
    definition = EVENT_CATALOG[code]
    return ServerEvent(
        event_id=event_id,
        occurred_at=occurred_at,
        severity=definition.severity,
        component=definition.component,
        event_code=code.value,
        release_id=release_id,
        attempt_id=attempt_id,
        correlation_id=correlation_id,
    )


def _cookies(browser_session: BrowserSession) -> dict[str, str]:
    return {"fm_staff_session": browser_session.session_token}


def _rendered_row_count(body: str) -> int:
    tbody = body.split("<tbody>", maxsplit=1)[1].split("</tbody>", maxsplit=1)[0]
    return tbody.count("<tr")


def _row(body: str, *, release_id: str) -> str:
    marker = f"<td>{escape(release_id)}</td>"
    marker_index = body.find(marker)
    assert marker_index >= 0
    row_start = body.rfind("<tr", 0, marker_index)
    row_end = body.find("</tr>", marker_index)
    assert row_start >= 0
    assert row_end >= 0
    return body[row_start : row_end + len("</tr>")]


def _request(
    app: FastAPI,
    target: str,
    *,
    cookies: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], str]:
    path, _separator, query = target.partition("?")
    request_headers = [(b"host", b"testserver")]
    if cookies:
        request_headers.append(
            (
                b"cookie",
                "; ".join(
                    f"{name}={value}" for name, value in cookies.items()
                ).encode(),
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
                "method": "GET",
                "scheme": "https",
                "path": path,
                "raw_path": path.encode(),
                "query_string": query.encode(),
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
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    ).decode()
    headers = {
        name.decode().lower(): value.decode() for name, value in start["headers"]
    }
    return start["status"], headers, body

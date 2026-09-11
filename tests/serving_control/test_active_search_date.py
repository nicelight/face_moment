from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from http.cookies import SimpleCookie
import uuid
from typing import Any

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control.ingest_target import IngestTargetRepository, Spa
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@dataclass(frozen=True, slots=True)
class _Fixture:
    app: FastAPI
    engine: Engine
    spa_id: uuid.UUID
    inaccessible_spa_id: uuid.UUID
    operator: dict[str, str]
    photographer: dict[str, str]


class _ResponseHeaders(dict[str, str]):
    """Keep repeated Set-Cookie fields while retaining mapping assertions."""

    def __init__(self, headers: dict[str, str], set_cookie_headers: list[str]) -> None:
        super().__init__(headers)
        self._set_cookie_headers = tuple(set_cookie_headers)

    def __iter__(self) -> Iterator[str]:
        return iter(self._set_cookie_headers)


@pytest.fixture
def active_search_date_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_Fixture]:
    base_settings = Settings.from_env()
    database_name = f"task068_{uuid.uuid4().hex}"
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
    marker = uuid.uuid4().hex
    password = f"task068-password-{marker}"
    operator = {"username": f"task068-operator-{marker}", "password": password}
    photographer = {
        "username": f"task068-photographer-{marker}",
        "password": password,
    }

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc),
                **PIPELINE_COMPATIBILITY,
            )
            active_spa = IngestTargetRepository(session).configure_spa(
                name=f"task068-active-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            inaccessible_spa = IngestTargetRepository(session).configure_spa(
                name=f"task068-inactive-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            session.execute(
                text("UPDATE face_moment.spas SET active = false WHERE id = :spa_id"),
                {"spa_id": inaccessible_spa.spa_id},
            )
            session.commit()
            for account, role in (
                (operator, StaffRole.OPERATOR),
                (photographer, StaffRole.PHOTOGRAPHER),
            ):
                provision_staff_user(
                    session,
                    username=account["username"],
                    password=account["password"],
                    role=role,
                )

        app = create_app()
        app.state.role_state["session_factory"] = lambda: Session(engine)
        yield _Fixture(
            app=app,
            engine=engine,
            spa_id=active_spa.spa_id,
            inaccessible_spa_id=inaccessible_spa.spa_id,
            operator=operator,
            photographer=photographer,
        )
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(
                text(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)")
            )
        admin_engine.dispose()


def test_active_search_date_surface_is_registered() -> None:
    app = create_app()

    routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", ())
    }

    assert ("/staff/search-settings", "GET") in routes
    assert ("/api/serving/spas/{spa_id}/active-visit-date", "GET") in routes
    assert ("/api/serving/spas/{spa_id}/active-visit-date", "PUT") in routes


def test_operator_reads_and_atomically_updates_active_date(
    active_search_date_fixture: _Fixture,
) -> None:
    fixture = active_search_date_fixture
    cookies = _login(fixture.app, fixture.operator)

    page_status, page_headers, page = _request(
        fixture.app,
        "GET",
        "/staff/search-settings",
        cookies=cookies,
    )
    assert page_status == 200
    assert page_headers["cache-control"] == "no-store"
    assert '<h1>Active search date</h1>' in page
    assert str(fixture.spa_id) in page

    path = f"/api/serving/spas/{fixture.spa_id}/active-visit-date"
    initial_status, _, initial = _request(
        fixture.app,
        "GET",
        path,
        cookies=cookies,
    )
    assert initial_status == 200
    assert set(initial) == {
        "schema_version",
        "spa_id",
        "active_visit_date",
        "settings_revision",
        "updated_at",
    }
    assert initial == {
        "schema_version": 1,
        "spa_id": str(fixture.spa_id),
        "active_visit_date": None,
        "settings_revision": 1,
        "updated_at": None,
    }

    status_code, _, updated = _request(
        fixture.app,
        "PUT",
        path,
        body={"visit_date": "2026-08-22"},
        cookies=cookies,
        headers={"X-CSRF-Token": cookies["fm_staff_csrf"]},
    )
    assert status_code == 200
    assert updated["schema_version"] == 1
    assert updated["spa_id"] == str(fixture.spa_id)
    assert updated["active_visit_date"] == "2026-08-22"
    assert updated["settings_revision"] == 2
    assert updated["updated_at"] is not None

    with Session(fixture.engine) as session:
        spa = session.scalar(select(Spa).where(Spa.id == fixture.spa_id))
        assert spa is not None
        assert spa.active_visit_date == date(2026, 8, 22)
        assert spa.settings_revision == 2


def test_authentication_authorization_and_validation_do_not_mutate_owner(
    active_search_date_fixture: _Fixture,
) -> None:
    fixture = active_search_date_fixture
    operator_cookies = _login(fixture.app, fixture.operator)
    photographer_cookies = _login(fixture.app, fixture.photographer)
    path = f"/api/serving/spas/{fixture.spa_id}/active-visit-date"

    assert _request(fixture.app, "GET", path)[0] == 401
    assert _request(
        fixture.app,
        "GET",
        path,
        cookies={"fm_staff_session": "invalid-task068-session"},
    )[0] == 401
    assert _request(
        fixture.app, "GET", path, cookies=photographer_cookies
    )[0] == 403
    assert _request(
        fixture.app,
        "GET",
        f"/api/serving/spas/{uuid.uuid4()}/active-visit-date",
        cookies=operator_cookies,
    )[0] == 404
    assert _request(
        fixture.app,
        "GET",
        f"/api/serving/spas/{fixture.inaccessible_spa_id}/active-visit-date",
        cookies=operator_cookies,
    )[0] == 403

    for cookies, headers in (
        (operator_cookies, {}),
        (operator_cookies, {"X-CSRF-Token": "wrong-task068-csrf"}),
        (photographer_cookies, {"X-CSRF-Token": photographer_cookies["fm_staff_csrf"]}),
    ):
        assert _request(
            fixture.app,
            "PUT",
            path,
            body={"visit_date": "2026-08-23"},
            cookies=cookies,
            headers=headers,
        )[0] == 403

    assert _request(
        fixture.app,
        "PUT",
        f"/api/serving/spas/{uuid.uuid4()}/active-visit-date",
        body={"visit_date": "2026-08-23"},
        cookies=operator_cookies,
        headers={"X-CSRF-Token": operator_cookies["fm_staff_csrf"]},
    )[0] == 404
    for invalid_body in (
        {"visit_date": "2026-02-30"},
        {"visit_date": "2026-08-23", "unexpected": True},
    ):
        assert _request(
            fixture.app,
            "PUT",
            path,
            body=invalid_body,
            cookies=operator_cookies,
            headers={"X-CSRF-Token": operator_cookies["fm_staff_csrf"]},
        )[0] == 422

    with Session(fixture.engine) as session:
        spa = session.scalar(select(Spa).where(Spa.id == fixture.spa_id))
        assert spa is not None
        assert spa.active_visit_date is None
        assert spa.settings_revision == 1


def _login(app: FastAPI, credentials: dict[str, str]) -> dict[str, str]:
    status_code, set_cookies, _ = _request(
        app,
        "POST",
        "/api/staff/sessions",
        body=credentials,
    )
    assert status_code == 204
    cookies: dict[str, str] = {}
    for header in set_cookies:
        parsed = SimpleCookie()
        parsed.load(header)
        cookies.update({name: morsel.value for name, morsel in parsed.items()})
    return cookies


def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    body: dict[str, object] | None = None,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, _ResponseHeaders, Any]:
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
    response_headers = {
        name.decode().lower(): value.decode() for name, value in start["headers"]
    }
    set_cookie_headers = [
        value.decode()
        for name, value in start["headers"]
        if name.lower() == b"set-cookie"
    ]
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return (
        int(start["status"]),
        _ResponseHeaders(
            {
            "cache-control": response_headers.get("cache-control", ""),
                "set-cookie": "\n".join(set_cookie_headers),
            },
            set_cookie_headers,
        ),
        json.loads(response_body or b'""')
        if response_headers.get("content-type", "").startswith("application/json")
        else response_body.decode(),
    )


def test_spa_rename_persists_in_staff_selectors_and_preserves_identity(
    active_search_date_fixture: _Fixture,
) -> None:
    fixture = active_search_date_fixture
    cookies = _login(fixture.app, fixture.operator)
    name = '  Термы <Центр> & бассейн  '
    status_code, _, payload = _request(
        fixture.app, "PUT", f"/api/serving/spas/{fixture.spa_id}/name",
        body={"name": name}, cookies=cookies,
        headers={"X-CSRF-Token": cookies["fm_staff_csrf"]},
    )
    assert status_code == 200
    assert payload == {"spa_id": str(fixture.spa_id), "name": name.strip()}
    with Session(fixture.engine) as session:
        spa = session.get(Spa, fixture.spa_id)
        assert spa is not None
        assert spa.name == name.strip()
        assert spa.settings_revision == 1
        assert spa.active_visit_date is None
    for path, selector in (
        ("/staff/photo-inventory", "recent-statistics-spa-id"),
        ("/staff/processing-health", "health-spa-id"),
        ("/staff/search-settings", "spa-id"),
    ):
        status_code, headers, page = _request(fixture.app, "GET", path, cookies=cookies)
        assert status_code == 200
        assert headers["cache-control"] == "no-store"
        assert f'<select id="{selector}"' in page
        assert f'<option value="{fixture.spa_id}">Термы &lt;Центр&gt; &amp; бассейн</option>' in page
        assert str(fixture.inaccessible_spa_id) not in page


def test_spa_rename_rejects_unauthorized_and_invalid_writes(
    active_search_date_fixture: _Fixture,
) -> None:
    fixture = active_search_date_fixture
    operator = _login(fixture.app, fixture.operator)
    photographer = _login(fixture.app, fixture.photographer)
    path = f"/api/serving/spas/{fixture.spa_id}/name"
    for cookies, headers, body, target, expected in (
        (None, None, {"name": "Новое имя"}, path, 401),
        (photographer, {"X-CSRF-Token": photographer["fm_staff_csrf"]}, {"name": "Новое имя"}, path, 403),
        (operator, None, {"name": "Новое имя"}, path, 403),
        (operator, {"X-CSRF-Token": operator["fm_staff_csrf"]}, {"name": "   "}, path, 422),
        (operator, {"X-CSRF-Token": operator["fm_staff_csrf"]}, {"name": "x" * 256}, path, 422),
        (operator, {"X-CSRF-Token": operator["fm_staff_csrf"]}, {"name": "Имя"}, f"/api/serving/spas/{uuid.uuid4()}/name", 404),
        (operator, {"X-CSRF-Token": operator["fm_staff_csrf"]}, {"name": "Имя"}, f"/api/serving/spas/{fixture.inaccessible_spa_id}/name", 403),
    ):
        assert _request(fixture.app, "PUT", target, cookies=cookies, headers=headers, body=body)[0] == expected
    with Session(fixture.engine) as session:
        spa = session.get(Spa, fixture.spa_id)
        assert spa is not None and spa.name.startswith("task068-active-")


def test_unnamed_spas_receive_persisted_numbered_names(
    active_search_date_fixture: _Fixture,
) -> None:
    fixture = active_search_date_fixture
    with Session(fixture.engine) as session:
        original = session.get(Spa, fixture.spa_id)
        assert original is not None
        repository = IngestTargetRepository(session)
        first = repository.configure_spa(timezone="UTC", serving_pipeline_revision_id=original.serving_pipeline_revision_id)
        second = repository.configure_spa(timezone="UTC", serving_pipeline_revision_id=original.serving_pipeline_revision_id)
        session.commit()
    with Session(fixture.engine) as session:
        repository = IngestTargetRepository(session)
        assert repository.resolve_ingest_target(first.spa_id).name == "Площадка 1"
        assert repository.resolve_ingest_target(second.spa_id).name == "Площадка 2"

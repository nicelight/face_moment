from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine, update
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.processing.revisions import PipelineRevision
from face_moment.serving_control import IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY
from face_moment.serving_control.ingest_target import Spa


@pytest.fixture
def disposable_ingest_target_state(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[FastAPI, dict[str, str], dict[str, str], dict[str, str]]]:
    base_settings = Settings.from_env()
    probe_database = f"task015_{uuid.uuid4().hex}"
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
    password = f"task015-password-{marker}"
    photographer = {"username": f"task015-photographer-{marker}", "password": password}
    operator = {"username": f"task015-operator-{marker}", "password": password}
    target: dict[str, str] = {}

    try:
        alembic_config = Config("alembic.ini")
        alembic_command.upgrade(alembic_config, "head")
        with Session(engine) as database_session:
            eligible_revision = PipelineRevisionRepository(
                database_session
            ).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=_utc_now(),
                **PIPELINE_COMPATIBILITY,
            )
            target_record = IngestTargetRepository(database_session).configure_spa(
                name=f"task015-eligible-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=eligible_revision.id,
            )
            inactive_record = IngestTargetRepository(database_session).configure_spa(
                name=f"task015-inactive-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=eligible_revision.id,
            )
            database_session.execute(
                update(Spa).where(Spa.id == inactive_record.spa_id).values(active=False)
            )
            database_session.add(
                Spa(
                    name=f"task015-invalid-timezone-{marker}",
                    timezone="Not/A_Timezone",
                    active=True,
                    serving_pipeline_revision_id=eligible_revision.id,
                )
            )
            ineligible_revision = PipelineRevision(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=None,
                **PIPELINE_COMPATIBILITY,
            )
            database_session.add(ineligible_revision)
            database_session.flush()
            database_session.add(
                Spa(
                    name=f"task015-ineligible-{marker}",
                    timezone="Asia/Dushanbe",
                    active=True,
                    serving_pipeline_revision_id=ineligible_revision.id,
                )
            )
            database_session.commit()
            target = {
                "spa_id": str(target_record.spa_id),
                "name": target_record.name,
                "timezone": target_record.timezone,
            }
        with Session(engine) as database_session:
            provision_staff_user(
                database_session,
                username=photographer["username"],
                password=photographer["password"],
                role=StaffRole.PHOTOGRAPHER,
            )
            provision_staff_user(
                database_session,
                username=operator["username"],
                password=operator["password"],
                role=StaffRole.OPERATOR,
            )
        app = create_app()
        app.state.role_state["session_factory"] = lambda: Session(engine)
        yield app, target, photographer, operator
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)")
        admin_engine.dispose()


def test_authenticated_ingest_targets_are_owner_filtered_and_redacted(
    disposable_ingest_target_state: tuple[
        FastAPI, dict[str, str], dict[str, str], dict[str, str]
    ],
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, target, photographer, operator = disposable_ingest_target_state

    photographer_cookies = _login(app, photographer)
    status, _, body = _request(
        app,
        "GET",
        "/api/inventory/ingest-targets",
        cookies=photographer_cookies,
    )

    assert status == 200
    assert body == {"schema_version": 1, "spas": [target]}
    assert set(body["spas"][0]) == {"spa_id", "name", "timezone"}
    assert "pipeline_revision_id" not in json.dumps(body)
    assert photographer["password"] not in caplog.text
    assert photographer_cookies["fm_staff_session"] not in caplog.text

    caddyfile = Path("deploy/Caddyfile").read_text()
    assert (
        "\thandle /api/inventory/* {\n"
        "\t\treverse_proxy backend:8000 {\n"
        "\t\t\theader_up X-Forwarded-For {remote_host}\n"
        "\t\t}\n"
        "\t}"
    ) in caddyfile
    assert "handle_path /api/inventory/" not in caddyfile

    assert _request(app, "GET", "/api/inventory/ingest-targets")[0] == 401
    assert (
        _request(
            app,
            "GET",
            "/api/inventory/ingest-targets",
            cookies={"fm_staff_session": "invalid-session-token"},
        )[0]
        == 401
    )

    operator_cookies = _login(app, operator)
    assert (
        _request(
            app,
            "GET",
            "/api/inventory/ingest-targets",
            cookies=operator_cookies,
        )[0]
        == 403
    )

    revoke_status, _, _ = _request(
        app,
        "DELETE",
        "/api/staff/session",
        cookies=photographer_cookies,
        headers={"X-CSRF-Token": photographer_cookies["fm_staff_csrf"]},
    )
    assert revoke_status == 204
    assert (
        _request(
            app,
            "GET",
            "/api/inventory/ingest-targets",
            cookies=photographer_cookies,
        )[0]
        == 401
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _login(app: FastAPI, credentials: dict[str, str]) -> dict[str, str]:
    status, set_cookies, _ = _request(
        app,
        "POST",
        "/api/staff/sessions",
        body=credentials,
    )
    assert status == 204
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

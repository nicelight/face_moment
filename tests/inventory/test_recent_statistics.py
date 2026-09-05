from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.inventory import recent_statistics
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.platform.auth.sessions import LoginRateLimiter, create_browser_session
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control.ingest_target import IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@dataclass(frozen=True, slots=True)
class _CounterCase:
    accepted_at: datetime
    status: str
    status_changed_at: datetime
    active: bool


@dataclass(frozen=True, slots=True)
class _Fixture:
    app: FastAPI
    engine: Engine
    spa_id: uuid.UUID
    unknown_spa_id: uuid.UUID
    observed_at: datetime
    cases: tuple[_CounterCase, ...]
    accounts: dict[str, dict[str, str]]


@pytest.fixture
def disposable_recent_statistics_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Fixture]:
    base_settings = Settings.from_env()
    probe_database = f"task108_{uuid.uuid4().hex}"
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
    accounts = {
        role: {"username": f"task108-{role}-{marker}", "password": f"task108-password-{marker}"}
        for role in ("operator", "developer", "photographer")
    }
    observed_at = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        with Session(engine) as session:
            admission_revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=observed_at,
                **PIPELINE_COMPATIBILITY,
            )
            later_revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
                validated_at=observed_at,
                **PIPELINE_COMPATIBILITY,
            )
            target = IngestTargetRepository(session).configure_spa(
                name=f"task108-spa-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=admission_revision.id,
            )
            principals = {
                role: provision_staff_user(
                    session,
                    username=account["username"],
                    password=account["password"],
                    role=StaffRole(role),
                )
                for role, account in accounts.items()
            }
            cases = _seed_cases(
                session,
                spa_id=target.spa_id,
                admission_revision_id=admission_revision.id,
                later_revision_id=later_revision.id,
                uploader_id=principals["photographer"].staff_user_id,
                observed_at=observed_at,
            )
            session.commit()
        app = create_app()
        app.state.role_state["session_factory"] = lambda: Session(engine)
        yield _Fixture(
            app=app,
            engine=engine,
            spa_id=target.spa_id,
            unknown_spa_id=uuid.uuid4(),
            observed_at=observed_at,
            cases=tuple(cases),
            accounts=accounts,
        )
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)")
        admin_engine.dispose()


def test_recent_statistics_endpoint_validates_its_required_spa() -> None:
    """The accepted staff boundary must expose its required СПА query field."""

    assert _get_status(create_app(), "/api/inventory/recent-statistics") == 422


def test_recent_statistics_matches_the_independent_controlled_clock_oracle(
    disposable_recent_statistics_state: _Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = disposable_recent_statistics_state
    monkeypatch.setattr(recent_statistics, "_observed_at", lambda: fixture.observed_at)
    operator = _cookies(fixture.engine, fixture.accounts["operator"])
    developer = _cookies(fixture.engine, fixture.accounts["developer"])
    photographer = _cookies(fixture.engine, fixture.accounts["photographer"])
    expected = _oracle(fixture.cases, fixture.observed_at)

    for cookies in (operator, developer):
        status_code, headers, response = _request(
            fixture.app,
            "/api/inventory/recent-statistics",
            params={"spa_id": str(fixture.spa_id)},
            cookies=cookies,
        )
        assert status_code == 200
        assert headers["cache-control"] == "no-store"
        assert response == {
            "schema_version": 1,
            "spa_id": str(fixture.spa_id),
            "observed_at": "2026-09-05T12:00:00Z",
            "windows": expected,
        }

    for cookies, expected_status in ((None, 401), (photographer, 403)):
        result = _request(
            fixture.app,
            "/api/inventory/recent-statistics",
            params={"spa_id": str(fixture.spa_id)},
            cookies=cookies,
        )
        assert result[0] == expected_status
        assert result[1]["cache-control"] == "no-store"
    unknown = _request(
        fixture.app,
        "/api/inventory/recent-statistics",
        params={"spa_id": str(fixture.unknown_spa_id)},
        cookies=operator,
    )
    assert unknown[0] == 404
    assert unknown[1]["cache-control"] == "no-store"
    invalid = _request(
        fixture.app,
        "/api/inventory/recent-statistics",
        params={"spa_id": "not-a-uuid"},
        cookies=operator,
    )
    assert invalid[0] == 422
    assert invalid[1]["cache-control"] == "no-store"


def test_recent_statistics_stays_a_read_only_polling_mechanism() -> None:
    aggregate_source = Path("src/face_moment/inventory/recent_statistics.py").read_text()
    transport_source = Path("src/face_moment/inventory/http.py").read_text()

    for forbidden in ("mapped_column", "Base", ".add(", ".commit("):
        assert forbidden not in aggregate_source
    for forbidden in ("Web" + "Socket", "Event" + "Source"):
        assert forbidden not in aggregate_source + transport_source
    assert "setInterval(loadRecentStatistics, 5000);" in transport_source


def _seed_cases(
    session: Session,
    *,
    spa_id: uuid.UUID,
    admission_revision_id: uuid.UUID,
    later_revision_id: uuid.UUID,
    uploader_id: uuid.UUID,
    observed_at: datetime,
) -> list[_CounterCase]:
    definitions = (
        ("pending-lower", observed_at - timedelta(minutes=1), "pending", observed_at - timedelta(minutes=1), True),
        ("processing-upper", observed_at, "processing", observed_at - timedelta(minutes=30), True),
        ("ready-five-lower", observed_at - timedelta(minutes=5), "ready", observed_at - timedelta(minutes=5), True),
        ("no-faces-sixty-lower", observed_at - timedelta(minutes=60), "no_faces", observed_at - timedelta(minutes=60), True),
        ("failed-one", observed_at - timedelta(minutes=61), "failed", observed_at - timedelta(minutes=1), True),
        ("ready-one-outside", observed_at - timedelta(minutes=1, microseconds=1), "ready", observed_at - timedelta(minutes=1, microseconds=1), True),
        ("inactive-failed", observed_at, "failed", observed_at, False),
        ("restored", observed_at - timedelta(minutes=5), "failed", observed_at - timedelta(minutes=5), True),
        ("admission-ready-later-failed", observed_at - timedelta(minutes=5), "ready", observed_at - timedelta(minutes=5), True),
    )
    cases: list[_CounterCase] = []
    for marker, accepted_at, state_status, changed_at, active in definitions:
        photo = Photo(
            spa_id=spa_id,
            visit_date=date(2026, 9, 5),
            captured_at=accepted_at,
            captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
            accepted_at=accepted_at,
            admission_pipeline_revision_id=admission_revision_id,
            uploader_id=uploader_id,
            checksum_sha256=hashlib.sha256(marker.encode()).digest(),
            original_object_key=f"task108/{marker}/original.jpg",
            original_byte_size=1,
            width=1,
            height=1,
            is_active=active,
        )
        session.add(photo)
        session.flush()
        session.add(
            PhotoPipelineState(
                photo_id=photo.id,
                pipeline_revision_id=admission_revision_id,
                status=state_status,
                attempt_count=0,
                status_changed_at=changed_at,
            )
        )
        if marker == "admission-ready-later-failed":
            session.add(
                PhotoPipelineState(
                    photo_id=photo.id,
                    pipeline_revision_id=later_revision_id,
                    status="failed",
                    attempt_count=1,
                    status_changed_at=observed_at,
                )
            )
        if marker == "restored":
            photo.is_active = False
            session.flush()
            photo.is_active = True
        cases.append(_CounterCase(accepted_at, state_status, changed_at, active))
    return cases


def _oracle(cases: tuple[_CounterCase, ...], observed_at: datetime) -> list[dict[str, int]]:
    windows = []
    for minutes in (1, 5, 60):
        lower = observed_at - timedelta(minutes=minutes)
        active_cases = [case for case in cases if case.active]
        accepted = [case for case in active_cases if lower <= case.accepted_at <= observed_at]
        transitioned = [
            case for case in active_cases if lower <= case.status_changed_at <= observed_at
        ]
        windows.append(
            {
                "minutes": minutes,
                "new": len(accepted),
                "unprocessed": sum(case.status in {"pending", "processing"} for case in accepted),
                "processed": sum(case.status in {"ready", "no_faces"} for case in transitioned),
                "failed": sum(case.status == "failed" for case in transitioned),
            }
        )
    return windows


def _get_status(app: FastAPI, path: str) -> int:
    messages: list[dict[str, object]] = []
    delivered = False

    async def receive() -> dict[str, object]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
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
                "query_string": b"",
                "headers": [(b"host", b"testserver")],
                "client": ("127.0.0.1", 51515),
                "server": ("testserver", 443),
            },
            receive,
            send,
        )
    )
    start = next(message for message in messages if message["type"] == "http.response.start")
    return int(start["status"])


def _cookies(engine: Engine, account: dict[str, str]) -> dict[str, str]:
    with Session(engine) as session:
        browser_session = create_browser_session(
            session,
            username=account["username"],
            password=account["password"],
            ip_address="127.0.0.1",
            ttl_seconds=3600,
            limiter=LoginRateLimiter(limit=10, window_seconds=60),
        )
    return {"fm_staff_session": browser_session.session_token}


def _request(
    app: FastAPI,
    path: str,
    *,
    params: dict[str, str],
    cookies: dict[str, str] | None,
) -> tuple[int, dict[str, str], object]:
    request_headers = [(b"host", b"testserver")]
    if cookies:
        request_headers.append(
            (
                b"cookie",
                "; ".join(f"{name}={value}" for name, value in cookies.items()).encode(),
            )
        )
    messages: list[dict[str, object]] = []
    delivered = False

    async def receive() -> dict[str, object]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
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
                "query_string": urlencode(params).encode(),
                "headers": request_headers,
                "client": ("127.0.0.1", 51515),
                "server": ("testserver", 443),
            },
            receive,
            send,
        )
    )
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    headers = {
        name.decode().lower(): value.decode()
        for name, value in start.get("headers", [])
    }
    return int(start["status"]), headers, json.loads(body or b"{}")

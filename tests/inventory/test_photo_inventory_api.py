from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.inventory import http as inventory_http
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.recent_statistics import read_recent_statistics
from face_moment.inventory.validation import CapturedAtSource
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.platform.auth.sessions import (
    LoginRateLimiter,
    create_browser_session,
)
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.processing.searchable_projection import SearchableProjectionRepository
from face_moment.serving_control.ingest_target import IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@dataclass(frozen=True, slots=True)
class _Fixture:
    app: FastAPI
    engine: Engine
    spa_id: uuid.UUID
    owned_photo_ids: tuple[uuid.UUID, ...]
    foreign_photo_id: uuid.UUID
    accounts: dict[str, dict[str, str]]
    observed_at: datetime


@pytest.fixture
def disposable_photo_inventory_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Fixture]:
    base_settings = Settings.from_env()
    database_name = f"task107_{uuid.uuid4().hex}"
    database_url = make_url(base_settings.database_url).set(database=database_name)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {database_name}")
    monkeypatch.setenv("DATABASE_URL", database_url.render_as_string(hide_password=False))
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    marker = uuid.uuid4().hex
    accounts = {
        role: {"username": f"task107-{role}-{marker}", "password": f"task107-{marker}"}
        for role in ("photographer", "other_photographer", "operator", "developer")
    }
    observed_at = datetime(2026, 9, 5, 8, 30, tzinfo=UTC)
    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=observed_at,
                **PIPELINE_COMPATIBILITY,
            )
            target = IngestTargetRepository(session).configure_spa(
                name=f"task107-spa-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            principals = {
                role: provision_staff_user(
                    session,
                    username=account["username"],
                    password=account["password"],
                    role=StaffRole.PHOTOGRAPHER
                    if "photographer" in role
                    else StaffRole(role),
                )
                for role, account in accounts.items()
            }
            own_photos = tuple(
                _add_photo(
                    session,
                    marker=f"{marker}-{source.value}",
                    spa_id=target.spa_id,
                    uploader_id=principals["photographer"].staff_user_id,
                    revision_id=revision.id,
                    captured_at=observed_at + timedelta(minutes=index),
                    source=source,
                    with_searchable_state=index == 1,
                )
                for index, source in enumerate(CapturedAtSource, start=1)
            )
            foreign_photo = _add_photo(
                session,
                marker=f"{marker}-foreign",
                spa_id=target.spa_id,
                uploader_id=principals["other_photographer"].staff_user_id,
                revision_id=revision.id,
                captured_at=observed_at + timedelta(minutes=2, seconds=30),
                source=CapturedAtSource.EXIF,
            )
            session.commit()
        app = create_app()
        app.state.role_state["session_factory"] = lambda: Session(engine)
        yield _Fixture(
            app=app,
            engine=engine,
            spa_id=target.spa_id,
            owned_photo_ids=own_photos,
            foreign_photo_id=foreign_photo,
            accounts=accounts,
            observed_at=observed_at,
        )
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)")
        admin_engine.dispose()


def test_inventory_list_applies_persisted_scope_interval_and_role_ownership(
    disposable_photo_inventory_state: _Fixture,
) -> None:
    fixture = disposable_photo_inventory_state
    parameters = _selection_parameters(fixture)
    photographer = _cookies(fixture.engine, fixture.accounts["photographer"])
    other = _cookies(fixture.engine, fixture.accounts["other_photographer"])
    operator = _cookies(fixture.engine, fixture.accounts["operator"])
    developer = _cookies(fixture.engine, fixture.accounts["developer"])

    for cookies, expected_ids in (
        (photographer, fixture.owned_photo_ids),
        (other, (fixture.foreign_photo_id,)),
        (operator, fixture.owned_photo_ids[:2] + (fixture.foreign_photo_id,) + fixture.owned_photo_ids[2:]),
        (developer, fixture.owned_photo_ids[:2] + (fixture.foreign_photo_id,) + fixture.owned_photo_ids[2:]),
    ):
        status_code, headers, body = _request(
            fixture.app, "GET", "/api/inventory/photos", params=parameters, cookies=cookies
        )
        assert status_code == 200
        assert headers["cache-control"] == "no-store"
        assert set(body) == {
            "schema_version", "spa_id", "visit_date", "captured_from", "captured_before", "photos"
        }
        assert [row["photo_id"] for row in body["photos"]] == [str(photo_id) for photo_id in expected_ids]
        assert all(set(row) == {"photo_id", "captured_at", "accepted_at", "active"} for row in body["photos"])

    assert _request(fixture.app, "GET", "/api/inventory/photos", params=parameters, cookies=None)[0] == 401
    assert _request(
        fixture.app,
        "GET",
        "/api/inventory/photos",
        params={**parameters, "spa_id": str(uuid.uuid4())},
        cookies=operator,
    )[0] == 404
    assert _request(
        fixture.app,
        "GET",
        "/api/inventory/photos",
        params={**parameters, "captured_before": parameters["captured_from"]},
        cookies=photographer,
    )[0] == 422


def test_visibility_is_role_safe_idempotent_and_preserves_existing_state(
    disposable_photo_inventory_state: _Fixture,
) -> None:
    fixture = disposable_photo_inventory_state
    photographer = _cookies(fixture.engine, fixture.accounts["photographer"])
    other = _cookies(fixture.engine, fixture.accounts["other_photographer"])
    operator = _cookies(fixture.engine, fixture.accounts["operator"])
    developer = _cookies(fixture.engine, fixture.accounts["developer"])
    photo_id = fixture.owned_photo_ids[0]
    before = _photo_snapshot(fixture.engine, photo_id)

    with Session(fixture.engine) as session:
        assert read_recent_statistics(
            session,
            session_token=operator["fm_staff_session"],
            spa_id=fixture.spa_id,
            observed_at=fixture.observed_at + timedelta(minutes=4),
        ).windows[1]["new"] == 1

    assert _visibility_request(fixture.app, photo_id, False, cookies=None)[0] == 401
    assert _visibility_request(
        fixture.app, photo_id, False, cookies={"fm_staff_session": photographer["fm_staff_session"]}
    )[0] == 403
    assert _visibility_request(fixture.app, photo_id, False, cookies=other)[0] == 403
    assert _visibility_request(fixture.app, uuid.uuid4(), False, cookies=photographer)[0] == 404
    assert _request(
        fixture.app,
        "PUT",
        f"/api/inventory/photos/{photo_id}/visibility",
        params={},
        cookies=photographer,
        headers={"x-csrf-token": photographer["fm_staff_csrf"]},
        body=b'{"schema_version": true, "active": false}',
    )[0] == 422
    assert _photo_snapshot(fixture.engine, photo_id) == before

    status_code, headers, body = _visibility_request(
        fixture.app, photo_id, False, cookies=photographer
    )
    assert (status_code, headers["cache-control"], body) == (
        200,
        "no-store",
        {"schema_version": 1, "photo_id": str(photo_id), "active": False},
    )
    assert _visibility_request(fixture.app, photo_id, False, cookies=photographer)[0] == 200
    inactive = _photo_snapshot(fixture.engine, photo_id)
    assert inactive[0] is False
    assert inactive[1:] == before[1:]

    with Session(fixture.engine) as session:
        assert not SearchableProjectionRepository(session).resolve_for_photo(
            photo_id=photo_id, pipeline_revision_id=None, spa_id=fixture.spa_id
        ).searchable
        assert read_recent_statistics(
            session,
            session_token=operator["fm_staff_session"],
            spa_id=fixture.spa_id,
            observed_at=fixture.observed_at + timedelta(minutes=4),
        ).windows[1]["new"] == 0

    assert _visibility_request(fixture.app, photo_id, True, cookies=operator)[2]["active"] is True
    restored = _photo_snapshot(fixture.engine, photo_id)
    assert restored == before
    with Session(fixture.engine) as session:
        assert SearchableProjectionRepository(session).resolve_for_photo(
            photo_id=photo_id, pipeline_revision_id=None, spa_id=fixture.spa_id
        ).searchable
        assert read_recent_statistics(
            session,
            session_token=operator["fm_staff_session"],
            spa_id=fixture.spa_id,
            observed_at=fixture.observed_at + timedelta(minutes=4),
        ).windows[1]["new"] == 1

    assert _visibility_request(fixture.app, photo_id, False, cookies=developer)[2]["active"] is False
    assert _visibility_request(fixture.app, photo_id, True, cookies=photographer)[2]["active"] is True
    assert _photo_snapshot(fixture.engine, photo_id) == before


def test_inventory_owner_failures_do_not_emit_false_success(
    disposable_photo_inventory_state: _Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = disposable_photo_inventory_state
    operator = _cookies(fixture.engine, fixture.accounts["operator"])

    def owner_failure(*_: object, **__: object) -> object:
        raise RuntimeError("task107-owner-failure")

    monkeypatch.setattr(inventory_http, "read_photo_inventory", owner_failure)
    status_code, headers, _ = _request(
        fixture.app,
        "GET",
        "/api/inventory/photos",
        params=_selection_parameters(fixture),
        cookies=operator,
    )
    assert (status_code, headers["cache-control"]) == (500, "no-store")


def test_inventory_transport_keeps_authorization_and_writes_inside_inventory() -> None:
    source = Path("src/face_moment/inventory/http.py").read_text()
    owner = Path("src/face_moment/inventory/photo_inventory.py").read_text()
    assert "read_photo_inventory" in source and "set_photo_visibility" in source
    assert "PhotoPipelineState" not in source and "Photo(" not in source
    assert "with_for_update" in owner and "photo.is_active = active" in owner


def _add_photo(
    session: Session,
    *,
    marker: str,
    spa_id: uuid.UUID,
    uploader_id: uuid.UUID,
    revision_id: uuid.UUID,
    captured_at: datetime,
    source: CapturedAtSource,
    with_searchable_state: bool = False,
) -> uuid.UUID:
    photo = Photo(
        spa_id=spa_id,
        visit_date=date(2026, 9, 5),
        captured_at=captured_at,
        captured_at_source=source,
        accepted_at=captured_at,
        admission_pipeline_revision_id=revision_id,
        uploader_id=uploader_id,
        checksum_sha256=hashlib.sha256(marker.encode()).digest(),
        original_object_key=f"private/task107/{marker}/original.jpg",
        original_byte_size=100,
        width=10,
        height=10,
        is_active=True,
    )
    session.add(photo)
    session.flush()
    if with_searchable_state:
        session.add(
            PhotoPipelineState(
                photo_id=photo.id,
                pipeline_revision_id=revision_id,
                status="ready",
                attempt_count=1,
                status_changed_at=captured_at,
                searchable_at=captured_at,
                preview_object_key=f"private/task107/{marker}/preview.jpg",
                thumbnail_object_key=f"private/task107/{marker}/thumbnail.jpg",
            )
        )
        session.add(
            PhotoFace(
                photo_id=photo.id,
                pipeline_revision_id=revision_id,
                face_index=0,
                bbox_x=1.0,
                bbox_y=1.0,
                bbox_w=2.0,
                bbox_h=2.0,
                landmarks_json=[[1.0, 1.0]] * 5,
                detection_confidence=0.9,
                embedding=[1.0] + [0.0] * 127,
            )
        )
    return photo.id


def _selection_parameters(fixture: _Fixture) -> dict[str, str]:
    return {
        "spa_id": str(fixture.spa_id),
        "visit_date": "2026-09-05",
        "captured_from": "2026-09-05T08:30:00+00:00",
        "captured_before": "2026-09-05T08:34:00+00:00",
    }


def _photo_snapshot(engine: Engine, photo_id: uuid.UUID) -> tuple[object, ...]:
    with Session(engine) as session:
        photo = session.get(Photo, photo_id)
        assert photo is not None
        state = session.scalar(
            select(PhotoPipelineState).where(PhotoPipelineState.photo_id == photo_id)
        )
        assert state is not None
        return (
            photo.is_active,
            photo.spa_id,
            photo.visit_date,
            photo.captured_at,
            photo.accepted_at,
            photo.admission_pipeline_revision_id,
            photo.uploader_id,
            photo.original_object_key,
            state.status,
            state.status_changed_at,
            state.preview_object_key,
            state.thumbnail_object_key,
        )


def _cookies(engine: Engine, account: dict[str, str]) -> dict[str, str]:
    with Session(engine) as session:
        browser = create_browser_session(
            session,
            username=account["username"],
            password=account["password"],
            ip_address="127.0.0.1",
            ttl_seconds=3600,
            limiter=LoginRateLimiter(limit=10, window_seconds=60),
        )
    return {"fm_staff_session": browser.session_token, "fm_staff_csrf": browser.csrf_token}


def _visibility_request(
    app: FastAPI, photo_id: uuid.UUID, active: bool, *, cookies: dict[str, str] | None
) -> tuple[int, dict[str, str], object]:
    headers = {} if cookies is None or "fm_staff_csrf" not in cookies else {"x-csrf-token": cookies["fm_staff_csrf"]}
    return _request(
        app,
        "PUT",
        f"/api/inventory/photos/{photo_id}/visibility",
        params={},
        cookies=cookies,
        headers=headers,
        body=json.dumps({"schema_version": 1, "active": active}).encode(),
    )


def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    params: dict[str, str],
    cookies: dict[str, str] | None,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, dict[str, str], object]:
    request_headers = [(b"host", b"testserver")]
    if cookies:
        request_headers.append((b"cookie", "; ".join(f"{key}={value}" for key, value in cookies.items()).encode()))
    for name, value in (headers or {}).items():
        request_headers.append((name.encode(), value.encode()))
    if body:
        request_headers.append((b"content-type", b"application/json"))
    messages: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    asyncio.run(app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "https", "path": path, "raw_path": path.encode(), "query_string": urlencode(params).encode(), "headers": request_headers, "client": ("127.0.0.1", 51515), "server": ("testserver", 443)}, receive, send))
    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    response_headers = {name.decode().lower(): value.decode() for name, value in start.get("headers", [])}
    return int(start["status"]), response_headers, json.loads(response_body or b"{}")

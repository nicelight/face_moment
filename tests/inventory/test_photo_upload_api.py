from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control import IngestTargetRepository


@pytest.fixture
def disposable_photo_upload_state(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[FastAPI, Engine, PrivateObjectStore, dict[str, str], dict[str, dict[str, str]]]]:
    base_settings = Settings.from_env()
    probe_database = f"task016_{uuid.uuid4().hex}"
    probe_url = make_url(base_settings.database_url).set(database=probe_database)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {probe_database}")

    monkeypatch.setenv("DATABASE_URL", probe_url.render_as_string(hide_password=False))
    monkeypatch.setenv("PHOTO_UPLOAD_RATE_LIMIT", "2")
    monkeypatch.setenv("PHOTO_UPLOAD_RATE_WINDOW_SECONDS", "60")
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    settings = Settings.from_env()
    object_store = PrivateObjectStore(settings)
    marker = uuid.uuid4().hex
    password = f"task016-password-{marker}"
    photographer = {"username": f"task016-photographer-{marker}", "password": password}
    operator = {"username": f"task016-operator-{marker}", "password": password}
    validation_photographer = {
        "username": f"task016-validation-{marker}",
        "password": password,
    }
    technical_photographer = {
        "username": f"task016-technical-{marker}",
        "password": password,
    }
    target: dict[str, str] = {}

    try:
        ensure_bucket(settings)
        alembic_command.upgrade(Config("alembic.ini"), "head")
        with Session(engine) as database_session:
            revision = PipelineRevisionRepository(database_session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime.now(timezone.utc),
                **PIPELINE_COMPATIBILITY,
            )
            target_record = IngestTargetRepository(database_session).configure_spa(
                name=f"task016-spa-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            database_session.commit()
            target = {"spa_id": str(target_record.spa_id), "visit_date": "2026-08-11"}
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
            provision_staff_user(
                database_session,
                username=validation_photographer["username"],
                password=validation_photographer["password"],
                role=StaffRole.PHOTOGRAPHER,
            )
            provision_staff_user(
                database_session,
                username=technical_photographer["username"],
                password=technical_photographer["password"],
                role=StaffRole.PHOTOGRAPHER,
            )
        yield create_app(), engine, object_store, target, {
            "photographer": photographer,
            "operator": operator,
            "validation": validation_photographer,
            "technical": technical_photographer,
        }
    finally:
        with Session(engine) as database_session:
            keys = set(database_session.scalars(select(Photo.original_object_key)))
        for key in keys:
            object_store.delete(key=key)
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)")
        admin_engine.dispose()


def test_photo_upload_authentication_failure_and_rate_contract(
    disposable_photo_upload_state: tuple[
        FastAPI,
        Engine,
        PrivateObjectStore,
        dict[str, str],
        dict[str, dict[str, str]],
    ],
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, engine, object_store, target, accounts = disposable_photo_upload_state
    photographer = accounts["photographer"]
    operator = accounts["operator"]
    photo = _jpeg()
    body, content_type = _multipart_photo(
        spa_id=target["spa_id"], visit_date=target["visit_date"], photo=photo
    )

    photographer_cookies = _login(app, photographer)
    status, _, response = _request(
        app,
        "POST",
        "/api/inventory/photos",
        body=body,
        content_type=content_type,
        cookies=photographer_cookies,
        headers={"X-CSRF-Token": photographer_cookies["fm_staff_csrf"]},
    )

    assert status == 201
    assert response["schema_version"] == 1
    assert response["outcome"] == "accepted"
    assert response["warnings"] == []
    assert set(response["photo"]) == {
        "photo_id",
        "spa_id",
        "visit_date",
        "accepted_at",
        "captured_at",
        "processing_status",
    }
    assert response["photo"]["spa_id"] == target["spa_id"]
    assert response["photo"]["visit_date"] == target["visit_date"]
    assert response["photo"]["processing_status"] == "pending"
    assert datetime.fromisoformat(response["photo"]["accepted_at"].replace("Z", "+00:00"))

    duplicate_status, _, duplicate = _request(
        app,
        "POST",
        "/api/inventory/photos",
        body=body,
        content_type=content_type,
        cookies=photographer_cookies,
        headers={"X-CSRF-Token": photographer_cookies["fm_staff_csrf"]},
    )
    assert duplicate_status == 200
    assert duplicate == {"schema_version": 1, "outcome": "duplicate", "warnings": []}

    assert _request(app, "POST", "/api/inventory/photos", body=body, content_type=content_type)[0] == 401
    assert (
        _request(
            app,
            "POST",
            "/api/inventory/photos",
            body=body,
            content_type=content_type,
            cookies=photographer_cookies,
        )[0]
        == 403
    )

    operator_cookies = _login(app, operator)
    assert (
        _request(
            app,
            "POST",
            "/api/inventory/photos",
            body=body,
            content_type=content_type,
            cookies=operator_cookies,
            headers={"X-CSRF-Token": operator_cookies["fm_staff_csrf"]},
        )[0]
        == 403
    )

    assert _request(
        app,
        "POST",
        "/api/inventory/photos",
        body=body,
        content_type=content_type,
        cookies=photographer_cookies,
        headers={"X-CSRF-Token": photographer_cookies["fm_staff_csrf"]},
    )[0] == 429

    with Session(engine) as database_session:
        stored_keys = set(database_session.scalars(select(Photo.original_object_key)))
    assert len(stored_keys) == 1
    assert all(key.startswith("candidates/") for key in stored_keys)
    rendered = json.dumps(response) + caplog.text
    for secret in (
        photographer["password"],
        photographer_cookies["fm_staff_session"],
        photographer_cookies["fm_staff_csrf"],
    ):
        assert secret not in rendered
    assert "original_object_key" not in rendered
    assert "minio:9000" not in rendered
    assert "postgres:5432" not in rendered
    assert not any(key in rendered for key in stored_keys)

    caddyfile = Path("deploy/Caddyfile").read_text()
    assert "handle /api/inventory/*" in caddyfile
    assert "minio:9000" not in caddyfile
    assert "postgres:5432" not in caddyfile

    validation_cookies = _login(app, accounts["validation"])
    oversized_body, oversized_content_type = _multipart_photo(
        spa_id=target["spa_id"],
        visit_date=target["visit_date"],
        photo=b"\xff\xd8" + b"x" * 10_485_760,
    )
    assert _request(
        app,
        "POST",
        "/api/inventory/photos",
        body=oversized_body,
        content_type=oversized_content_type,
        cookies=validation_cookies,
        headers={"X-CSRF-Token": validation_cookies["fm_staff_csrf"]},
    )[0] == 413

    invalid_body, invalid_content_type = _multipart_photo(
        spa_id=target["spa_id"],
        visit_date=target["visit_date"],
        photo=b"not-a-jpeg",
        photo_content_type="image/png",
    )
    assert _request(
        app,
        "POST",
        "/api/inventory/photos",
        body=invalid_body,
        content_type=invalid_content_type,
        cookies=validation_cookies,
        headers={"X-CSRF-Token": validation_cookies["fm_staff_csrf"]},
    )[0] == 422

    technical_cookies = _login(app, accounts["technical"])

    def fail_private_stage(*_: object, **__: object) -> None:
        raise RuntimeError("task016-disposable-object-store-failure")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "face_moment.inventory.photo_upload.PrivateObjectStore.put",
            fail_private_stage,
        )
        assert _request(
            app,
            "POST",
            "/api/inventory/photos",
            body=body,
            content_type=content_type,
            cookies=technical_cookies,
            headers={"X-CSRF-Token": technical_cookies["fm_staff_csrf"]},
        )[0] == 500


def _jpeg() -> bytes:
    pixels = np.full((4, 4, 3), 127, dtype=np.uint8)
    encoded_ok, encoded = cv2.imencode(".jpg", pixels)
    assert encoded_ok
    return encoded.tobytes()


def _login(app: FastAPI, credentials: dict[str, str]) -> dict[str, str]:
    status, set_cookies, _ = _request(
        app,
        "POST",
        "/api/staff/sessions",
        body=json.dumps(credentials).encode(),
        content_type="application/json",
    )
    assert status == 204
    cookies: dict[str, str] = {}
    for header in set_cookies:
        parsed = SimpleCookie()
        parsed.load(header)
        cookies.update({name: morsel.value for name, morsel in parsed.items()})
    return cookies


def _multipart_photo(
    *,
    spa_id: str,
    visit_date: str,
    photo: bytes,
    photo_content_type: str = "image/jpeg",
) -> tuple[bytes, str]:
    boundary = f"task016-{uuid.uuid4().hex}"
    fields = [
        _part(boundary, "spa_id", spa_id.encode()),
        _part(boundary, "visit_date", visit_date.encode()),
        _part(
            boundary,
            "photo",
            photo,
            filename="photo.jpg",
            content_type=photo_content_type,
        ),
    ]
    return b"".join(fields) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def _part(
    boundary: str,
    name: str,
    value: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> bytes:
    disposition = f'Content-Disposition: form-data; name="{name}"'
    if filename is not None:
        disposition += f'; filename="{filename}"'
    headers = [f"--{boundary}", disposition]
    if content_type is not None:
        headers.append(f"Content-Type: {content_type}")
    return "\r\n".join(headers).encode() + b"\r\n\r\n" + value + b"\r\n"


def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    body: bytes = b"",
    content_type: str | None = None,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, list[str], dict[str, Any]]:
    request_headers = [(b"host", b"testserver")]
    if content_type is not None:
        request_headers.append((b"content-type", content_type.encode()))
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
        return {"type": "http.request", "body": body, "more_body": False}

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

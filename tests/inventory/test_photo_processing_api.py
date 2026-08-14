from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import event, create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.platform.auth.sessions import StaffSession
from face_moment.processing import InitialPendingRepository, PipelineCode, PipelineRevisionRepository
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace
from face_moment.serving_control import IngestTargetRepository
from face_moment.serving_control.ingest_target import Spa
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@dataclass(frozen=True, slots=True)
class _PhotoCase:
    photo_id: uuid.UUID
    pipeline_revision_id: uuid.UUID
    pipeline_code: str
    processing_status: str
    searchable: bool
    attempt_count: int
    status_changed_at: datetime
    searchable_at: datetime | None
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class _Fixture:
    app: FastAPI
    engine: Engine
    spa_id: uuid.UUID
    admission_revision_id: uuid.UUID
    later_revision_id: uuid.UUID
    photographer_id: uuid.UUID
    cases: tuple[_PhotoCase, ...]
    accounts: dict[str, dict[str, str]]


@pytest.fixture
def disposable_photo_processing_api_state(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_Fixture]:
    base_settings = Settings.from_env()
    probe_database = f"task030_{uuid.uuid4().hex}"
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
    password = f"task030-password-{marker}"
    accounts = {
        "photographer": {
            "username": f"task030-photographer-{marker}",
            "password": password,
        },
        "other_photographer": {
            "username": f"task030-other-photographer-{marker}",
            "password": password,
        },
        "operator": {"username": f"task030-operator-{marker}", "password": password},
        "developer": {"username": f"task030-developer-{marker}", "password": password},
    }

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        with Session(engine) as session:
            current_revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc),
                **PIPELINE_COMPATIBILITY,
            )
            incompatible_revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
                validated_at=datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc),
                **PIPELINE_COMPATIBILITY,
            )
            target = IngestTargetRepository(session).configure_spa(
                name=f"task030-spa-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=current_revision.id,
            )
            session.commit()

        principals = {}
        with Session(engine) as session:
            for account_name, account in accounts.items():
                role = {
                    "photographer": StaffRole.PHOTOGRAPHER,
                    "other_photographer": StaffRole.PHOTOGRAPHER,
                    "operator": StaffRole.OPERATOR,
                    "developer": StaffRole.DEVELOPER,
                }[account_name]
                principals[account_name] = provision_staff_user(
                    session,
                    username=account["username"],
                    password=account["password"],
                    role=role,
                )

        cases = _seed_cases(
            engine,
            marker=marker,
            spa_id=target.spa_id,
            uploader_id=principals["photographer"].staff_user_id,
            current_revision_id=current_revision.id,
            incompatible_revision_id=incompatible_revision.id,
        )
        yield _Fixture(
            app=create_app(),
            engine=engine,
            spa_id=target.spa_id,
            admission_revision_id=current_revision.id,
            later_revision_id=incompatible_revision.id,
            photographer_id=principals["photographer"].staff_user_id,
            cases=cases,
            accounts=accounts,
        )
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)")
        admin_engine.dispose()


def test_per_photo_processing_status_returns_exact_safe_projection_matrix(
    disposable_photo_processing_api_state: _Fixture,
) -> None:
    fixture = disposable_photo_processing_api_state
    photographer_cookies = _login(fixture.app, fixture.accounts["photographer"])

    for case in fixture.cases:
        status_code, _, response = _request(
            fixture.app,
            "GET",
            f"/api/inventory/photos/{case.photo_id}/processing",
            cookies=photographer_cookies,
        )

        assert status_code == 200
        assert set(response) == {
            "schema_version",
            "photo_id",
            "pipeline_revision_id",
            "pipeline_code",
            "processing_status",
            "searchable",
            "attempt_count",
            "status_changed_at",
            "searchable_at",
            "failure_reason",
        }
        assert response == {
            "schema_version": 1,
            "photo_id": str(case.photo_id),
            "pipeline_revision_id": str(case.pipeline_revision_id),
            "pipeline_code": case.pipeline_code,
            "processing_status": case.processing_status,
            "searchable": case.searchable,
            "attempt_count": case.attempt_count,
            "status_changed_at": _utc_z(case.status_changed_at),
            "searchable_at": _utc_z(case.searchable_at),
            "failure_reason": case.failure_reason,
        }
        rendered = json.dumps(response)
        for protected_marker in (
            "original_object_key",
            "preview_object_key",
            "thumbnail_object_key",
            "embedding",
            "landmark",
            "model_path",
            "traceback",
        ):
            assert protected_marker not in rendered


def test_per_photo_processing_status_auth_failure_validation_and_owner_read_failure(
    disposable_photo_processing_api_state: _Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = disposable_photo_processing_api_state
    owned_photo_id = fixture.cases[0].photo_id
    photographer_cookies = _login(fixture.app, fixture.accounts["photographer"])
    other_photographer_cookies = _login(
        fixture.app, fixture.accounts["other_photographer"]
    )
    operator_cookies = _login(fixture.app, fixture.accounts["operator"])
    developer_cookies = _login(fixture.app, fixture.accounts["developer"])

    assert _request(
        fixture.app,
        "GET",
        f"/api/inventory/photos/{owned_photo_id}/processing",
    )[0] == 401
    assert _request(
        fixture.app,
        "GET",
        f"/api/inventory/photos/{owned_photo_id}/processing",
        cookies=other_photographer_cookies,
    )[0] == 403
    assert _request(
        fixture.app,
        "GET",
        f"/api/inventory/photos/{uuid.uuid4()}/processing",
        cookies=photographer_cookies,
    )[0] == 404
    assert _request(
        fixture.app,
        "GET",
        "/api/inventory/photos/not-a-uuid/processing",
        cookies=photographer_cookies,
    )[0] == 422
    assert _request(
        fixture.app,
        "GET",
        f"/api/inventory/photos/{owned_photo_id}/processing",
        cookies=operator_cookies,
    )[0] == 200
    assert _request(
        fixture.app,
        "GET",
        f"/api/inventory/photos/{owned_photo_id}/processing",
        cookies=developer_cookies,
    )[0] == 200

    def fail_owner_read(*_: object, **__: object) -> object:
        raise RuntimeError("task030-disposable-owner-read-failure")

    monkeypatch.setattr(
        "face_moment.inventory.http.read_photo_processing_status", fail_owner_read
    )
    status_code, _, response = _request(
        fixture.app,
        "GET",
        f"/api/inventory/photos/{owned_photo_id}/processing",
        cookies=photographer_cookies,
    )
    assert status_code == 500
    assert response == {"detail": "Internal Server Error"}


def test_per_photo_processing_status_rejects_revoked_session(
    disposable_photo_processing_api_state: _Fixture,
) -> None:
    fixture = disposable_photo_processing_api_state
    cookies = _login(fixture.app, fixture.accounts["photographer"])
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            staff_session = session.query(StaffSession).one()
            staff_session.revoked_at = datetime.now(timezone.utc)
            session.commit()
    finally:
        engine.dispose()

    assert _request(
        fixture.app,
        "GET",
        f"/api/inventory/photos/{fixture.cases[0].photo_id}/processing",
        cookies=cookies,
    )[0] == 401


def test_per_photo_processing_status_uses_immutable_admission_lineage(
    disposable_photo_processing_api_state: _Fixture,
) -> None:
    fixture = disposable_photo_processing_api_state
    photographer_cookies = _login(fixture.app, fixture.accounts["photographer"])
    cases, missing_admission_state_photo_id = _seed_admission_lineage_cases(
        fixture.engine,
        marker=uuid.uuid4().hex,
        spa_id=fixture.spa_id,
        uploader_id=fixture.photographer_id,
        admission_revision_id=fixture.admission_revision_id,
        later_revision_id=fixture.later_revision_id,
    )

    for case in cases:
        status_code, _, response = _request(
            fixture.app,
            "GET",
            f"/api/inventory/photos/{case.photo_id}/processing",
            cookies=photographer_cookies,
        )
        assert status_code == 200
        assert response == _status_response(case, searchable=True)

    with Session(fixture.engine) as session:
        spa = session.get(Spa, fixture.spa_id)
        assert spa is not None
        spa.serving_pipeline_revision_id = fixture.later_revision_id
        session.commit()

    statements: list[str] = []

    def capture_sql(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", capture_sql)
    try:
        for case in cases:
            status_code, _, response = _request(
                fixture.app,
                "GET",
                f"/api/inventory/photos/{case.photo_id}/processing",
                cookies=photographer_cookies,
            )
            assert status_code == 200
            assert response == _status_response(case, searchable=False)

        assert _request(
            fixture.app,
            "GET",
            f"/api/inventory/photos/{missing_admission_state_photo_id}/processing",
            cookies=photographer_cookies,
        )[0] == 500
    finally:
        event.remove(Engine, "before_cursor_execute", capture_sql)

    assert statements
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)


def test_per_photo_processing_status_uses_only_inventory_and_public_processing_boundary() -> None:
    transport_source = (Path("src/face_moment/inventory/http.py")).read_text()
    outcome_source = (
        Path("src/face_moment/inventory/photo_processing_status.py")
    ).read_text()

    assert "read_photo_processing_status" in transport_source
    assert "PhotoPipelineState" not in transport_source
    assert "SearchableProjectionRepository" not in transport_source
    assert "read_photo_processing_projection" in outcome_source
    assert "SearchableProjectionRepository" not in outcome_source
    assert "admission_pipeline_revision_id" in outcome_source


def _seed_cases(
    engine: Engine,
    *,
    marker: str,
    spa_id: uuid.UUID,
    uploader_id: uuid.UUID,
    current_revision_id: uuid.UUID,
    incompatible_revision_id: uuid.UUID,
) -> tuple[_PhotoCase, ...]:
    now = datetime(2026, 8, 14, 8, 15, tzinfo=timezone.utc)
    definitions = (
        ("pending", current_revision_id, "opencv_sface", "pending", True, False, None),
        ("processing", current_revision_id, "opencv_sface", "processing", True, False, None),
        ("ready", current_revision_id, "opencv_sface", "ready", True, True, None),
        ("no-faces", current_revision_id, "opencv_sface", "no_faces", True, False, None),
        (
            "failed",
            current_revision_id,
            "opencv_sface",
            "failed",
            True,
            False,
            "retry limit reached",
        ),
        (
            "incompatible-ready",
            incompatible_revision_id,
            "insightface_buffalo_m",
            "ready",
            True,
            True,
            None,
        ),
        (
            "inactive-ready",
            current_revision_id,
            "opencv_sface",
            "ready",
            False,
            True,
            None,
        ),
    )
    cases: list[_PhotoCase] = []
    with Session(engine) as session:
        for index, (
            name,
            revision_id,
            pipeline_code,
            processing_status,
            is_active,
            complete_ready,
            failure_reason,
        ) in enumerate(definitions, start=1):
            status_changed_at = now + timedelta(seconds=index)
            searchable_at = status_changed_at if processing_status == "ready" else None
            photo = Photo(
                spa_id=spa_id,
                visit_date=date(2026, 8, 14),
                captured_at=now,
                captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
                admission_pipeline_revision_id=revision_id,
                uploader_id=uploader_id,
                checksum_sha256=hashlib.sha256(f"{marker}-{name}".encode()).digest(),
                original_object_key=f"private/task030/{marker}/{name}/original.jpg",
                original_byte_size=123,
                width=12,
                height=10,
                is_active=is_active,
            )
            session.add(photo)
            session.flush()
            state = InitialPendingRepository(session).create_initial_pending(
                photo_id=photo.id,
                pipeline_revision_id=revision_id,
            )
            state.status = processing_status
            state.attempt_count = index
            state.status_changed_at = status_changed_at
            state.searchable_at = searchable_at
            state.last_error = failure_reason
            if complete_ready:
                state.preview_object_key = f"private/task030/{marker}/{name}/preview.jpg"
                state.thumbnail_object_key = f"private/task030/{marker}/{name}/thumbnail.jpg"
                session.add(
                    PhotoFace(
                        photo_id=photo.id,
                        pipeline_revision_id=revision_id,
                        face_index=0,
                        bbox_x=1.0,
                        bbox_y=1.0,
                        bbox_w=4.0,
                        bbox_h=4.0,
                        landmarks_json=[[1.0, 1.0]] * 5,
                        detection_confidence=0.9,
                        embedding=[1.0] + [0.0] * 127,
                    )
                )
            cases.append(
                _PhotoCase(
                    photo_id=photo.id,
                    pipeline_revision_id=revision_id,
                    pipeline_code=pipeline_code,
                    processing_status=processing_status,
                    searchable=complete_ready
                    and is_active
                    and revision_id == current_revision_id,
                    attempt_count=index,
                    status_changed_at=status_changed_at,
                    searchable_at=searchable_at,
                    failure_reason=failure_reason,
                )
            )
        session.commit()
    return tuple(cases)


def _seed_admission_lineage_cases(
    engine: Engine,
    *,
    marker: str,
    spa_id: uuid.UUID,
    uploader_id: uuid.UUID,
    admission_revision_id: uuid.UUID,
    later_revision_id: uuid.UUID,
) -> tuple[tuple[_PhotoCase, ...], uuid.UUID]:
    now = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)
    cases: list[_PhotoCase] = []
    with Session(engine) as session:
        extra_revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=now,
            **PIPELINE_COMPATIBILITY,
        )
        for index, (name, later_status, has_extra_later_row) in enumerate(
            (
                ("absent-b", None, False),
                ("pending-b", "pending", False),
                ("ready-b", "ready", False),
                ("ready-b-plus-c", "ready", True),
            ),
            start=1,
        ):
            status_changed_at = now + timedelta(seconds=index)
            photo = _new_lineage_photo(
                spa_id=spa_id,
                uploader_id=uploader_id,
                marker=marker,
                name=name,
                admission_revision_id=admission_revision_id,
                captured_at=now,
            )
            session.add(photo)
            session.flush()
            admission_state = InitialPendingRepository(session).create_initial_pending(
                photo_id=photo.id,
                pipeline_revision_id=admission_revision_id,
            )
            admission_state.status = "ready"
            admission_state.attempt_count = index
            admission_state.status_changed_at = status_changed_at
            admission_state.searchable_at = status_changed_at
            admission_state.preview_object_key = f"private/task038/{marker}/{name}/a-preview.jpg"
            admission_state.thumbnail_object_key = f"private/task038/{marker}/{name}/a-thumbnail.jpg"
            session.add(
                PhotoFace(
                    photo_id=photo.id,
                    pipeline_revision_id=admission_revision_id,
                    face_index=0,
                    bbox_x=1.0,
                    bbox_y=1.0,
                    bbox_w=4.0,
                    bbox_h=4.0,
                    landmarks_json=[[1.0, 1.0]] * 5,
                    detection_confidence=0.9,
                    embedding=[1.0] + [0.0] * 127,
                )
            )
            if later_status is not None:
                later_state = InitialPendingRepository(session).create_initial_pending(
                    photo_id=photo.id,
                    pipeline_revision_id=later_revision_id,
                )
                later_state.status = later_status
                later_state.attempt_count = 100 + index
                later_state.status_changed_at = now + timedelta(minutes=index)
                if later_status == "ready":
                    later_state.searchable_at = later_state.status_changed_at
                    later_state.preview_object_key = f"private/task038/{marker}/{name}/b-preview.jpg"
                    later_state.thumbnail_object_key = f"private/task038/{marker}/{name}/b-thumbnail.jpg"
                    session.add(
                        PhotoFace(
                            photo_id=photo.id,
                            pipeline_revision_id=later_revision_id,
                            face_index=0,
                            bbox_x=1.0,
                            bbox_y=1.0,
                            bbox_w=4.0,
                            bbox_h=4.0,
                            landmarks_json=[[1.0, 1.0]] * 5,
                            detection_confidence=0.9,
                            embedding=[1.0] + [0.0] * 127,
                        )
                    )
            if has_extra_later_row:
                extra_state = InitialPendingRepository(session).create_initial_pending(
                    photo_id=photo.id,
                    pipeline_revision_id=extra_revision.id,
                )
                extra_state.status = "failed"
                extra_state.attempt_count = 200 + index
                extra_state.status_changed_at = now + timedelta(minutes=2)
                extra_state.last_error = "later row must be ignored"
            cases.append(
                _PhotoCase(
                    photo_id=photo.id,
                    pipeline_revision_id=admission_revision_id,
                    pipeline_code="opencv_sface",
                    processing_status="ready",
                    searchable=True,
                    attempt_count=index,
                    status_changed_at=status_changed_at,
                    searchable_at=status_changed_at,
                    failure_reason=None,
                )
            )

        missing_admission_state = _new_lineage_photo(
            spa_id=spa_id,
            uploader_id=uploader_id,
            marker=marker,
            name="missing-a",
            admission_revision_id=admission_revision_id,
            captured_at=now,
        )
        session.add(missing_admission_state)
        session.flush()
        later_state = InitialPendingRepository(session).create_initial_pending(
            photo_id=missing_admission_state.id,
            pipeline_revision_id=later_revision_id,
        )
        later_state.status = "ready"
        later_state.attempt_count = 999
        later_state.status_changed_at = now + timedelta(minutes=5)
        missing_admission_state_photo_id = missing_admission_state.id
        session.commit()
    return tuple(cases), missing_admission_state_photo_id


def _new_lineage_photo(
    *,
    spa_id: uuid.UUID,
    uploader_id: uuid.UUID,
    marker: str,
    name: str,
    admission_revision_id: uuid.UUID,
    captured_at: datetime,
) -> Photo:
    return Photo(
        spa_id=spa_id,
        visit_date=date(2026, 8, 14),
        captured_at=captured_at,
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        admission_pipeline_revision_id=admission_revision_id,
        uploader_id=uploader_id,
        checksum_sha256=hashlib.sha256(f"{marker}-{name}".encode()).digest(),
        original_object_key=f"private/task038/{marker}/{name}/original.jpg",
        original_byte_size=123,
        width=12,
        height=10,
        is_active=True,
    )


def _status_response(case: _PhotoCase, *, searchable: bool) -> dict[str, object]:
    return {
        "schema_version": 1,
        "photo_id": str(case.photo_id),
        "pipeline_revision_id": str(case.pipeline_revision_id),
        "pipeline_code": case.pipeline_code,
        "processing_status": case.processing_status,
        "searchable": searchable,
        "attempt_count": case.attempt_count,
        "status_changed_at": _utc_z(case.status_changed_at),
        "searchable_at": _utc_z(case.searchable_at),
        "failure_reason": case.failure_reason,
    }


def _login(app: FastAPI, credentials: dict[str, str]) -> dict[str, str]:
    status_code, set_cookies, _ = _request(
        app,
        "POST",
        "/api/staff/sessions",
        body=json.dumps(credentials).encode(),
        content_type="application/json",
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
    body: bytes = b"",
    content_type: str | None = None,
    cookies: dict[str, str] | None = None,
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


def _utc_z(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

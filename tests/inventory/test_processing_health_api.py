from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import uuid
from urllib.parse import urlencode

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure import capacity
from face_moment.infrastructure.capacity import CapacityObservation
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.platform.auth.sessions import (
    LoginRateLimiter,
    create_browser_session,
)
from face_moment.processing.health_projection import ProcessingHealthProjectionRepository
from face_moment.processing.initial_pending import InitialPendingRepository
from face_moment.processing.persistence import PhotoFace, ProcessingRuntimeStatus
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control.ingest_target import IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@dataclass(frozen=True, slots=True)
class _Fixture:
    app: FastAPI
    engine: Engine
    spa_id: uuid.UUID
    unknown_spa_id: uuid.UUID
    accepted_from: datetime
    accepted_before: datetime
    empty_from: datetime
    empty_before: datetime
    expected_oldest_pending: datetime
    expected_runtime: tuple[datetime, datetime, datetime]
    accounts: dict[str, dict[str, str]]
    protected_marker: str


@pytest.fixture
def disposable_processing_health_api_state(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_Fixture]:
    base_settings = Settings.from_env()
    probe_database = f"task035_{uuid.uuid4().hex}"
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
    protected_marker = f"task035-protected-{marker}"
    password = f"task035-password-{marker}"
    accounts = {
        "operator": {"username": f"task035-operator-{marker}", "password": password},
        "developer": {"username": f"task035-developer-{marker}", "password": password},
        "photographer": {
            "username": f"task035-photographer-{marker}",
            "password": password,
        },
    }
    now = datetime.now(UTC).replace(microsecond=0)
    accepted_from = now - timedelta(minutes=30)
    accepted_before = now + timedelta(minutes=1)

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=now,
                **PIPELINE_COMPATIBILITY,
            )
            target = IngestTargetRepository(session).configure_spa(
                name=f"task035-spa-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            principals = {
                name: provision_staff_user(
                    session,
                    username=account["username"],
                    password=account["password"],
                    role={
                        "operator": StaffRole.OPERATOR,
                        "developer": StaffRole.DEVELOPER,
                        "photographer": StaffRole.PHOTOGRAPHER,
                    }[name],
                )
                for name, account in accounts.items()
            }
            _seed_projection(
                session,
                spa_id=target.spa_id,
                revision_id=revision.id,
                uploader_id=principals["photographer"].staff_user_id,
                now=now,
                protected_marker=protected_marker,
            )
            runtime = session.get(ProcessingRuntimeStatus, 1)
            assert runtime is not None
            worker_started_at = now - timedelta(hours=2)
            last_recovery_at = now - timedelta(hours=1)
            operation_started_at = now - timedelta(minutes=2)
            runtime.worker_started_at = worker_started_at
            runtime.last_recovery_at = last_recovery_at
            runtime.last_recovered_count = 3
            runtime.current_operation = "calibration"
            runtime.operation_started_at = operation_started_at
            session.commit()

        yield _Fixture(
            app=create_app(),
            engine=engine,
            spa_id=target.spa_id,
            unknown_spa_id=uuid.uuid4(),
            accepted_from=accepted_from,
            accepted_before=accepted_before,
            empty_from=now + timedelta(days=1),
            empty_before=now + timedelta(days=2),
            expected_oldest_pending=now - timedelta(minutes=25),
            expected_runtime=(worker_started_at, last_recovery_at, operation_started_at),
            accounts=accounts,
            protected_marker=protected_marker,
        )
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)")
        admin_engine.dispose()


def test_processing_health_assembles_exact_owner_projections(
    disposable_processing_health_api_state: _Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = disposable_processing_health_api_state
    settings = Settings.from_env()
    observed_at = datetime.now(UTC).replace(microsecond=0)
    observations = {
        settings.postgresql_capacity_view_path: CapacityObservation(
            status="ok",
            available_bytes=8192,
            low_threshold_bytes=settings.postgresql_capacity_low_threshold_bytes,
            observed_at=observed_at,
            error=None,
        ),
        settings.minio_capacity_view_path: CapacityObservation(
            status="low",
            available_bytes=1024,
            low_threshold_bytes=settings.minio_capacity_low_threshold_bytes,
            observed_at=observed_at,
            error=None,
        ),
    }
    monkeypatch.setattr(
        capacity,
        "observe_capacity",
        lambda view_path, *, low_threshold_bytes: observations[view_path],
    )
    cookies = _cookies(fixture.engine, fixture.accounts["operator"])

    status_code, _, response = _request(
        fixture.app,
        "/api/inventory/processing-health",
        params={"spa_id": str(fixture.spa_id)},
        cookies=cookies,
    )

    assert status_code == 200
    assert set(response) == {
        "schema_version",
        "spa_id",
        "observed_at",
        "queue",
        "ingest_to_searchable",
        "storage",
    }
    assert response["schema_version"] == 1
    assert response["spa_id"] == str(fixture.spa_id)
    assert _as_utc(response["observed_at"]) >= observed_at - timedelta(seconds=1)
    assert response["ingest_to_searchable"] is None
    assert response["queue"] == {
        "pending": 1,
        "processing": 1,
        "ready": 2,
        "no_faces": 1,
        "failed": 1,
        "oldest_pending_accepted_at": _z(fixture.expected_oldest_pending),
        "current_operation": "calibration",
        "operation_started_at": _z(fixture.expected_runtime[2]),
        "worker_started_at": _z(fixture.expected_runtime[0]),
        "last_recovery_at": _z(fixture.expected_runtime[1]),
        "last_recovered_count": 3,
    }
    assert response["storage"] == {
        "postgresql": _capacity_response(observations[settings.postgresql_capacity_view_path]),
        "minio": _capacity_response(observations[settings.minio_capacity_view_path]),
    }
    assert fixture.protected_marker not in json.dumps(response)

    status_code, _, response = _request(
        fixture.app,
        "/api/inventory/processing-health",
        params={
            "spa_id": str(fixture.spa_id),
            "accepted_from": _z(fixture.accepted_from),
            "accepted_before": _z(fixture.accepted_before),
        },
        cookies=cookies,
    )
    assert status_code == 200
    assert response["ingest_to_searchable"] == {
        "accepted_from": _z(fixture.accepted_from),
        "accepted_before": _z(fixture.accepted_before),
        "population": 6,
        "success_under_15_minutes": 1,
        "breach": 4,
        "open": 1,
        "success_ratio": 1 / 6,
        "meets_95_percent": None,
    }

    status_code, _, response = _request(
        fixture.app,
        "/api/inventory/processing-health",
        params={
            "spa_id": str(fixture.spa_id),
            "accepted_from": _z(fixture.empty_from),
            "accepted_before": _z(fixture.empty_before),
        },
        cookies=cookies,
    )
    assert status_code == 200
    assert response["ingest_to_searchable"] == {
        "accepted_from": _z(fixture.empty_from),
        "accepted_before": _z(fixture.empty_before),
        "population": 0,
        "success_under_15_minutes": 0,
        "breach": 0,
        "open": 0,
        "success_ratio": None,
        "meets_95_percent": None,
    }


def test_processing_health_preserves_access_validation_and_independent_store_results(
    disposable_processing_health_api_state: _Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = disposable_processing_health_api_state
    settings = Settings.from_env()
    observed_at = datetime.now(UTC).replace(microsecond=0)
    observations = {
        settings.postgresql_capacity_view_path: CapacityObservation(
            status="unavailable",
            available_bytes=None,
            low_threshold_bytes=settings.postgresql_capacity_low_threshold_bytes,
            observed_at=observed_at,
            error="capacity observation unavailable",
        ),
        settings.minio_capacity_view_path: CapacityObservation(
            status="ok",
            available_bytes=16384,
            low_threshold_bytes=settings.minio_capacity_low_threshold_bytes,
            observed_at=observed_at,
            error=None,
        ),
    }
    monkeypatch.setattr(
        capacity,
        "observe_capacity",
        lambda view_path, *, low_threshold_bytes: observations[view_path],
    )
    operator_cookies = _cookies(fixture.engine, fixture.accounts["operator"])
    developer_cookies = _cookies(fixture.engine, fixture.accounts["developer"])
    photographer_cookies = _cookies(fixture.engine, fixture.accounts["photographer"])

    for cookies, expected_status in (
        (None, 401),
        (photographer_cookies, 403),
    ):
        assert _request(
            fixture.app,
            "/api/inventory/processing-health",
            params={"spa_id": str(fixture.spa_id)},
            cookies=cookies,
        )[0] == expected_status

    status_code, _, response = _request(
        fixture.app,
        "/api/inventory/processing-health",
        params={"spa_id": str(fixture.spa_id)},
        cookies=developer_cookies,
    )
    assert status_code == 200
    assert response["storage"] == {
        "postgresql": _capacity_response(observations[settings.postgresql_capacity_view_path]),
        "minio": _capacity_response(observations[settings.minio_capacity_view_path]),
    }

    observations[settings.postgresql_capacity_view_path] = CapacityObservation(
        status="low",
        available_bytes=1,
        low_threshold_bytes=settings.postgresql_capacity_low_threshold_bytes,
        observed_at=observed_at,
        error=None,
    )
    observations[settings.minio_capacity_view_path] = CapacityObservation(
        status="unavailable",
        available_bytes=None,
        low_threshold_bytes=settings.minio_capacity_low_threshold_bytes,
        observed_at=observed_at,
        error="capacity observation unavailable",
    )
    status_code, _, response = _request(
        fixture.app,
        "/api/inventory/processing-health",
        params={"spa_id": str(fixture.spa_id)},
        cookies=operator_cookies,
    )
    assert status_code == 200
    assert response["storage"] == {
        "postgresql": _capacity_response(observations[settings.postgresql_capacity_view_path]),
        "minio": _capacity_response(observations[settings.minio_capacity_view_path]),
    }

    for params, expected_status in (
        ({"spa_id": "not-a-uuid"}, 422),
        (
            {
                "spa_id": str(fixture.spa_id),
                "accepted_from": _z(fixture.accepted_from),
            },
            422,
        ),
        (
            {
                "spa_id": str(fixture.spa_id),
                "accepted_from": _z(fixture.accepted_from),
                "accepted_before": _z(fixture.accepted_from),
            },
            422,
        ),
        (
            {
                "spa_id": str(fixture.spa_id),
                "accepted_from": _z(fixture.accepted_before),
                "accepted_before": _z(fixture.accepted_from),
            },
            422,
        ),
        (
            {
                "spa_id": str(fixture.spa_id),
                "accepted_from": fixture.accepted_from.replace(tzinfo=None).isoformat(),
                "accepted_before": _z(fixture.accepted_before),
            },
            422,
        ),
        (
            {
                "spa_id": str(fixture.spa_id),
                "accepted_from": _z(fixture.accepted_from),
                "accepted_before": fixture.accepted_before.replace(tzinfo=None).isoformat(),
            },
            422,
        ),
        ({"spa_id": str(fixture.unknown_spa_id)}, 404),
    ):
        assert _request(
            fixture.app,
            "/api/inventory/processing-health",
            params=params,
            cookies=operator_cookies,
        )[0] == expected_status


def test_processing_health_maps_owner_failure_without_handler_writes(
    disposable_processing_health_api_state: _Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = disposable_processing_health_api_state
    cookies = _cookies(fixture.engine, fixture.accounts["operator"])

    def fail_owner_read(
        _self: ProcessingHealthProjectionRepository, *, spa_id: uuid.UUID
    ) -> object:
        raise RuntimeError("synthetic owner read failure")

    monkeypatch.setattr(ProcessingHealthProjectionRepository, "resolve", fail_owner_read)
    status_code, _, response = _request(
        fixture.app,
        "/api/inventory/processing-health",
        params={"spa_id": str(fixture.spa_id)},
        cookies=cookies,
    )
    assert status_code == 500
    assert response == {"detail": "Internal Server Error"}

    transport_source = Path("src/face_moment/inventory/http.py").read_text()
    outcome_source = Path("src/face_moment/inventory/processing_health.py").read_text()
    assert "read_processing_health" in transport_source
    assert "ProcessingHealthProjectionRepository" not in transport_source
    assert "PhotoPipelineState" not in outcome_source
    assert ".commit(" not in outcome_source
    assert ".add(" not in outcome_source
    assert fixture.protected_marker not in transport_source + outcome_source


def _seed_projection(
    session: Session,
    *,
    spa_id: uuid.UUID,
    revision_id: uuid.UUID,
    uploader_id: uuid.UUID,
    now: datetime,
    protected_marker: str,
) -> None:
    _add_photo_state(
        session,
        spa_id=spa_id,
        revision_id=revision_id,
        uploader_id=uploader_id,
        marker=f"{protected_marker}-success",
        accepted_at=now - timedelta(minutes=10),
        status="ready",
        searchable_at=now - timedelta(minutes=5),
        complete=True,
    )
    _add_photo_state(
        session,
        spa_id=spa_id,
        revision_id=revision_id,
        uploader_id=uploader_id,
        marker=f"{protected_marker}-ready-breach",
        accepted_at=now - timedelta(minutes=20),
        status="ready",
        searchable_at=now - timedelta(minutes=1),
        complete=True,
    )
    _add_photo_state(
        session,
        spa_id=spa_id,
        revision_id=revision_id,
        uploader_id=uploader_id,
        marker=f"{protected_marker}-no-faces",
        accepted_at=now - timedelta(minutes=21),
        status="no_faces",
    )
    _add_photo_state(
        session,
        spa_id=spa_id,
        revision_id=revision_id,
        uploader_id=uploader_id,
        marker=f"{protected_marker}-failed",
        accepted_at=now - timedelta(minutes=22),
        status="failed",
    )
    _add_photo_state(
        session,
        spa_id=spa_id,
        revision_id=revision_id,
        uploader_id=uploader_id,
        marker=f"{protected_marker}-pending",
        accepted_at=now - timedelta(minutes=25),
        status="pending",
    )
    _add_photo_state(
        session,
        spa_id=spa_id,
        revision_id=revision_id,
        uploader_id=uploader_id,
        marker=f"{protected_marker}-processing",
        accepted_at=now - timedelta(minutes=5),
        status="processing",
    )


def _add_photo_state(
    session: Session,
    *,
    spa_id: uuid.UUID,
    revision_id: uuid.UUID,
    uploader_id: uuid.UUID,
    marker: str,
    accepted_at: datetime,
    status: str,
    searchable_at: datetime | None = None,
    complete: bool = False,
) -> None:
    photo = Photo(
        spa_id=spa_id,
        visit_date=date(2026, 8, 14),
        captured_at=accepted_at,
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        accepted_at=accepted_at,
        admission_pipeline_revision_id=revision_id,
        uploader_id=uploader_id,
        checksum_sha256=hashlib.sha256(marker.encode()).digest(),
        original_object_key=f"private/{marker}/original.jpg",
        original_byte_size=123,
        width=12,
        height=10,
        is_active=True,
    )
    session.add(photo)
    session.flush()
    state = InitialPendingRepository(session).create_initial_pending(
        photo_id=photo.id,
        pipeline_revision_id=revision_id,
    )
    state.status = status
    state.status_changed_at = searchable_at or accepted_at
    state.searchable_at = searchable_at
    if complete:
        state.preview_object_key = f"private/{marker}/preview.jpg"
        state.thumbnail_object_key = f"private/{marker}/thumbnail.jpg"
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
    start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return start["status"], {}, json.loads(body or b"{}")


def _capacity_response(observation: CapacityObservation) -> dict[str, object]:
    return {
        "status": observation.status,
        "available_bytes": observation.available_bytes,
        "low_threshold_bytes": observation.low_threshold_bytes,
        "observed_at": _z(observation.observed_at),
        "error": observation.error,
    }


def _z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _as_utc(value: object) -> datetime:
    assert isinstance(value, str)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)

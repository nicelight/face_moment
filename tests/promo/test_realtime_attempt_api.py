from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from typing import Any
import uuid

import cv2
import numpy as np
import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints import realtime
from face_moment.infrastructure.settings import Settings
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.promo import PromoAttempt
from face_moment.serving_control import IngestTargetRepository
from face_moment.serving_control.display_client_access import DisplayClientRepository
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from face_moment.serving_control.realtime_context import RealtimeContextRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@pytest.fixture
def realtime_state(monkeypatch: pytest.MonkeyPatch) -> Any:
    base_settings = Settings.from_env()
    probe_database = f"task045_{uuid.uuid4().hex}"
    probe_url = make_url(base_settings.database_url).set(database=probe_database)
    admin_engine = create_engine(
        base_settings.database_url, pool_pre_ping=True, isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {probe_database}")
    monkeypatch.setenv("DATABASE_URL", probe_url.render_as_string(hide_password=False))
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime.now(timezone.utc),
                **PIPELINE_COMPATIBILITY,
            )
            target = IngestTargetRepository(session).configure_spa(
                name=f"task045-{uuid.uuid4().hex}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            context_repository = RealtimeContextRepository(session)
            context_repository.update_active_visit_date(
                spa_id=target.spa_id, active_visit_date=datetime(2026, 8, 18).date()
            )
            context_repository.provision_reference_settings(
                spa_id=target.spa_id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
                reference_threshold=0.6,
                min_query_face_quality=0.5,
                quality_settings={"jpeg_quality": 85},
            )
            display_client = DisplayClientRepository(session).provision(
                spa_id=target.spa_id, name="task045-kiosk"
            )
            session.commit()
            token = display_client.token_value
            spa_id = target.spa_id
        app = realtime.create_app()
        app.state.role_state.update(
            {
                "ready": True,
                "session_factory": lambda: Session(engine),
                "admitted_pipeline_revision_id": revision.id,
                "display_client_rate_limiter": DisplayClientRateLimiter(
                    limit=100, window_seconds=60
                ),
            }
        )
        yield app, engine, spa_id, token
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)"
            )
        admin_engine.dispose()


def test_realtime_attempt_admits_zero_proposals_and_is_idempotent(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str]
) -> None:
    app, engine, spa_id, token = realtime_state
    attempt_id = uuid.uuid4()
    body, content_type = _multipart(_manifest(attempt_id, occurrences=[]))
    first = _request(app, body, content_type, token)
    second = _request(app, body, content_type, token)

    assert first[0] == second[0] == 200
    assert first[2]["outcome"] == second[2]["outcome"] == "no_proposals"
    assert first[2]["attempt_id"] == second[2]["attempt_id"]
    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(PromoAttempt).where(
                    PromoAttempt.spa_id == spa_id,
                    PromoAttempt.client_attempt_id == attempt_id,
                )
            )
        )
    assert len(rows) == 1
    assert rows[0].proposal_count == 0
    assert rows[0].processing_status == "no_success"
    assert rows[0].domain_outcome == "no_proposals"


def test_realtime_attempt_rejects_invalid_payload_without_attempt(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str]
) -> None:
    app, engine, _, token = realtime_state
    manifest = _manifest(uuid.uuid4(), occurrences=[])
    manifest["unexpected"] = True
    body, content_type = _multipart(manifest)
    status, _, _ = _request(app, body, content_type, token)

    assert status == 422
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PromoAttempt)) == 0


def test_realtime_attempt_maps_auth_failure_before_admission(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str]
) -> None:
    app, engine, _, _ = realtime_state
    body, content_type = _multipart(_manifest(uuid.uuid4(), occurrences=[]))

    status, _, _ = _request(app, body, content_type, token=None)

    assert status == 401
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PromoAttempt)) == 0


def test_realtime_attempt_maps_closed_readiness_before_admission(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str]
) -> None:
    app, engine, _, token = realtime_state
    app.state.role_state["admitted_pipeline_revision_id"] = uuid.uuid4()
    body, content_type = _multipart(_manifest(uuid.uuid4(), occurrences=[]))

    status, _, _ = _request(app, body, content_type, token)

    assert status == 503
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PromoAttempt)) == 0


def test_realtime_attempt_rejects_body_over_exact_cap_before_admission(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str]
) -> None:
    app, engine, _, _ = realtime_state
    body = b"x" * (20_971_520 + 1)

    status, _, _ = _request(
        app, body, "multipart/form-data; boundary=unused", token=None
    )

    assert status == 413
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PromoAttempt)) == 0


def test_realtime_attempt_admits_exact_body_limit_before_nonzero_seam(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str]
) -> None:
    app, engine, _, token = realtime_state
    attempt_id = uuid.uuid4()
    manifest = _manifest(attempt_id, occurrences=[_occurrence(0)])
    crop = _jpeg()
    body, content_type = _multipart(manifest, crops=[crop])
    crop = crop + b"\x00" * (20_971_520 - len(body))
    body, content_type = _multipart(manifest, crops=[crop])
    assert len(body) == 20_971_520

    status, _, _ = _request(app, body, content_type, token)

    assert status == 500
    with Session(engine) as session:
        row = session.scalar(
            select(PromoAttempt).where(PromoAttempt.client_attempt_id == attempt_id)
        )
    assert row is not None
    assert row.processing_status == "internal_failure"
    assert row.domain_outcome is None


def _manifest(attempt_id: uuid.UUID, *, occurrences: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "attempt_id": str(attempt_id),
        "trigger_source": "test",
        "client_release": "task045-test",
        "detector_id": "mediapipe_blazeface_full_range",
        "model_version": "blazeface-full-range-1",
        "jpeg_quality": 0.85,
        "camera_device_id": "task045-camera",
        "timing": {
            "reference_series_ready_at": "2026-08-18T10:00:00.000Z",
            "local_detection_completed_ms": 10,
            "request_started_ms": 20,
        },
        "occurrences": occurrences,
    }


def _occurrence(index: int) -> dict[str, Any]:
    return {
        "occurrence_index": index,
        "frame_index": index,
        "frame_offset_ms": index * 10,
        "detector_confidence": 0.9,
        "crop_part": f"crop_{index:03d}",
    }


def _jpeg() -> bytes:
    image = np.zeros((32, 32, 3), dtype=np.uint8)
    image[:, :, 1] = 120
    encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])[1]
    return encoded.tobytes()


def _multipart(manifest: dict[str, Any], *, crops: list[bytes] | None = None) -> tuple[bytes, str]:
    boundary = "task045-boundary"
    fields = [
        (
            b'--' + boundary.encode() + b'\r\n'
            b'Content-Disposition: form-data; name="manifest"\r\n'
            b'Content-Type: application/json; charset=utf-8\r\n\r\n'
            + json.dumps(manifest, separators=(",", ":")).encode()
            + b"\r\n"
        )
    ]
    for index, crop in enumerate(crops or []):
        name = f"crop_{index:03d}"
        fields.append(
            (
                b"--"
                + boundary.encode()
                + f'\r\nContent-Disposition: form-data; name="{name}"; filename="{name}.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()
                + crop
                + b"\r\n"
            )
        )
    return b"".join(fields) + b"--" + boundary.encode() + b"--\r\n", f"multipart/form-data; boundary={boundary}"


def _request(
    app: FastAPI, body: bytes, content_type: str, token: str | None
) -> tuple[int, dict[str, str], dict[str, Any]]:
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

    headers = [(b"host", b"testserver"), (b"content-type", content_type.encode()), (b"content-length", str(len(body)).encode())]
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "https",
                "path": "/api/realtime/attempts",
                "raw_path": b"/api/realtime/attempts",
                "query_string": b"",
                "headers": headers,
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
    return int(start["status"]), {}, json.loads(response_body or b"{}")

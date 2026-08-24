from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, timezone
import json
from typing import Any, Callable
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
from face_moment.processing import (
    DetectionSearchObservation,
    PhotoMatchObservation,
    PipelineCode,
    PipelineRevisionRepository,
    RealtimeSearchResult,
)
from face_moment.promo import PromoAttempt, PromoSession
from face_moment.serving_control import IngestTargetRepository
from face_moment.serving_control.display_client_access import DisplayClientRepository
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from face_moment.serving_control.realtime_context import RealtimeContextRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@pytest.fixture
def realtime_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[FastAPI, Engine, uuid.UUID, str]]:
    base_settings = Settings.from_env()
    probe_database = f"task075_{uuid.uuid4().hex}"
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
                name=f"task075-{uuid.uuid4().hex}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            context = RealtimeContextRepository(session)
            context.update_active_visit_date(
                spa_id=target.spa_id, active_visit_date=datetime(2026, 8, 22).date()
            )
            context.provision_reference_settings(
                spa_id=target.spa_id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
                reference_threshold=0.6,
                min_query_face_quality=0.5,
                quality_settings={"version": 1},
            )
            display_client = DisplayClientRepository(session).provision(
                spa_id=target.spa_id, name="task075-kiosk"
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
                "model_adapter": object(),
                "object_store": object(),
                "qr_ticket_secret": "task075-disposable-qr-secret",
                "realtime_deadline_ms": 3000,
                "realtime_result_display_ms": 15000,
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


def test_result_route_publishes_v1_and_terminal_repeat_without_second_search(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, engine, spa_id, token = realtime_state
    calls: list[str] = []

    def search(**_: object) -> RealtimeSearchResult:
        calls.append("search")
        return _successful_search_result()

    monkeypatch.setattr(realtime, "search_realtime_references", search)
    attempt_id = uuid.uuid4()
    body, content_type = _multipart(_manifest(attempt_id, count=2))

    first = _request(app, body, content_type, token)
    second = _request(app, body, content_type, token)

    assert first[0] == second[0] == 200
    assert first[2] == second[2]
    assert set(first[2]) == {"schema_version", "attempt_id", "outcome", "result"}
    assert first[2]["attempt_id"] == str(attempt_id)
    result = first[2]["result"]
    assert set(result) == {
        "session_id",
        "teasers",
        "n",
        "qr_url",
        "qr_first_open_expires_at",
    }
    assert len(result["teasers"]) == 4
    assert len({item["photo_id"] for item in result["teasers"]}) == 4
    assert result["n"] == 5
    assert result["qr_url"].startswith("/q?ticket=")
    assert calls == ["search"]

    with Session(engine) as session:
        attempt = session.scalar(
            select(PromoAttempt).where(
                PromoAttempt.spa_id == spa_id,
                PromoAttempt.client_attempt_id == attempt_id,
            )
        )
        assert attempt is not None
        assert attempt.processing_status == "result_issued"
        assert attempt.domain_outcome == "result"
        assert session.scalar(
            select(func.count()).select_from(PromoSession).where(
                PromoSession.attempt_id == attempt.id
            )
        ) == 1


def test_insufficient_and_repeated_photo_publish_no_session(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, engine, spa_id, token = realtime_state

    monkeypatch.setattr(
        realtime,
        "search_realtime_references",
        lambda **_: _insufficient_search_result(),
    )
    attempt_id = uuid.uuid4()
    body, content_type = _multipart(_manifest(attempt_id, count=1))

    response = _request(app, body, content_type, token)

    assert response[0] == 200
    assert response[2] == {
        "schema_version": 1,
        "attempt_id": str(attempt_id),
        "outcome": "insufficient_results",
    }
    with Session(engine) as session:
        attempt = session.scalar(
            select(PromoAttempt).where(
                PromoAttempt.spa_id == spa_id,
                PromoAttempt.client_attempt_id == attempt_id,
            )
        )
        assert attempt is not None
        assert attempt.processing_status == "no_success"
        assert attempt.domain_outcome == "insufficient_results"
        assert session.scalar(select(func.count()).select_from(PromoSession)) == 0


def test_missing_date_is_pre_admission_and_body_override_is_rejected(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str],
) -> None:
    app, engine, spa_id, token = realtime_state
    with Session(engine) as session:
        RealtimeContextRepository(session).update_active_visit_date(
            spa_id=spa_id, active_visit_date=None
        )
        session.commit()

    missing_date_id = uuid.uuid4()
    body, content_type = _multipart(_manifest(missing_date_id, count=1))
    missing_date = _request(app, body, content_type, token)
    assert missing_date[0] == 503

    override_id = uuid.uuid4()
    manifest = _manifest(override_id, count=0)
    manifest["spa_id"] = str(spa_id)
    body, content_type = _multipart(manifest)
    override = _request(app, body, content_type, token)
    assert override[0] == 422

    with Session(engine) as session:
        assert session.scalar(
            select(func.count()).select_from(PromoAttempt).where(
                PromoAttempt.client_attempt_id.in_((missing_date_id, override_id))
            )
        ) == 0


def test_absent_foreign_and_rate_limited_requests_are_rejected_without_attempt(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, engine, _, token = realtime_state
    attempt_id = uuid.uuid4()
    body, content_type = _multipart(_manifest(attempt_id, count=0))

    absent = _request(app, body, content_type, None)
    foreign = _request(app, body, content_type, "foreign-task075-token")
    assert absent[0] == foreign[0] == 401

    app.state.role_state["display_client_rate_limiter"] = DisplayClientRateLimiter(
        limit=1, window_seconds=60
    )
    allowed = _request(app, body, content_type, token)
    limited = _request(app, body, content_type, token)
    assert allowed[0] == 200
    assert allowed[2]["outcome"] == "no_proposals"
    assert limited[0] == 429
    assert token not in caplog.text
    assert "task075-disposable-qr-secret" not in caplog.text
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PromoAttempt)) == 1


def _successful_search_result() -> RealtimeSearchResult:
    first = tuple(_match(number, 1.0 - number / 100, number) for number in range(1, 5))
    second = (_match(1, 0.90, 1), _match(5, 0.89, 5))
    return RealtimeSearchResult(
        detections=(
            _detection(0, first),
            _detection(1, second),
        )
    )


def _insufficient_search_result() -> RealtimeSearchResult:
    return RealtimeSearchResult(
        detections=(
            _detection(0, (_match(1, 0.9, 1), _match(2, 0.8, 2))),
            _detection(1, (_match(1, 0.9, 1), _match(3, 0.8, 3))),
        )
    )


def _detection(index: int, matches: tuple[PhotoMatchObservation, ...]) -> DetectionSearchObservation:
    return DetectionSearchObservation(
        occurrence_index=index,
        rank=index + 1,
        reference_quality_score=0.9,
        quality_gate_passed=True,
        rejection_reason=None,
        matches=matches,
    )


def _match(number: int, similarity: float, phash64: int) -> PhotoMatchObservation:
    return PhotoMatchObservation(
        photo_id=uuid.UUID(int=number),
        cosine_similarity=similarity,
        preview_object_key=f"task075/{number}",
        phash64=phash64,
    )


def _manifest(attempt_id: uuid.UUID, *, count: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "attempt_id": str(attempt_id),
        "trigger_source": "test",
        "client_release": "task075-test",
        "detector_id": "mediapipe_blazeface_full_range",
        "model_version": "task075-model",
        "jpeg_quality": 0.85,
        "camera_device_id": "task075-camera",
        "timing": {
            "reference_series_ready_at": "2026-08-22T10:00:00.000Z",
            "local_detection_completed_ms": 10,
            "request_started_ms": 20,
        },
        "occurrences": [
            {
                "occurrence_index": index,
                "frame_index": index,
                "frame_offset_ms": index * 10,
                "detector_confidence": 0.9,
                "crop_part": f"crop_{index:03d}",
            }
            for index in range(count)
        ],
    }


def _jpeg() -> bytes:
    image = np.zeros((32, 32, 3), dtype=np.uint8)
    image[:, :, 1] = 120
    encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])[1]
    return encoded.tobytes()


def _multipart(manifest: dict[str, Any], *, crops: list[bytes] | None = None) -> tuple[bytes, str]:
    boundary = "task075-boundary"
    fields = [
        (
            b'--' + boundary.encode() + b'\r\n'
            b'Content-Disposition: form-data; name="manifest"\r\n'
            b'Content-Type: application/json; charset=utf-8\r\n\r\n'
            + json.dumps(manifest, separators=(",", ":")).encode()
            + b"\r\n"
        )
    ]
    for index, crop in enumerate(crops or [_jpeg() for _ in manifest["occurrences"]]):
        name = f"crop_{index:03d}"
        fields.append(
            (
                b"--" + boundary.encode()
                + f'\r\nContent-Disposition: form-data; name="{name}"; filename="{name}.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()
                + crop + b"\r\n"
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

    headers = [
        (b"host", b"testserver"),
        (b"content-type", content_type.encode()),
        (b"content-length", str(len(body)).encode()),
    ]
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

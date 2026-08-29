from __future__ import annotations

import asyncio
from collections.abc import Iterator
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

from face_moment.diagnostics import DiagnosticEvidence, DiagnosticEvidenceRepository
from face_moment.entrypoints import backend
from face_moment.entrypoints import realtime
from face_moment.infrastructure.settings import Settings
from face_moment.processing import (
    DetectionSearchObservation,
    PhotoMatchObservation,
    PipelineCode,
    PipelineRevisionRepository,
    RealtimeSearchResult,
)
from face_moment.promo import PromoAttempt
from face_moment.promo import PromoSession
from face_moment.promo import realtime_evidence
from face_moment.promo import realtime_orchestration
from face_moment.serving_control import IngestTargetRepository
from face_moment.serving_control.display_client_access import DisplayClientRepository
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from face_moment.serving_control.realtime_context import RealtimeContextRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@pytest.fixture
def realtime_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[FastAPI, Engine, uuid.UUID, str]]:
    base_settings = Settings.from_env()
    probe_database = f"task085_{uuid.uuid4().hex}"
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
                name=f"task085-{uuid.uuid4().hex}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            context = RealtimeContextRepository(session)
            context.update_active_visit_date(
                spa_id=target.spa_id, active_visit_date=datetime(2026, 8, 28).date()
            )
            context.provision_reference_settings(
                spa_id=target.spa_id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
                reference_threshold=0.6,
                min_query_face_quality=0.5,
                quality_settings={"version": 1},
            )
            display_client = DisplayClientRepository(session).provision(
                spa_id=target.spa_id, name="task085-kiosk"
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
                "qr_ticket_secret": "task085-disposable-qr-secret",
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


def test_result_realtime_path_persists_diagnostics_evidence(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, engine, _, token = realtime_state
    monkeypatch.setattr(
        realtime,
        "search_realtime_references",
        lambda **_: _successful_search_result(),
    )
    attempt_id = uuid.uuid4()
    body, content_type = _multipart(_manifest(attempt_id))

    response = _request(app, body, content_type, token)

    assert response[0] == 200
    with Session(engine) as session:
        attempt = session.scalar(
            select(PromoAttempt).where(PromoAttempt.client_attempt_id == attempt_id)
        )
        assert attempt is not None
        evidence = DiagnosticEvidenceRepository(session).get(attempt.id)
    assert evidence is not None
    assert evidence.ordinary_manifest is not None
    assert evidence.completeness == "incomplete"
    assert evidence.gap_reason == "response_receipt_missing"
    expected_teasers = [
        item["photo_id"] for item in response[2]["result"]["teasers"]
    ]
    assert evidence.ordinary_manifest["result"] == {
        "outcome": "result",
        "teaser_photo_ids": expected_teasers,
        "session_result_photo_ids": [
            str(uuid.UUID(int=number)) for number in range(1, 5)
        ],
        "n": 4,
    }
    assert len(evidence.ordinary_manifest["detections"]) == 1
    assert "selfie" not in _all_keys(evidence.ordinary_manifest)
    assert evidence.ordinary_manifest["artifacts"] == []


def test_zero_proposal_realtime_path_records_absent_search_without_blocking(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str],
) -> None:
    app, engine, _, token = realtime_state
    attempt_id = uuid.uuid4()
    body, content_type = _multipart(_manifest(attempt_id, count=0))

    response = _request(app, body, content_type, token)

    assert response[0] == 200
    assert response[2]["outcome"] == "no_proposals"
    with Session(engine) as session:
        attempt = session.scalar(
            select(PromoAttempt).where(PromoAttempt.client_attempt_id == attempt_id)
        )
        assert attempt is not None
        evidence = DiagnosticEvidenceRepository(session).require(attempt.id)
        assert attempt.processing_status == "no_success"
        assert attempt.domain_outcome == "no_proposals"
        assert evidence.ordinary_manifest is not None
        assert evidence.ordinary_manifest["result"] == {"outcome": "no_proposals"}
        assert "detections" not in evidence.ordinary_manifest
        assert evidence.gap_reason == "response_receipt_missing"


def test_busy_realtime_path_records_inapplicable_search_without_blocking(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str],
) -> None:
    app, engine, _, token = realtime_state
    attempt_id = uuid.uuid4()
    body, content_type = _multipart(_manifest(attempt_id))
    assert realtime_orchestration._PROCESS_LOCAL_REALTIME_SLOT.acquire()
    try:
        response = _request(app, body, content_type, token)
    finally:
        realtime_orchestration._PROCESS_LOCAL_REALTIME_SLOT.release()

    assert response[0] == 200
    assert response[2]["outcome"] == "busy"
    with Session(engine) as session:
        attempt = session.scalar(
            select(PromoAttempt).where(PromoAttempt.client_attempt_id == attempt_id)
        )
        assert attempt is not None
        evidence = DiagnosticEvidenceRepository(session).require(attempt.id)
        assert attempt.domain_outcome == "busy"
        assert evidence.ordinary_manifest is not None
        assert evidence.ordinary_manifest["result"] == {"outcome": "busy"}
        assert "detections" not in evidence.ordinary_manifest
        assert evidence.gap_reason == "response_receipt_missing"


def test_deadline_and_technical_failure_keep_explicit_gaps(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, engine, _, token = realtime_state
    original_execute = realtime.execute_realtime_attempt
    clock_values = iter((0.0, 4.0))

    def deadline_execute(**kwargs: Any) -> Any:
        return original_execute(**kwargs, clock=lambda: next(clock_values))

    monkeypatch.setattr(realtime, "execute_realtime_attempt", deadline_execute)
    deadline_id = uuid.uuid4()
    body, content_type = _multipart(_manifest(deadline_id))
    deadline = _request(app, body, content_type, token)
    assert deadline[0] == 200
    assert deadline[2]["outcome"] == "deadline"

    monkeypatch.setattr(realtime, "execute_realtime_attempt", original_execute)
    monkeypatch.setattr(
        realtime,
        "search_realtime_references",
        lambda **_: (_ for _ in ()).throw(RuntimeError("task085 search failure")),
    )
    failure_id = uuid.uuid4()
    body, content_type = _multipart(_manifest(failure_id))
    failure = _request(app, body, content_type, token)
    assert failure[0] == 500

    with Session(engine) as session:
        deadline_attempt = session.scalar(
            select(PromoAttempt).where(PromoAttempt.client_attempt_id == deadline_id)
        )
        failure_attempt = session.scalar(
            select(PromoAttempt).where(PromoAttempt.client_attempt_id == failure_id)
        )
        assert deadline_attempt is not None
        assert failure_attempt is not None
        deadline_evidence = DiagnosticEvidenceRepository(session).require(
            deadline_attempt.id
        )
        failure_evidence = DiagnosticEvidenceRepository(session).require(
            failure_attempt.id
        )
        assert deadline_evidence.ordinary_manifest is not None
        assert deadline_evidence.ordinary_manifest["result"] == {"outcome": "deadline"}
        assert deadline_evidence.gap_reason == "response_receipt_missing"
        assert failure_attempt.processing_status == "internal_failure"
        assert failure_evidence.ordinary_manifest is not None
        assert failure_evidence.ordinary_manifest["result"] == {
            "outcome": "internal_failure"
        }
        assert failure_evidence.gap_reason == "search_evidence_missing"


def test_evidence_writer_failure_preserves_result_and_owner_rows(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, engine, _, token = realtime_state

    def fail_write(self: object, **_: object) -> object:
        raise RuntimeError("task085 injected diagnostics failure")

    monkeypatch.setattr(realtime_evidence.DiagnosticEvidenceProvider, "write", fail_write)
    monkeypatch.setattr(
        realtime,
        "search_realtime_references",
        lambda **_: _successful_search_result(),
    )
    attempt_id = uuid.uuid4()
    body, content_type = _multipart(_manifest(attempt_id))

    response = _request(app, body, content_type, token)

    assert response[0] == 200
    assert response[2]["outcome"] == "result"
    with Session(engine) as session:
        attempt = session.scalar(
            select(PromoAttempt).where(PromoAttempt.client_attempt_id == attempt_id)
        )
        assert attempt is not None
        assert attempt.processing_status == "result_issued"
        assert attempt.domain_outcome == "result"
        assert session.scalar(
            select(func.count()).select_from(PromoSession).where(
                PromoSession.attempt_id == attempt.id
            )
        ) == 1
        assert DiagnosticEvidenceRepository(session).get(attempt.id) is None


def test_response_and_display_receipts_merge_to_complete_evidence(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, engine, spa_id, token = realtime_state
    monkeypatch.setattr(
        realtime,
        "search_realtime_references",
        lambda **_: _successful_search_result(),
    )
    attempt_id = uuid.uuid4()
    body, content_type = _multipart(_manifest(attempt_id))
    initial = _request(app, body, content_type, token)
    session_id = initial[2]["result"]["session_id"]

    timing = _json_request(
        app,
        method="POST",
        path=f"/api/realtime/attempts/{attempt_id}/client-timing",
        payload={"schema_version": 1, "response_received_ms": 30},
        token=token,
    )
    assert timing[0] == 200
    with Session(engine) as session:
        attempt = session.scalar(
            select(PromoAttempt).where(PromoAttempt.client_attempt_id == attempt_id)
        )
        assert attempt is not None
        evidence = DiagnosticEvidenceRepository(session).require(attempt.id)
        assert evidence.completeness == "incomplete"
        assert evidence.gap_reason == "display_event_missing"
        assert evidence.ordinary_manifest is not None
        assert evidence.ordinary_manifest["client"]["response_received_ms"] == 30
        assert "detections" in evidence.ordinary_manifest

    display_app = backend.create_app()
    display = _json_request(
        display_app,
        method="PUT",
        path=f"/api/promo/sessions/{session_id}/display",
        payload={
            "schema_version": 1,
            "status": "confirmed",
            "qr_fully_visible_elapsed_ms": 8420,
        },
        token=token,
    )
    assert display[0] == 200
    with Session(engine) as session:
        attempt = session.scalar(
            select(PromoAttempt).where(
                PromoAttempt.spa_id == spa_id,
                PromoAttempt.client_attempt_id == attempt_id,
            )
        )
        assert attempt is not None
        evidence = DiagnosticEvidenceRepository(session).require(attempt.id)
        assert evidence.completeness == "complete"
        assert evidence.gap_reason is None
        assert evidence.ordinary_manifest is not None
        assert evidence.ordinary_manifest["display"] == {
            "status": "confirmed",
            "reported_at": evidence.ordinary_manifest["display"]["reported_at"],
            "qr_fully_visible_elapsed_ms": 8420,
        }
        assert evidence.ordinary_manifest["client"]["response_received_ms"] == 30


def _all_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(value)
        for child in value.values():
            keys.update(_all_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_all_keys(child))
    return keys


def _successful_search_result() -> RealtimeSearchResult:
    return RealtimeSearchResult(
        detections=(
            _detection(
                0,
                tuple(_match(number, 1.0 - number / 100, number) for number in range(1, 5)),
            ),
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
        preview_object_key=f"task085/{number}",
        phash64=phash64,
    )


def _manifest(attempt_id: uuid.UUID, *, count: int = 1) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "attempt_id": str(attempt_id),
        "trigger_source": "test",
        "client_release": "task085-test",
        "detector_id": "mediapipe_blazeface_full_range",
        "model_version": "task085-model",
        "jpeg_quality": 0.85,
        "camera_device_id": "task085-camera",
        "timing": {
            "reference_series_ready_at": "2026-08-28T10:00:00.000Z",
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


def _multipart(manifest: dict[str, Any]) -> tuple[bytes, str]:
    boundary = "task085-boundary"
    fields = [
        (
            b"--" + boundary.encode() + b"\r\n"
            b'Content-Disposition: form-data; name="manifest"\r\n'
            b"Content-Type: application/json; charset=utf-8\r\n\r\n"
            + json.dumps(manifest, separators=(",", ":")).encode()
            + b"\r\n"
        ),
    ]
    for index in range(len(manifest["occurrences"])):
        name = f"crop_{index:03d}"
        fields.append(
            (
                b"--" + boundary.encode()
                + f'\r\nContent-Disposition: form-data; name="{name}"; filename="{name}.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()
                + _jpeg()
                + b"\r\n"
            )
        )
    return b"".join(fields) + b"--" + boundary.encode() + b"--\r\n", f"multipart/form-data; boundary={boundary}"


def _request(
    app: FastAPI, body: bytes, content_type: str, token: str | None
) -> tuple[int, dict[str, str], dict[str, Any]]:
    return _asgi_request(
        app,
        method="POST",
        path="/api/realtime/attempts",
        body=body,
        content_type=content_type,
        token=token,
    )


def _json_request(
    app: FastAPI,
    *,
    method: str,
    path: str,
    payload: dict[str, object],
    token: str,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    return _asgi_request(
        app,
        method=method,
        path=path,
        body=json.dumps(payload, separators=(",", ":")).encode(),
        content_type="application/json",
        token=token,
    )


def _asgi_request(
    app: FastAPI,
    *,
    method: str,
    path: str,
    body: bytes,
    content_type: str,
    token: str | None,
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
                "method": method,
                "scheme": "https",
                "path": path,
                "raw_path": path.encode(),
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

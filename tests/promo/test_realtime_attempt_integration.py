from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, timezone
import json
import threading
import time
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
from face_moment.promo import (
    PromoAttempt, PromoSession, PromoAttemptRepository, PromoAttemptNotFoundError,
)
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
    return asyncio.run(_async_request(app, body, content_type, token))


async def _async_request(
    app: FastAPI, body: bytes, content_type: str, token: str | None, *, path: str = "/api/realtime/attempts"
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
    await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET" if path == "/healthz" else "POST",
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
    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return int(start["status"]), {}, json.loads(response_body or b"{}")


@pytest.mark.parametrize("racing_key,first_outcome", [
    (False, "result"), (True, "result"),
    (False, "internal_failure"), (False, "deadline"),
])
def test_concurrent_real_route_returns_before_inference_release(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str],
    monkeypatch: pytest.MonkeyPatch,
    racing_key: bool,
    first_outcome: str,
) -> None:
    app, engine, spa_id, token = realtime_state
    started, release = threading.Event(), threading.Event()
    probe_started = time.monotonic()
    calls: list[int] = []
    trace: list[str] = []
    sessions: list[Session] = []
    closed: list[Session] = []
    thread_ids: dict[int, int] = {}
    loop_thread = threading.get_ident()

    class TrackedSession(Session):
        def __init__(self) -> None:
            super().__init__(engine)
            sessions.append(self)
            thread_ids[id(self)] = threading.get_ident()

        def get_bind(self, *args: Any, **kwargs: Any) -> Any:
            assert thread_ids[id(self)] == threading.get_ident()
            return super().get_bind(*args, **kwargs)

        def close(self) -> None:
            assert thread_ids[id(self)] == threading.get_ident()
            closed.append(self)
            super().close()

    app.state.role_state["session_factory"] = TrackedSession
    app.state.role_state["realtime_deadline_ms"] = 10000

    clock = [0.0]
    original_execute = realtime.execute_realtime_attempt
    def execute_with_clock(**kwargs: Any) -> Any:
        return original_execute(**kwargs, clock=lambda: clock[0])
    monkeypatch.setattr(realtime, "execute_realtime_attempt", execute_with_clock)

    def search(**_: object) -> RealtimeSearchResult:
        calls.append(threading.get_ident())
        trace.append("search_started")
        started.set()
        release.wait(4)
        trace.append("search_released")
        if len(calls) == 1:
            if first_outcome == "internal_failure":
                raise RuntimeError("controlled search failure")
            if first_outcome == "deadline":
                clock[0] = 11.0
        return _successful_search_result()

    monkeypatch.setattr(realtime, "search_realtime_references", search)
    if racing_key:
        # Both transport reads miss before serving-context admission serialization.
        barrier = threading.Barrier(2, timeout=3)
        original_get = PromoAttemptRepository.get_by_admission_key
        def synchronized_get(self: Any, **kwargs: Any) -> Any:
            try:
                return original_get(self, **kwargs)
            except PromoAttemptNotFoundError:
                barrier.wait()
                raise
        monkeypatch.setattr(PromoAttemptRepository, "get_by_admission_key", synchronized_get)

    owner_id, other_id = uuid.uuid4(), uuid.uuid4()
    owner_body, content_type = _multipart(_manifest(owner_id, count=2))
    other_body, _ = _multipart(_manifest(other_id, count=2))

    async def scenario() -> None:
        pending: list[asyncio.Task[Any]] = []
        # A separate watchdog makes pre-fix loop blocking finite too.
        watchdog = threading.Timer(4, release.set)
        watchdog.start()
        try:
            owner = asyncio.create_task(_async_request(app, owner_body, content_type, token))
            pending.append(owner)
            if racing_key:
                duplicate = asyncio.create_task(_async_request(app, owner_body, content_type, token))
                pending.append(duplicate)
            assert await asyncio.to_thread(started.wait, 3)
            assert not release.is_set(), "event loop stayed blocked until inference release"
            health = await asyncio.wait_for(_async_request(app, b"", "", None, path="/healthz"), 1)
            assert health[0] == 200 and not release.is_set()
            trace.append("health_before_release")
            if racing_key:
                done, _ = await asyncio.wait(pending, timeout=1, return_when=asyncio.FIRST_COMPLETED)
                assert len(done) == 1, "duplicate waited on inference-held PostgreSQL row lock"
                duplicate_response = next(iter(done)).result()
                # Do not apply the missing-read barrier to the distinct request.
                monkeypatch.setattr(PromoAttemptRepository, "get_by_admission_key", original_get)
            else:
                duplicate_response = await asyncio.wait_for(_async_request(app, owner_body, content_type, token), 1)
            assert duplicate_response[0] == 200
            assert duplicate_response[2]["outcome"] == "in_progress"
            trace.append("duplicate_in_progress_before_release")
            competing = await asyncio.wait_for(_async_request(app, other_body, content_type, token), 1)
            assert competing[0] == 200 and competing[2]["outcome"] == "busy"
            assert not release.is_set() and len(calls) == 1
            trace.append("distinct_busy_before_release")
            with Session(engine) as session:
                rows = session.scalars(select(PromoAttempt).where(PromoAttempt.spa_id == spa_id)).all()
                assert len(rows) == 2
                by_key = {row.client_attempt_id: row for row in rows}
                assert by_key[owner_id].processing_status == "accepted"
                assert by_key[owner_id].domain_outcome is None
                assert by_key[other_id].domain_outcome == "busy"
            release.set()
            responses = await asyncio.gather(*pending)
            terminal = next(response for response in responses if response[2].get("outcome") != "in_progress")
            if first_outcome == "internal_failure":
                assert terminal[0] == 500
            else:
                assert terminal[0] == 200 and terminal[2]["outcome"] == first_outcome
            replay = await _async_request(app, owner_body, content_type, token)
            assert replay == terminal and len(calls) == 1
            fresh_body, _ = _multipart(_manifest(uuid.uuid4(), count=2))
            fresh = await _async_request(app, fresh_body, content_type, token)
            assert fresh[2]["outcome"] == "result" and len(calls) == 2
            def fail_parse(*_: Any) -> Any:
                raise RuntimeError("controlled worker failure")
            monkeypatch.setattr(realtime, "parse_realtime_multipart", fail_parse)
            with pytest.raises(RuntimeError, match="controlled worker failure"):
                await _async_request(app, owner_body, content_type, token)
        finally:
            release.set()
            watchdog.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            watchdog.join()

    try:
        asyncio.run(scenario())
    finally:
        print({"racing_key": racing_key, "first_outcome": first_outcome, "events": trace, "search_calls": len(calls),
               "elapsed_seconds": round(time.monotonic() - probe_started, 3),
               "session_count": len(sessions), "closed_count": len(closed),
               "worker_threads": sorted(set(thread_ids.values())), "loop_thread": loop_thread})
    assert len(sessions) == len(closed) and set(sessions) == set(closed)
    assert all(thread_id != loop_thread for thread_id in thread_ids.values())
    assert len(set(thread_ids.values())) >= 2


def test_concurrent_route_auth_workers_keep_rate_budget(
    realtime_state: tuple[FastAPI, Engine, uuid.UUID, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, engine, _, token = realtime_state
    callers, limit = 12, 3
    barrier = threading.Barrier(callers, timeout=3)
    original_auth = realtime.authenticate_display_client
    app.state.role_state["display_client_rate_limiter"] = DisplayClientRateLimiter(
        limit=limit, window_seconds=60,
    )

    def synchronized_auth(*args: Any, **kwargs: Any) -> Any:
        barrier.wait()
        return original_auth(*args, **kwargs)

    monkeypatch.setattr(realtime, "authenticate_display_client", synchronized_auth)
    async def scenario() -> list[Any]:
        requests = []
        for _ in range(callers):
            body, content_type = _multipart(_manifest(uuid.uuid4(), count=0))
            requests.append(_async_request(app, body, content_type, token))
        return await asyncio.gather(*requests)

    responses = asyncio.run(scenario())
    statuses = [response[0] for response in responses]
    assert statuses.count(200) == limit and statuses.count(429) == callers - limit
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PromoAttempt)) == limit
    print({"worker_auth_allowed": statuses.count(200), "worker_auth_denied": statuses.count(429)})

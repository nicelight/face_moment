"""TASK-104 exact developer Calibration HTML flow and state-isolation proof."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit
import uuid

import cv2
from fastapi import FastAPI
import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import face_moment.diagnostics.calibration_http as calibration_http
from face_moment.diagnostics.calibration_runs import (
    CalibrationRun,
    CalibrationRunRepository,
    CalibrationRunService,
    CalibrationRunStatus,
)
from face_moment.diagnostics.ground_truth_annotations import GroundTruthAnnotationProvider
from face_moment.entrypoints.backend import create_app
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.platform.auth.principals import StaffRole, StaffUser, provision_staff_user
from face_moment.platform.auth.sessions import (
    LoginRateLimiter,
    create_browser_session,
    revoke_current_browser_session,
)
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.promo.attempt import PromoAttempt
from face_moment.serving_control.ingest_target import IngestTargetRepository, Spa
from face_moment.serving_control.realtime_context import RealtimeContextRepository
from tests.disposable_postgresql import disposable_postgresql_engine


@dataclass(frozen=True)
class CalibrationHttpFixture:
    app: FastAPI
    engine: Engine
    spa_id: uuid.UUID
    photo_id: uuid.UUID
    attempt_id: uuid.UUID
    sface_revision_id: uuid.UUID
    buffalo_revision_id: uuid.UUID
    credentials: dict[str, dict[str, str]]
    cookies: dict[str, dict[str, str]]


class _Store:
    def read(self, *, key: str) -> bytes:
        assert key == "task104/disposable.jpg"
        return _PHOTO_BYTES


class _Adapter:
    def __init__(self, revision_id: uuid.UUID, face_count: int) -> None:
        self.pipeline_revision_id = revision_id
        self._face_count = face_count

    def process_photo(self, photo: np.ndarray) -> tuple[object, ...]:
        assert photo.shape == (12, 20, 3)
        return tuple(object() for _ in range(self._face_count))


def _jpeg() -> bytes:
    encoded, payload = cv2.imencode(
        ".jpg", np.zeros((12, 20, 3), dtype=np.uint8)
    )
    assert encoded
    return bytes(payload)


_PHOTO_BYTES = _jpeg()


@pytest.fixture(scope="module")
def disposable_calibration_http() -> Iterator[CalibrationHttpFixture]:
    marker = uuid.uuid4().hex
    password = f"task104-password-{marker}"
    credentials = {
        role: {"username": f"task104-{role}-{marker}", "password": password}
        for role in ("developer", "operator", "photographer")
    }
    payload = _PHOTO_BYTES
    with disposable_postgresql_engine("task104_http") as engine:
        with Session(engine) as session:
            for name, role in (
                ("developer", StaffRole.DEVELOPER),
                ("operator", StaffRole.OPERATOR),
                ("photographer", StaffRole.PHOTOGRAPHER),
            ):
                provision_staff_user(
                    session,
                    username=credentials[name]["username"],
                    password=password,
                    role=role,
                )
            sface = _revision(session, PipelineCode.OPENCV_SFACE, "sface")
            buffalo = _revision(
                session, PipelineCode.INSIGHTFACE_BUFFALO_M, "buffalo"
            )
            spa = IngestTargetRepository(session).configure_spa(
                name="Task 104 HTTP",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=sface.id,
            )
            RealtimeContextRepository(session).provision_reference_settings(
                spa_id=spa.spa_id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
                reference_threshold=0.61,
                min_query_face_quality=0.51,
                quality_settings={"blur_maximum": 7.0, "version": 1},
            )
            photo = Photo(
                spa_id=spa.spa_id,
                visit_date=date(2026, 9, 6),
                captured_at=datetime(2026, 9, 6, tzinfo=UTC),
                captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
                uploader_id=uuid.uuid4(),
                checksum_sha256=hashlib.sha256(payload).digest(),
                original_object_key="task104/disposable.jpg",
                original_byte_size=len(payload),
                width=20,
                height=12,
                admission_pipeline_revision_id=sface.id,
            )
            session.add(photo)
            session.flush()
            attempt = _attempt(spa_id=spa.spa_id, revision_id=sface.id)
            session.add(attempt)
            session.flush()
            GroundTruthAnnotationProvider(session).create(
                attempt_id=attempt.id,
                target_kind="person",
                detection_occurrence_index=None,
                participant_name="Synthetic Task 104",
                outcome="missed",
            )
            session.commit()
            identifiers = (spa.spa_id, photo.id, attempt.id, sface.id, buffalo.id)

        cookies = {
            role: _login_cookies(engine, values)
            for role, values in credentials.items()
        }
        app = create_app()
        app.state.role_state["session_factory"] = lambda: Session(engine)
        yield CalibrationHttpFixture(
            app=app,
            engine=engine,
            spa_id=identifiers[0],
            photo_id=identifiers[1],
            attempt_id=identifiers[2],
            sface_revision_id=identifiers[3],
            buffalo_revision_id=identifiers[4],
            credentials=credentials,
            cookies=cookies,
        )


def test_exact_routes_are_developer_only_no_store_and_csrf_protected(
    disposable_calibration_http: CalibrationHttpFixture,
) -> None:
    fixture = disposable_calibration_http
    expected = {
        ("GET", "/staff/calibrations"),
        ("POST", "/staff/calibrations"),
        ("GET", "/staff/calibrations/{calibration_id}"),
        ("POST", "/staff/calibrations/{calibration_id}"),
    }
    actual = {
        (method, route.path)
        for route in fixture.app.routes
        for method in (getattr(route, "methods", None) or set())
        if "calibration" in route.path
    }
    assert actual == expected
    assert not any(route.path.startswith("/api/calibration") for route in fixture.app.routes)

    page = _request(
        fixture.app,
        "GET",
        "/staff/calibrations",
        cookies=fixture.cookies["developer"],
    )
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert "Create Calibration run" in page.body

    for cookies, expected_status in (
        (None, 401),
        (fixture.cookies["operator"], 403),
        (fixture.cookies["photographer"], 403),
    ):
        for denied in _authorization_matrix(fixture, cookies):
            assert (
                denied.status_code,
                denied.headers["cache-control"],
                denied.body,
            ) == (expected_status, "no-store", "")

    for missing_csrf in _mutation_matrix(
        fixture, fixture.cookies["developer"], headers={}
    ):
        assert (
            missing_csrf.status_code,
            missing_csrf.headers["cache-control"],
            missing_csrf.body,
        ) == (403, "no-store", "")

    revoked = _login_cookies(fixture.engine, fixture.credentials["developer"])
    with Session(fixture.engine) as session:
        revoke_current_browser_session(
            session,
            session_token=revoked["fm_staff_session"],
            csrf_cookie_token=revoked["fm_staff_csrf"],
            csrf_header_token=revoked["fm_staff_csrf"],
        )
    for revoked_result in _authorization_matrix(fixture, revoked):
        assert (
            revoked_result.status_code,
            revoked_result.headers["cache-control"],
            revoked_result.body,
        ) == (401, "no-store", "")


def test_create_view_rejections_and_confirmed_apply_preserve_exact_owner_state(
    disposable_calibration_http: CalibrationHttpFixture,
) -> None:
    fixture = disposable_calibration_http
    developer = fixture.cookies["developer"]
    csrf = {"X-CSRF-Token": developer["fm_staff_csrf"]}
    before = _serving_snapshot(fixture)

    invalid = _request(
        fixture.app,
        "POST",
        "/staff/calibrations",
        cookies=developer,
        headers=csrf,
        form={**_create_form(fixture), "browser_score": "0.99"},
    )
    assert (invalid.status_code, invalid.body) == (422, "")
    missing = _request(
        fixture.app,
        "POST",
        "/staff/calibrations",
        cookies=developer,
        headers=csrf,
        form={**_create_form(fixture), "photo_ids": str(uuid.uuid4())},
    )
    assert (missing.status_code, missing.body) == (404, "")

    created = _request(
        fixture.app,
        "POST",
        "/staff/calibrations",
        cookies=developer,
        headers=csrf,
        form=_create_form(fixture),
    )
    assert created.status_code == 303
    assert created.headers["cache-control"] == "no-store"
    detail_path = created.headers["location"]
    run_id = uuid.UUID(detail_path.rsplit("/", 1)[1])
    assert _serving_snapshot(fixture) == before

    requested = _request(fixture.app, "GET", detail_path, cookies=developer)
    assert requested.status_code == 200
    assert requested.headers["cache-control"] == "no-store"
    assert "requested" in requested.body
    assert f'/staff/attempts/{fixture.attempt_id}' in requested.body
    assert _serving_snapshot(fixture) == before

    with Session(fixture.engine) as session:
        run = CalibrationRunRepository(session).require(run_id)
        assert run.status == CalibrationRunStatus.REQUESTED
        developer_user = session.scalar(
            select(StaffUser).where(
                StaffUser.username == fixture.credentials["developer"]["username"]
            )
        )
        assert developer_user is not None
        assert run.requested_by_staff_id == developer_user.id
        CalibrationRunService(session).execute(
            run_id=run.id,
            sface_adapter=_Adapter(fixture.sface_revision_id, 1),
            buffalo_adapter=_Adapter(fixture.buffalo_revision_id, 2),
            object_store=_Store(),
        )
        session.commit()

    completed = _request(fixture.app, "GET", detail_path, cookies=developer)
    assert completed.status_code == 200
    assert 'id="calibration-status">complete' in completed.body
    assert "sface-balance" in completed.body
    assert "Attempt drill-down" in completed.body
    assert "<script>task104</script>" not in completed.body
    assert _serving_snapshot(fixture) == before

    forged = _request(
        fixture.app,
        "GET",
        f"{detail_path}?applied_revision={before[0]}",
        cookies=developer,
    )
    assert forged.status_code == 200
    assert "Stored recommendation applied." not in forged.body
    assert _serving_snapshot(fixture) == before

    unconfirmed = _request(
        fixture.app,
        "POST",
        detail_path,
        cookies=developer,
        headers=csrf,
        form={
            "action": "apply",
            "recommendation_key": "sface-balance",
            "confirmation": "no",
        },
    )
    assert (unconfirmed.status_code, unconfirmed.body) == (422, "")
    assert _serving_snapshot(fixture) == before

    unknown = _request(
        fixture.app,
        "POST",
        detail_path,
        cookies=developer,
        headers=csrf,
        form={
            "action": "apply",
            "recommendation_key": "browser-invented",
            "confirmation": "apply",
        },
    )
    assert (unknown.status_code, unknown.body) == (404, "")
    assert _serving_snapshot(fixture) == before

    applied = _request(
        fixture.app,
        "POST",
        detail_path,
        cookies=developer,
        headers=csrf,
        form={
            "action": "apply",
            "recommendation_key": "sface-balance",
            "confirmation": "apply",
        },
    )
    assert applied.status_code == 303
    assert applied.headers["location"] == (
        f"{detail_path}?applied_revision={before[0] + 1}"
    )
    assert applied.headers["cache-control"] == "no-store"
    after = _serving_snapshot(fixture)
    assert after == (
        before[0] + 1,
        0.73,
        0.51,
        {"blur_maximum": 7.0, "version": 1},
        run_id,
    )
    confirmed = _request(
        fixture.app,
        "GET",
        applied.headers["location"],
        cookies=developer,
    )
    assert "Stored recommendation applied." in confirmed.body

    stale = _request(
        fixture.app,
        "POST",
        detail_path,
        cookies=developer,
        headers=csrf,
        form={
            "action": "apply",
            "recommendation_key": "sface-balance",
            "confirmation": "apply",
        },
    )
    assert (stale.status_code, stale.body) == (409, "")
    assert _serving_snapshot(fixture) == after


def test_unexpected_apply_failure_is_empty_sanitized_and_rolls_back(
    disposable_calibration_http: CalibrationHttpFixture,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fixture = disposable_calibration_http
    developer = fixture.cookies["developer"]
    csrf = {"X-CSRF-Token": developer["fm_staff_csrf"]}
    created = _request(
        fixture.app,
        "POST",
        "/staff/calibrations",
        cookies=developer,
        headers=csrf,
        form=_create_form(fixture),
    )
    run_id = uuid.UUID(created.headers["location"].rsplit("/", 1)[1])
    baseline = _serving_snapshot(fixture)
    with Session(fixture.engine) as session:
        CalibrationRunService(session).execute(
            run_id=run_id,
            sface_adapter=_Adapter(fixture.sface_revision_id, 1),
            buffalo_adapter=_Adapter(fixture.buffalo_revision_id, 2),
            object_store=_Store(),
        )
        session.commit()

    protected = "task104-protected-failure"

    def fail_after_flush(
        self: RealtimeContextRepository, **kwargs: object
    ) -> object:
        settings = self.get_reference_settings(
            spa_id=fixture.spa_id,
            pipeline_code=PipelineCode.OPENCV_SFACE,
        )
        settings.reference_threshold = 0.01
        self._session.flush()  # noqa: SLF001 - intentional rollback probe
        raise RuntimeError(protected)

    monkeypatch.setattr(
        RealtimeContextRepository,
        "apply_calibration_recommendation",
        fail_after_flush,
    )
    failed = _request(
        fixture.app,
        "POST",
        f"/staff/calibrations/{run_id}",
        cookies=developer,
        headers=csrf,
        form={
            "action": "apply",
            "recommendation_key": "sface-balance",
            "confirmation": "apply",
        },
    )
    assert (failed.status_code, failed.headers["cache-control"], failed.body) == (
        500,
        "no-store",
        "",
    )
    assert protected not in failed.body
    assert protected not in caplog.text
    assert _serving_snapshot(fixture) == baseline


def test_source_keeps_http_as_adapter_and_serving_control_as_only_writer() -> None:
    http_source = Path("src/face_moment/diagnostics/calibration_http.py").read_text()
    diagnostics_source = Path("src/face_moment/diagnostics/calibration_runs.py").read_text()
    backend_source = Path("src/face_moment/entrypoints/backend.py").read_text()

    assert "ReferenceSearchSettings" not in http_source
    assert ".reference_threshold =" not in diagnostics_source
    assert ".quality_settings =" not in diagnostics_source
    assert "apply_calibration_recommendation" in diagnostics_source
    assert "register_calibration_routes" in backend_source
    assert "FastAPI(" not in http_source
    assert 'fetch(form.getAttribute("action")' in http_source


def _create_form(fixture: CalibrationHttpFixture) -> dict[str, str]:
    return {
        "photo_ids": str(fixture.photo_id),
        "attempt_ids": str(fixture.attempt_id),
        "sface_revision_id": str(fixture.sface_revision_id),
        "buffalo_revision_id": str(fixture.buffalo_revision_id),
    }


def _authorization_matrix(
    fixture: CalibrationHttpFixture, cookies: dict[str, str] | None
) -> tuple[HttpResult, ...]:
    headers = (
        {}
        if cookies is None
        else {"X-CSRF-Token": cookies["fm_staff_csrf"]}
    )
    missing_path = f"/staff/calibrations/{uuid.uuid4()}"
    return (
        _request(fixture.app, "GET", "/staff/calibrations", cookies=cookies),
        *_mutation_matrix(fixture, cookies, headers=headers, detail_path=missing_path),
        _request(fixture.app, "GET", missing_path, cookies=cookies),
    )


def _mutation_matrix(
    fixture: CalibrationHttpFixture,
    cookies: dict[str, str] | None,
    *,
    headers: dict[str, str],
    detail_path: str | None = None,
) -> tuple[HttpResult, ...]:
    target = detail_path or f"/staff/calibrations/{uuid.uuid4()}"
    return (
        _request(
            fixture.app,
            "POST",
            "/staff/calibrations",
            cookies=cookies,
            headers=headers,
            form=_create_form(fixture),
        ),
        _request(
            fixture.app,
            "POST",
            target,
            cookies=cookies,
            headers=headers,
            form={
                "action": "apply",
                "recommendation_key": "sface-balance",
                "confirmation": "apply",
            },
        ),
    )


def _serving_snapshot(
    fixture: CalibrationHttpFixture,
) -> tuple[int, float, float, dict[str, object], uuid.UUID | None]:
    with Session(fixture.engine) as session:
        spa = session.get(Spa, fixture.spa_id)
        assert spa is not None
        settings = RealtimeContextRepository(session).get_reference_settings(
            spa_id=fixture.spa_id,
            pipeline_code=PipelineCode.OPENCV_SFACE,
        )
        return (
            spa.settings_revision,
            settings.reference_threshold,
            settings.min_query_face_quality,
            settings.quality_settings,
            settings.calibration_id,
        )


def _revision(session: Session, code: PipelineCode, label: str):
    return PipelineRevisionRepository(session).publish_eligible(
        pipeline_code=code,
        validated_at=datetime(2026, 9, 6, tzinfo=UTC),
        detector_id=f"task104-{label}-detector",
        detector_version="v1",
        recognizer_id=f"task104-{label}-recognizer",
        recognizer_version="v1",
        weights_sha256=hashlib.sha256(label.encode()).hexdigest(),
        preprocessing_version="task104-preprocess-v1",
        alignment_version="task104-align-v1",
        normalization_version="task104-normalize-v1",
        embedding_dimension=3,
    )


def _attempt(*, spa_id: uuid.UUID, revision_id: uuid.UUID) -> PromoAttempt:
    now = datetime(2026, 9, 6, tzinfo=UTC)
    return PromoAttempt(
        id=uuid.uuid4(),
        spa_id=spa_id,
        client_attempt_id=uuid.uuid4(),
        trigger_source="test",
        client_release="task104-client",
        detector_id="task104-detector",
        model_version="1",
        jpeg_quality=85,
        camera_device_id="task104-camera",
        reference_series_ready_at=now - timedelta(milliseconds=200),
        local_detection_completed_ms=100,
        request_started_ms=200,
        response_received_ms=300,
        proposal_count=0,
        settings_revision=1,
        visit_date=date(2026, 9, 6),
        pipeline_revision_id=revision_id,
        pipeline_code="opencv_sface",
        query_source="reference",
        release_id="task104-release",
        threshold=0.73,
        quality_settings={"version": 1},
        calibration_id=None,
        deadline_ms=3_000,
        slot_decided_at=now,
        search_started_at=now,
        search_finished_at=now,
        processing_status="result_issued",
        domain_outcome="result",
        display_status="confirmed",
        display_expires_at=now + timedelta(seconds=15),
        display_reported_at=now,
        qr_fully_visible_elapsed_ms=9_000,
        created_at=now,
        updated_at=now,
    )


@dataclass(frozen=True)
class HttpResult:
    status_code: int
    headers: dict[str, str]
    body: str


def _request(
    app: FastAPI,
    method: str,
    target: str,
    *,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    form: dict[str, str] | None = None,
) -> HttpResult:
    parsed_target = urlsplit(target)
    body_bytes = b"" if form is None else urlencode(form).encode()
    request_headers = [(b"host", b"testserver")]
    if form is not None:
        request_headers.extend(
            (
                (b"content-type", b"application/x-www-form-urlencoded"),
                (b"content-length", str(len(body_bytes)).encode()),
            )
        )
    if cookies:
        request_headers.append(
            (
                b"cookie",
                "; ".join(
                    f"{name}={value}" for name, value in cookies.items()
                ).encode(),
            )
        )
    request_headers.extend(
        (name.lower().encode(), value.encode())
        for name, value in (headers or {}).items()
    )
    messages: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body_bytes, "more_body": False}

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
                "path": parsed_target.path,
                "raw_path": parsed_target.path.encode(),
                "query_string": parsed_target.query.encode(),
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
    response_headers = {
        name.decode().lower(): value.decode() for name, value in start["headers"]
    }
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    ).decode()
    return HttpResult(start["status"], response_headers, response_body)


def _login_cookies(engine: Engine, values: dict[str, str]) -> dict[str, str]:
    with Session(engine) as session:
        browser = create_browser_session(
            session,
            username=values["username"],
            password=values["password"],
            ip_address="127.0.0.1",
            ttl_seconds=3600,
            limiter=LoginRateLimiter(limit=10, window_seconds=60),
        )
    return {
        "fm_staff_session": browser.session_token,
        "fm_staff_csrf": browser.csrf_token,
    }

"""TASK-097 developer-only ground-truth annotation HTML flow evidence."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
import uuid

from fastapi import FastAPI
import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.diagnostics.evidence import DiagnosticEvidenceRepository
from face_moment.diagnostics.ground_truth_annotations import (
    GroundTruthAnnotation,
    GroundTruthAnnotationProvider,
)
from face_moment.diagnostics.server_events import ServerEvent
import face_moment.diagnostics.ground_truth_annotation_http as annotation_http
from face_moment.entrypoints.backend import create_app
from face_moment.platform.auth.principals import StaffRole, StaffUser, provision_staff_user
from face_moment.platform.auth.sessions import (
    LoginRateLimiter,
    create_browser_session,
    revoke_current_browser_session,
)
from face_moment.promo.attempt import PromoAttempt
from tests.disposable_postgresql import disposable_postgresql_engine


@dataclass(frozen=True)
class AnnotationHttpFixture:
    app: FastAPI
    engine: Engine
    attempt_id: uuid.UUID
    cookies: dict[str, dict[str, str]]
    credentials: dict[str, dict[str, str]]


@pytest.fixture(scope="module")
def disposable_annotation_http() -> Iterator[AnnotationHttpFixture]:
    marker = uuid.uuid4().hex
    password = f"task097-password-{marker}"
    credentials = {
        role: {"username": f"task097-{role}-{marker}", "password": password}
        for role in ("operator", "developer", "photographer")
    }
    attempt = _attempt()
    attempt_id = attempt.id
    with disposable_postgresql_engine("task097") as engine:
        with Session(engine) as session:
            for role_name, role in (
                ("operator", StaffRole.OPERATOR),
                ("developer", StaffRole.DEVELOPER),
                ("photographer", StaffRole.PHOTOGRAPHER),
            ):
                provision_staff_user(
                    session,
                    username=credentials[role_name]["username"],
                    password=password,
                    role=role,
                )
            session.add(attempt)
            session.flush()
            DiagnosticEvidenceRepository(session).write_bundle(
                attempt_id=attempt.id,
                ordinary_manifest={
                    "schema_version": 1,
                    "identity": {"attempt_id": str(attempt.id)},
                    "detections": [{"occurrence_index": 0}],
                    "artifacts": [],
                },
                completeness="complete",
            )
            session.commit()
        cookies = {
            role: _login_cookies(engine, values)
            for role, values in credentials.items()
        }
        app = create_app()
        app.state.role_state["session_factory"] = lambda: Session(engine)
        yield AnnotationHttpFixture(
            app=app,
            engine=engine,
            attempt_id=attempt_id,
            cookies=cookies,
            credentials=credentials,
        )


def test_developer_navigates_from_attempt_detail_and_creates_detection_annotation(
    disposable_annotation_http: AnnotationHttpFixture,
) -> None:
    fixture = disposable_annotation_http
    detail = _request(
        fixture.app,
        "GET",
        f"/staff/attempts/{fixture.attempt_id}",
        cookies=fixture.cookies["developer"],
    )
    annotations_path = f"/staff/attempts/{fixture.attempt_id}/annotations"
    assert detail.status_code == 200
    assert f'href="{annotations_path}"' in detail.body

    page = _request(
        fixture.app,
        "GET",
        annotations_path,
        cookies=fixture.cookies["developer"],
    )
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert "No annotations" in page.body

    created = _request(
        fixture.app,
        "POST",
        annotations_path,
        cookies=fixture.cookies["developer"],
        headers={"X-CSRF-Token": fixture.cookies["developer"]["fm_staff_csrf"]},
        form={
            "target_kind": "detection",
            "detection_occurrence_index": "0",
            "participant_name": "Synthetic Task 097",
            "outcome": "correct",
        },
    )
    assert created.status_code == 303
    assert created.headers["location"] == annotations_path
    assert created.headers["cache-control"] == "no-store"

    persisted = _request(
        fixture.app,
        "GET",
        annotations_path,
        cookies=fixture.cookies["developer"],
    )
    assert persisted.status_code == 200
    assert "Synthetic Task 097" in persisted.body
    with Session(fixture.engine) as session:
        snapshot = GroundTruthAnnotationProvider(session).calculation_snapshot(
            attempt_id=fixture.attempt_id
        )
        assert snapshot.attempt_id == fixture.attempt_id
        assert len(snapshot.annotations) == 1


def test_create_correct_remove_and_missing_versus_explicit_missed(
    disposable_annotation_http: AnnotationHttpFixture,
) -> None:
    fixture = disposable_annotation_http
    attempt_id = _insert_attempt(fixture.engine, with_detection=False)
    path = f"/staff/attempts/{attempt_id}/annotations"
    developer = fixture.cookies["developer"]
    csrf = {"X-CSRF-Token": developer["fm_staff_csrf"]}

    empty = _request(fixture.app, "GET", path, cookies=developer)
    assert empty.status_code == 200
    assert "No annotations" in empty.body
    with Session(fixture.engine) as session:
        assert GroundTruthAnnotationProvider(session).calculation_snapshot(
            attempt_id=attempt_id
        ).annotations == ()

    created = _request(
        fixture.app,
        "POST",
        path,
        cookies=developer,
        headers=csrf,
        form={
            "target_kind": "person",
            "detection_occurrence_index": "",
            "participant_name": "Synthetic Missed 097",
            "outcome": "missed",
        },
    )
    assert created.status_code == 303
    with Session(fixture.engine) as session:
        snapshot = GroundTruthAnnotationProvider(session).calculation_snapshot(
            attempt_id=attempt_id
        )
        assert snapshot.attempt_id == attempt_id
        assert len(snapshot.annotations) == 1
        annotation = snapshot.annotations[0]
        assert annotation.outcome == "missed"
        assert annotation.detection_occurrence_index is None

    item_path = f"{path}/{annotation.annotation_id}"
    corrected = _request(
        fixture.app,
        "POST",
        item_path,
        cookies=developer,
        headers=csrf,
        form={
            "action": "update",
            "participant_name": "Synthetic Corrected 097",
            "outcome": "missed",
        },
    )
    assert corrected.status_code == 303
    assert corrected.headers["cache-control"] == "no-store"
    assert corrected.headers["location"] == path
    corrected_page = _request(fixture.app, "GET", path, cookies=developer)
    assert "Synthetic Corrected 097" in corrected_page.body
    assert "Synthetic Missed 097" not in corrected_page.body

    removed = _request(
        fixture.app,
        "POST",
        item_path,
        cookies=developer,
        headers=csrf,
        form={"action": "delete"},
    )
    assert removed.status_code == 303
    assert removed.headers["cache-control"] == "no-store"
    assert removed.headers["location"] == path
    with Session(fixture.engine) as session:
        assert GroundTruthAnnotationProvider(session).calculation_snapshot(
            attempt_id=attempt_id
        ).annotations == ()


@pytest.mark.parametrize("method", ("GET", "POST"))
@pytest.mark.parametrize("role", ("operator", "photographer"))
def test_non_developer_roles_never_receive_attempt_or_annotation_existence(
    disposable_annotation_http: AnnotationHttpFixture,
    method: str,
    role: str,
) -> None:
    fixture = disposable_annotation_http
    cookies = fixture.cookies[role]
    result = _request(
        fixture.app,
        method,
        f"/staff/attempts/{fixture.attempt_id}/annotations",
        cookies=cookies,
        headers={"X-CSRF-Token": cookies["fm_staff_csrf"]},
        form=(
            {
                "target_kind": "person",
                "detection_occurrence_index": "",
                "participant_name": "Synthetic Denied 097",
                "outcome": "missed",
            }
            if method == "POST"
            else None
        ),
    )
    assert result.status_code == 403
    assert result.headers["cache-control"] == "no-store"
    assert result.body == ""


def test_unauthenticated_revoked_downgraded_and_csrf_requests_are_denied(
    disposable_annotation_http: AnnotationHttpFixture,
) -> None:
    fixture = disposable_annotation_http
    path = f"/staff/attempts/{fixture.attempt_id}/annotations"
    developer = fixture.cookies["developer"]
    form = {
        "target_kind": "person",
        "detection_occurrence_index": "",
        "participant_name": "Synthetic Auth Matrix 097",
        "outcome": "missed",
    }
    for result, expected in (
        (_request(fixture.app, "GET", path), 401),
        (_request(fixture.app, "POST", path, form=form), 401),
        (_request(fixture.app, "POST", path, cookies=developer, form=form), 403),
        (
            _request(
                fixture.app,
                "POST",
                path,
                cookies=developer,
                headers={"X-CSRF-Token": "mismatched-task097"},
                form=form,
            ),
            403,
        ),
    ):
        assert result.status_code == expected
        assert result.headers["cache-control"] == "no-store"
        assert result.body == ""

    revoked = _login_cookies(fixture.engine, fixture.credentials["developer"])
    with Session(fixture.engine) as session:
        revoke_current_browser_session(
            session,
            session_token=revoked["fm_staff_session"],
            csrf_cookie_token=revoked["fm_staff_csrf"],
            csrf_header_token=revoked["fm_staff_csrf"],
        )
    revoked_result = _request(fixture.app, "GET", path, cookies=revoked)
    assert revoked_result.status_code == 401
    assert revoked_result.body == ""

    with Session(fixture.engine) as session:
        user = session.scalar(
            select(StaffUser).where(
                StaffUser.username == fixture.credentials["developer"]["username"]
            )
        )
        assert user is not None
        user.role = StaffRole.OPERATOR
        session.commit()
    try:
        downgraded = _request(fixture.app, "GET", path, cookies=developer)
        assert downgraded.status_code == 403
        assert downgraded.body == ""
    finally:
        with Session(fixture.engine) as session:
            user = session.scalar(
                select(StaffUser).where(
                    StaffUser.username
                    == fixture.credentials["developer"]["username"]
                )
            )
            assert user is not None
            user.role = StaffRole.DEVELOPER
            session.commit()


def test_current_role_and_csrf_matrix_covers_list_and_every_mutation(
    disposable_annotation_http: AnnotationHttpFixture,
) -> None:
    fixture = disposable_annotation_http
    attempt_id = _insert_attempt(fixture.engine, with_detection=True)
    with Session(fixture.engine) as session:
        annotation = GroundTruthAnnotationProvider(session).create(
            attempt_id=attempt_id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Matrix Baseline 097",
            outcome="missed",
        )
        session.commit()

    for role in ("operator", "photographer"):
        for result in _authorization_matrix(
            fixture, attempt_id, annotation.annotation_id, fixture.cookies[role]
        ):
            assert result.status_code == 403
            assert result.headers["cache-control"] == "no-store"
            assert result.body == ""

    for result in _authorization_matrix(fixture, attempt_id, annotation.annotation_id, None):
        assert result.status_code == 401
        assert result.headers["cache-control"] == "no-store"
        assert result.body == ""

    revoked = _login_cookies(fixture.engine, fixture.credentials["developer"])
    with Session(fixture.engine) as session:
        revoke_current_browser_session(
            session,
            session_token=revoked["fm_staff_session"],
            csrf_cookie_token=revoked["fm_staff_csrf"],
            csrf_header_token=revoked["fm_staff_csrf"],
        )
    for result in _authorization_matrix(fixture, attempt_id, annotation.annotation_id, revoked):
        assert result.status_code == 401
        assert result.headers["cache-control"] == "no-store"
        assert result.body == ""

    with Session(fixture.engine) as session:
        user = session.scalar(
            select(StaffUser).where(
                StaffUser.username == fixture.credentials["developer"]["username"]
            )
        )
        assert user is not None
        user.role = StaffRole.OPERATOR
        session.commit()
    try:
        for result in _authorization_matrix(
            fixture, attempt_id, annotation.annotation_id, fixture.cookies["developer"]
        ):
            assert result.status_code == 403
            assert result.headers["cache-control"] == "no-store"
            assert result.body == ""
    finally:
        with Session(fixture.engine) as session:
            user = session.scalar(
                select(StaffUser).where(
                    StaffUser.username
                    == fixture.credentials["developer"]["username"]
                )
            )
            assert user is not None
            user.role = StaffRole.DEVELOPER
            session.commit()

    developer = fixture.cookies["developer"]
    for csrf_header in ({}, {"X-CSRF-Token": "mismatched-task097"}):
        for result in _mutation_matrix(
            fixture,
            attempt_id,
            annotation.annotation_id,
            developer,
            csrf_header,
        ):
            assert result.status_code == 403
            assert result.headers["cache-control"] == "no-store"
            assert result.body == ""

    with Session(fixture.engine) as session:
        rows = GroundTruthAnnotationProvider(session).list(attempt_id=attempt_id)
        assert rows == (annotation,)


@pytest.mark.parametrize(
    "form",
    (
        [("target_kind", "person"), ("target_kind", "person"), ("detection_occurrence_index", ""), ("participant_name", "Repeated"), ("outcome", "missed")],
        [("target_kind", "person"), ("detection_occurrence_index", ""), ("participant_name", "Unknown"), ("outcome", "missed"), ("unknown", "value")],
        [("target_kind", "detection"), ("detection_occurrence_index", "not-an-index"), ("participant_name", "Invalid"), ("outcome", "correct")],
        [("target_kind", "detection"), ("detection_occurrence_index", "99"), ("participant_name", "Missing target"), ("outcome", "correct")],
        [("target_kind", "person"), ("detection_occurrence_index", ""), ("participant_name", "Invalid outcome"), ("outcome", "correct")],
        [("target_kind", "person"), ("detection_occurrence_index", ""), ("participant_name", "   "), ("outcome", "missed")],
    ),
)
def test_invalid_forms_return_no_store_422_without_writes(
    disposable_annotation_http: AnnotationHttpFixture,
    form: list[tuple[str, str]],
) -> None:
    fixture = disposable_annotation_http
    attempt_id = _insert_attempt(fixture.engine, with_detection=True)
    developer = fixture.cookies["developer"]
    result = _request(
        fixture.app,
        "POST",
        f"/staff/attempts/{attempt_id}/annotations",
        cookies=developer,
        headers={"X-CSRF-Token": developer["fm_staff_csrf"]},
        form=form,
    )
    assert result.status_code == 422
    assert result.headers["cache-control"] == "no-store"
    assert result.body == ""
    with Session(fixture.engine) as session:
        assert not session.scalars(
            select(GroundTruthAnnotation).where(
                GroundTruthAnnotation.attempt_id == attempt_id
            )
        ).all()


def test_missing_wrong_owner_and_injected_failure_are_sanitized_and_rolled_back(
    disposable_annotation_http: AnnotationHttpFixture,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fixture = disposable_annotation_http
    developer = fixture.cookies["developer"]
    headers = {"X-CSRF-Token": developer["fm_staff_csrf"]}
    missing_id = uuid.uuid4()
    missing = _request(
        fixture.app,
        "GET",
        f"/staff/attempts/{missing_id}/annotations",
        cookies=developer,
    )
    malformed = _request(
        fixture.app,
        "GET",
        "/staff/attempts/not-a-uuid/annotations",
        cookies=developer,
    )
    assert (missing.status_code, malformed.status_code) == (404, 422)
    assert missing.body == malformed.body == ""

    first_id = _insert_attempt(fixture.engine, with_detection=False)
    second_id = _insert_attempt(fixture.engine, with_detection=False)
    with Session(fixture.engine) as session:
        annotation = GroundTruthAnnotationProvider(session).create(
            attempt_id=first_id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Owner 097",
            outcome="missed",
        )
        session.commit()
    wrong_owner = _request(
        fixture.app,
        "POST",
        f"/staff/attempts/{second_id}/annotations/{annotation.annotation_id}",
        cookies=developer,
        headers=headers,
        form={"action": "delete"},
    )
    assert wrong_owner.status_code == 404
    assert wrong_owner.body == ""

    protected_name = "Task097 Protected Failure Name"

    def fail_after_flush(
        self: GroundTruthAnnotationProvider, **kwargs: object
    ) -> object:
        self._session.add(  # noqa: SLF001 - intentional transactional probe
            GroundTruthAnnotation(
                annotation_id=uuid.uuid4(),
                attempt_id=second_id,
                target_kind="person",
                detection_occurrence_index=None,
                participant_name=protected_name,
                outcome="missed",
            )
        )
        self._session.flush()  # noqa: SLF001 - intentional transactional probe
        raise RuntimeError(protected_name)

    monkeypatch.setattr(annotation_http.GroundTruthAnnotationProvider, "create", fail_after_flush)
    failed = _request(
        fixture.app,
        "POST",
        f"/staff/attempts/{second_id}/annotations",
        cookies=developer,
        headers=headers,
        form={
            "target_kind": "person",
            "detection_occurrence_index": "",
            "participant_name": protected_name,
            "outcome": "missed",
        },
    )
    assert failed.status_code == 500
    assert failed.headers["cache-control"] == "no-store"
    assert failed.body == ""
    assert protected_name not in failed.body
    assert protected_name not in caplog.text
    with Session(fixture.engine) as session:
        assert not session.scalars(
            select(GroundTruthAnnotation).where(
                GroundTruthAnnotation.attempt_id == second_id,
                GroundTruthAnnotation.participant_name == protected_name,
            )
        ).all()


def test_names_are_escaped_and_absent_from_general_projection_urls_and_events(
    disposable_annotation_http: AnnotationHttpFixture,
) -> None:
    fixture = disposable_annotation_http
    attempt_id = _insert_attempt(fixture.engine, with_detection=False)
    protected_name = 'Synthetic <Task097 & "Quoted">'
    developer = fixture.cookies["developer"]
    path = f"/staff/attempts/{attempt_id}/annotations"
    created = _request(
        fixture.app,
        "POST",
        path,
        cookies=developer,
        headers={"X-CSRF-Token": developer["fm_staff_csrf"]},
        form={
            "target_kind": "person",
            "detection_occurrence_index": "",
            "participant_name": protected_name,
            "outcome": "missed",
        },
    )
    assert created.status_code == 303
    child = _request(fixture.app, "GET", path, cookies=developer)
    assert protected_name not in child.body
    assert "Synthetic &lt;Task097 &amp; &quot;Quoted&quot;&gt;" in child.body
    assert protected_name not in created.headers["location"]

    operator = _request(
        fixture.app,
        "GET",
        f"/staff/attempts/{attempt_id}",
        cookies=fixture.cookies["operator"],
    )
    assert operator.status_code == 200
    assert protected_name not in operator.body
    assert "annotation" not in operator.body.casefold()
    with Session(fixture.engine) as session:
        assert not session.scalars(select(ServerEvent)).all()


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
    form: dict[str, str] | list[tuple[str, str]] | None = None,
) -> HttpResult:
    from urllib.parse import urlencode

    path, _separator, query = target.partition("?")
    body_bytes = b"" if form is None else urlencode(form).encode()
    request_headers = [(b"host", b"testserver")]
    if form is not None:
        request_headers.append(
            (b"content-type", b"application/x-www-form-urlencoded")
        )
        request_headers.append((b"content-length", str(len(body_bytes)).encode()))
    if cookies:
        request_headers.append(
            (
                b"cookie",
                "; ".join(f"{name}={value}" for name, value in cookies.items()).encode(),
            )
        )
    request_headers.extend(
        (name.lower().encode(), value.encode()) for name, value in (headers or {}).items()
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
                "path": path,
                "raw_path": path.encode(),
                "query_string": query.encode(),
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
    ).decode()
    response_headers = {
        name.decode().lower(): value.decode() for name, value in start["headers"]
    }
    return HttpResult(start["status"], response_headers, response_body)


def _login_cookies(engine: Engine, credentials: dict[str, str]) -> dict[str, str]:
    with Session(engine) as session:
        browser_session = create_browser_session(
            session,
            username=credentials["username"],
            password=credentials["password"],
            ip_address="127.0.0.1",
            ttl_seconds=3600,
            limiter=LoginRateLimiter(limit=10, window_seconds=60),
        )
    return {
        "fm_staff_session": browser_session.session_token,
        "fm_staff_csrf": browser_session.csrf_token,
    }


def _attempt() -> PromoAttempt:
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    return PromoAttempt(
        id=uuid.uuid4(),
        spa_id=uuid.uuid4(),
        client_attempt_id=uuid.uuid4(),
        trigger_source="test",
        client_release="kiosk-task097",
        detector_id="mediapipe-blazeface-full-range",
        model_version="1",
        jpeg_quality=85,
        camera_device_id="task097-camera",
        reference_series_ready_at=now - timedelta(milliseconds=220),
        local_detection_completed_ms=140,
        request_started_ms=220,
        response_received_ms=360,
        proposal_count=1,
        settings_revision=4,
        visit_date=date(2026, 9, 4),
        pipeline_revision_id=uuid.uuid4(),
        pipeline_code="opencv_sface",
        query_source="reference",
        release_id="server-task097",
        threshold=0.71,
        quality_settings={"version": 1},
        calibration_id=None,
        deadline_ms=3_000,
        slot_decided_at=now + timedelta(milliseconds=10),
        search_started_at=now + timedelta(milliseconds=20),
        search_finished_at=now + timedelta(milliseconds=50),
        processing_status="result_issued",
        domain_outcome="result",
        display_status="confirmed",
        display_expires_at=now + timedelta(seconds=10),
        display_reported_at=now + timedelta(seconds=1),
        qr_fully_visible_elapsed_ms=9_500,
        created_at=now,
        updated_at=now,
    )


def _insert_attempt(engine: Engine, *, with_detection: bool) -> uuid.UUID:
    attempt = _attempt()
    attempt_id = attempt.id
    with Session(engine) as session:
        session.add(attempt)
        session.flush()
        if with_detection:
            DiagnosticEvidenceRepository(session).write_bundle(
                attempt_id=attempt_id,
                ordinary_manifest={
                    "schema_version": 1,
                    "identity": {"attempt_id": str(attempt_id)},
                    "detections": [{"occurrence_index": 0}],
                    "artifacts": [],
                },
                completeness="complete",
            )
        session.commit()
    return attempt_id


def _authorization_matrix(
    fixture: AnnotationHttpFixture,
    attempt_id: uuid.UUID,
    annotation_id: uuid.UUID,
    cookies: dict[str, str] | None,
) -> tuple[HttpResult, ...]:
    headers = (
        {}
        if cookies is None
        else {"X-CSRF-Token": cookies["fm_staff_csrf"]}
    )
    path = f"/staff/attempts/{attempt_id}/annotations"
    return (
        _request(fixture.app, "GET", path, cookies=cookies),
        *_mutation_matrix(
            fixture, attempt_id, annotation_id, cookies, headers
        ),
    )


def _mutation_matrix(
    fixture: AnnotationHttpFixture,
    attempt_id: uuid.UUID,
    annotation_id: uuid.UUID,
    cookies: dict[str, str] | None,
    headers: dict[str, str],
) -> tuple[HttpResult, ...]:
    path = f"/staff/attempts/{attempt_id}/annotations"
    item_path = f"{path}/{annotation_id}"
    return (
        _request(
            fixture.app,
            "POST",
            path,
            cookies=cookies,
            headers=headers,
            form={
                "target_kind": "person",
                "detection_occurrence_index": "",
                "participant_name": "Synthetic Matrix Create 097",
                "outcome": "missed",
            },
        ),
        _request(
            fixture.app,
            "POST",
            item_path,
            cookies=cookies,
            headers=headers,
            form={
                "action": "update",
                "participant_name": "Synthetic Matrix Update 097",
                "outcome": "missed",
            },
        ),
        _request(
            fixture.app,
            "POST",
            item_path,
            cookies=cookies,
            headers=headers,
            form={"action": "delete"},
        ),
    )

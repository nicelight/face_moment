from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
from typing import Any
import uuid

from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

import face_moment.diagnostics.attempt_investigation as investigation
import face_moment.diagnostics.http as diagnostics_http
from face_moment.diagnostics.evidence import (
    DiagnosticEvidence,
    DiagnosticEvidenceProvider,
    DiagnosticEvidenceRepository,
)
from face_moment.diagnostics.retention import DiagnosticRetentionProvider
from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.principals import (
    StaffRole,
    StaffUser,
    provision_staff_user,
)
from face_moment.platform.auth.sessions import LoginRateLimiter, create_browser_session
from face_moment.promo.attempt import PromoAttempt


@dataclass(frozen=True)
class InvestigationFixture:
    app: FastAPI
    engine: Engine
    cookies: dict[str, dict[str, str]]
    attempts: dict[str, uuid.UUID]
    correlations: dict[str, uuid.UUID]


@pytest.fixture
def disposable_investigation(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InvestigationFixture]:
    base_settings = Settings.from_env()
    probe_database = f"task089_{uuid.uuid4().hex}"
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
    password = f"task089-password-{marker}"
    credentials = {
        role: {"username": f"task089-{role}-{marker}", "password": password}
        for role in ("operator", "developer", "photographer")
    }
    attempts = {name: uuid.uuid4() for name in ("complete", "partial", "absent", "expired", "removed")}
    correlations = {name: uuid.uuid4() for name in attempts}
    created = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
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
            session.add_all(
                _attempt(
                    attempt_id=attempts[name],
                    correlation_id=correlations[name],
                    created_at=created + timedelta(minutes=index),
                )
                for index, name in enumerate(attempts)
            )
            session.commit()

            repository = DiagnosticEvidenceRepository(session)
            repository.write_bundle(
                attempt_id=attempts["complete"],
                ordinary_manifest=_manifest(attempts["complete"], "complete-marker"),
                completeness="complete",
                issue_tags=("accepted_detail",),
                now=created,
            )
            repository.write_bundle(
                attempt_id=attempts["partial"],
                ordinary_manifest=_manifest(attempts["partial"], "partial-marker"),
                completeness="incomplete",
                gap_reason="response_receipt_missing",
                issue_tags=("partial_detail",),
                now=created,
            )
            repository.write_bundle(
                attempt_id=attempts["expired"],
                ordinary_manifest=_manifest(attempts["expired"], "expired-secret-marker"),
                completeness="complete",
                now=created,
            )
            repository.promote_subset(
                attempt_id=attempts["expired"],
                promoted_subset={"participant_name": "excluded-expired-name"},
                now=created,
            )
            repository.expire_ordinary(attempt_id=attempts["expired"], now=created)
            repository.write_bundle(
                attempt_id=attempts["removed"],
                ordinary_manifest=_manifest(attempts["removed"], "removed-secret-marker"),
                completeness="complete",
                now=created,
            )
            repository.promote_subset(
                attempt_id=attempts["removed"],
                promoted_subset={"participant_name": "excluded-removed-name"},
                now=created,
            )
            repository.remove_ordinary(attempt_id=attempts["removed"], now=created)
            session.commit()

        cookies = {
            role: _login_token(engine, credentials[role])
            for role in credentials
        }
        app = create_app()
        app.state.role_state["session_factory"] = lambda: Session(engine)
        yield InvestigationFixture(
            app=app,
            engine=engine,
            cookies=cookies,
            attempts=attempts,
            correlations=correlations,
        )
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)"
            )
        admin_engine.dispose()


def test_exact_filters_table_and_detail_project_complete_core_and_evidence(
    disposable_investigation: InvestigationFixture,
) -> None:
    fixture = disposable_investigation
    attempt_id = fixture.attempts["complete"]
    correlation_id = fixture.correlations["complete"]
    query = (
        f"attempt_id={attempt_id}&correlation_id={correlation_id}"
        "&from=2026-09-01T08%3A00%3A00Z&to=2026-09-01T09%3A00%3A00Z"
        "&state=result_issued"
    )
    status_code, headers, body = _request(
        fixture.app,
        f"/staff/attempts?{query}",
        cookies=fixture.cookies["developer"],
    )
    assert status_code == 200
    assert headers["cache-control"] == "no-store"
    assert str(attempt_id) in body
    assert str(correlation_id) in body
    assert "result_issued" in body
    assert "admission_to_slot=" in body
    assert "9500ms client-local" in body
    assert "complete" in body

    status_code, headers, body = _request(
        fixture.app,
        f"/staff/attempts/{attempt_id}",
        cookies=fixture.cookies["developer"],
    )
    assert status_code == 200
    assert headers["cache-control"] == "no-store"
    for expected in (
        "Ready-series start",
        "Local detection completion",
        "Request start",
        "Response receipt",
        "Slot decision",
        "Search start",
        "Search finish",
        "Display state",
        "QR visible elapsed",
        "Developer evidence",
        "complete-marker",
    ):
        assert expected in body


def test_operator_is_sanitized_and_current_role_is_enforced_on_every_request(
    disposable_investigation: InvestigationFixture,
) -> None:
    fixture = disposable_investigation
    attempt_id = fixture.attempts["complete"]
    path = f"/staff/attempts/{attempt_id}"
    status_code, headers, operator_body = _request(
        fixture.app, path, cookies=fixture.cookies["operator"]
    )
    assert status_code == 200
    assert headers["cache-control"] == "no-store"
    assert "Evidence availability" in operator_body
    assert "Developer evidence" not in operator_body
    assert "complete-marker" not in operator_body
    assert "participant" not in operator_body.casefold()
    assert "annotation" not in operator_body.casefold()
    assert "calibration" not in operator_body.casefold()
    assert "server event" not in operator_body.casefold()

    for cookies, expected_status in (
        (fixture.cookies["photographer"], 403),
        (None, 401),
    ):
        denied_status, denied_headers, denied_body = _request(
            fixture.app, path, cookies=cookies
        )
        assert denied_status == expected_status
        assert denied_headers["cache-control"] == "no-store"
        assert denied_body == ""

        malformed_status, malformed_headers, malformed_body = _request(
            fixture.app, "/staff/attempts/not-a-uuid", cookies=cookies
        )
        assert malformed_status == expected_status
        assert malformed_headers["cache-control"] == "no-store"
        assert malformed_body == ""

    with Session(fixture.engine) as session:
        developer = session.scalar(
            select(StaffUser).where(StaffUser.username.like("task089-developer-%"))
        )
        assert developer is not None
        developer.role = StaffRole.PHOTOGRAPHER
        session.commit()

    stale_status, stale_headers, stale_body = _request(
        fixture.app, path, cookies=fixture.cookies["developer"]
    )
    assert stale_status == 403
    assert stale_headers["cache-control"] == "no-store"
    assert stale_body == ""


def test_complete_incomplete_absent_expired_and_removed_are_distinct_and_truthful(
    disposable_investigation: InvestigationFixture,
) -> None:
    fixture = disposable_investigation
    expected = {
        "complete": "complete",
        "partial": "incomplete",
        "absent": "incomplete",
        "expired": "expired",
        "removed": "removed",
    }
    for name, availability in expected.items():
        status_code, headers, body = _request(
            fixture.app,
            f"/staff/attempts/{fixture.attempts[name]}",
            cookies=fixture.cookies["developer"],
        )
        assert status_code == 200
        assert headers["cache-control"] == "no-store"
        assert f'id="evidence-availability">{availability}<' in body
    expired_body = _request(
        fixture.app,
        f"/staff/attempts/{fixture.attempts['expired']}",
        cookies=fixture.cookies["developer"],
    )[2]
    removed_body = _request(
        fixture.app,
        f"/staff/attempts/{fixture.attempts['removed']}",
        cookies=fixture.cookies["developer"],
    )[2]
    for body in (expired_body, removed_body):
        assert "secret-marker" not in body
        assert "excluded-" not in body


def test_explicit_removal_is_idempotent_preserves_subset_and_rejects_stale_writes(
    disposable_investigation: InvestigationFixture,
) -> None:
    fixture = disposable_investigation
    attempt_id = fixture.attempts["complete"]
    with Session(fixture.engine) as session:
        repository = DiagnosticEvidenceRepository(session)
        repository.promote_subset(
            attempt_id=attempt_id,
            promoted_subset={"participant_name": "retained-curated-subset"},
        )
        first = repository.remove_ordinary(attempt_id=attempt_id)
        first_updated_at = first.updated_at
        first_id = first.id
        promoted_before = first.promoted_subset
        session.commit()

    with Session(fixture.engine) as session:
        repeated = DiagnosticEvidenceRepository(session).remove_ordinary(
            attempt_id=attempt_id
        )
        assert repeated.id == first_id
        assert repeated.updated_at == first_updated_at
        assert repeated.promoted_subset == promoted_before
        assert repeated.ordinary_expired_at is None
        session.commit()

    with Session(fixture.engine) as session:
        retention = DiagnosticRetentionProvider(session).expire(
            [attempt_id],
            cutoff=datetime(2026, 6, 1, tzinfo=timezone.utc),
            now=datetime(2026, 9, 2, tzinfo=timezone.utc),
        )
        preserved = DiagnosticEvidenceRepository(session).require(attempt_id)
        assert retention.eligible_attempt_ids == (attempt_id,)
        assert retention.ordinary_evidence_expired == 0
        assert retention.promoted_subsets_preserved == 1
        assert preserved.gap_reason == "ordinary_removed"
        assert preserved.ordinary_expired_at is None
        assert preserved.promoted_subset == promoted_before

    with Session(fixture.engine) as session:
        provider = DiagnosticEvidenceProvider(session)
        stale_write = provider.write(
            attempt_id=attempt_id,
            ordinary_manifest=_manifest(attempt_id, "stale-write"),
            completeness="complete",
        )
        stale_patch = provider.patch(
            attempt_id=attempt_id,
            ordinary_manifest=_manifest(attempt_id, "stale-patch"),
            gap_reason="response_receipt_missing",
        )
        stale_finalize = provider.finalize(attempt_id=attempt_id)
        assert not stale_write.accepted
        assert not stale_patch.accepted
        assert not stale_finalize.accepted

    status_code, _headers, body = _request(
        fixture.app,
        f"/staff/attempts/{attempt_id}",
        cookies=fixture.cookies["developer"],
    )
    assert status_code == 200
    assert 'id="evidence-availability">removed<' in body
    assert "stale-write" not in body
    assert "stale-patch" not in body


@pytest.mark.parametrize(
    "query",
    (
        "unknown=value",
        "state=accepted&state=deadline",
        "attempt_id=not-a-uuid",
        "correlation_id=",
        "from=2026-09-01T08%3A00%3A00%2B03%3A00",
        "to=not-a-time",
        "state=unsupported",
        "from=2026-09-01T09%3A00%3A00Z&to=2026-09-01T08%3A00%3A00Z",
    ),
)
def test_invalid_filters_return_no_store_422_before_provider_access(
    disposable_investigation: InvestigationFixture,
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    calls = 0

    def forbidden_provider(*args: object, **kwargs: object) -> tuple[()]:
        nonlocal calls
        calls += 1
        return ()

    monkeypatch.setattr(diagnostics_http, "read_attempts", forbidden_provider)
    status_code, headers, body = _request(
        disposable_investigation.app,
        f"/staff/attempts?{query}",
        cookies=disposable_investigation.cookies["operator"],
    )
    assert status_code == 422
    assert headers["cache-control"] == "no-store"
    assert body == ""
    assert calls == 0


def test_missing_core_does_not_reconstruct_from_orphan_evidence(
    disposable_investigation: InvestigationFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = disposable_investigation
    missing_id = uuid.uuid4()
    with Session(fixture.engine) as session:
        DiagnosticEvidenceRepository(session).write_bundle(
            attempt_id=missing_id,
            ordinary_manifest=_manifest(missing_id, "orphan-protected-marker"),
            completeness="complete",
        )
        session.commit()

    evidence_reads = 0
    original_get = investigation.DiagnosticEvidenceRepository.get

    def counting_get(self: DiagnosticEvidenceRepository, *args: object, **kwargs: object) -> DiagnosticEvidence | None:
        nonlocal evidence_reads
        evidence_reads += 1
        return original_get(self, *args, **kwargs)

    monkeypatch.setattr(investigation.DiagnosticEvidenceRepository, "get", counting_get)
    status_code, headers, body = _request(
        fixture.app,
        f"/staff/attempts/{missing_id}",
        cookies=fixture.cookies["developer"],
    )
    assert status_code == 404
    assert headers["cache-control"] == "no-store"
    assert body == ""
    assert evidence_reads == 0


@pytest.mark.parametrize("branch", ("provider", "evidence", "render"))
def test_internal_failures_are_sanitized_no_store_and_redacted(
    disposable_investigation: InvestigationFixture,
    monkeypatch: pytest.MonkeyPatch,
    branch: str,
) -> None:
    fixture = disposable_investigation
    protected = "cookie=forbidden participant=forbidden manifest=forbidden"

    def fail(*args: object, **kwargs: object) -> Any:
        raise RuntimeError(protected)

    if branch == "provider":
        monkeypatch.setattr(diagnostics_http, "read_attempts", fail)
        path = "/staff/attempts"
    elif branch == "evidence":
        monkeypatch.setattr(investigation.DiagnosticEvidenceRepository, "get", fail)
        path = f"/staff/attempts/{fixture.attempts['complete']}"
    else:
        monkeypatch.setattr(diagnostics_http, "_render_attempt_detail", fail)
        path = f"/staff/attempts/{fixture.attempts['complete']}"
    status_code, headers, body = _request(
        fixture.app, path, cookies=fixture.cookies["developer"]
    )
    assert status_code == 500
    assert headers["cache-control"] == "no-store"
    assert body == ""
    assert "traceback" not in body.casefold()
    assert protected not in body


def _manifest(attempt_id: uuid.UUID, marker: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "identity": {"attempt_id": str(attempt_id), "marker": marker},
        "artifacts": [],
    }


def _attempt(
    *, attempt_id: uuid.UUID, correlation_id: uuid.UUID, created_at: datetime
) -> PromoAttempt:
    return PromoAttempt(
        id=attempt_id,
        spa_id=uuid.uuid4(),
        client_attempt_id=correlation_id,
        trigger_source="test",
        client_release="kiosk-task089",
        detector_id="mediapipe-blazeface-full-range",
        model_version="1",
        jpeg_quality=85,
        camera_device_id="task089-camera",
        reference_series_ready_at=created_at - timedelta(milliseconds=220),
        local_detection_completed_ms=140,
        request_started_ms=220,
        response_received_ms=360,
        proposal_count=3,
        settings_revision=4,
        visit_date=date(2026, 9, 1),
        pipeline_revision_id=uuid.uuid4(),
        pipeline_code="opencv_sface",
        query_source="reference",
        release_id="server-task089",
        threshold=0.71,
        quality_settings={"version": 1},
        calibration_id=None,
        deadline_ms=3_000,
        slot_decided_at=created_at + timedelta(milliseconds=10),
        search_started_at=created_at + timedelta(milliseconds=20),
        search_finished_at=created_at + timedelta(milliseconds=50),
        processing_status="result_issued",
        domain_outcome="result",
        display_status="confirmed",
        display_expires_at=created_at + timedelta(seconds=10),
        display_reported_at=created_at + timedelta(seconds=1),
        qr_fully_visible_elapsed_ms=9_500,
        created_at=created_at,
        updated_at=created_at,
    )


def _login_token(engine: Engine, credentials: dict[str, str]) -> dict[str, str]:
    with Session(engine) as session:
        browser_session = create_browser_session(
            session,
            username=credentials["username"],
            password=credentials["password"],
            ip_address="127.0.0.1",
            ttl_seconds=3600,
            limiter=LoginRateLimiter(limit=10, window_seconds=60),
        )
        return {"fm_staff_session": browser_session.session_token}


def _request(
    app: FastAPI,
    target: str,
    *, cookies: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], str]:
    path, _separator, query = target.partition("?")
    request_headers = [(b"host", b"testserver")]
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
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
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
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    ).decode()
    headers = {
        name.decode().lower(): value.decode() for name, value in start["headers"]
    }
    return start["status"], headers, body

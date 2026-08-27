from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import json
from typing import Iterator
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session
from starlette.requests import Request

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.processing import PipelineCode
from face_moment.promo import (
    DisplayOutcomeRepository,
    DisplayReport,
    DisplayReportConflictError,
    PromoAttempt,
    PromoAttemptRepository,
    ResultAssembly,
    parse_display_report,
)
from face_moment.promo import http as promo_http
from face_moment.serving_control.display_client_auth import (
    DisplayClientPrincipal,
    InvalidDisplayClientCredentials,
)


@pytest.fixture
def disposable_display_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    base_settings = Settings.from_env()
    probe_database = f"task077_{uuid.uuid4().hex}"
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
    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)"
            )
        admin_engine.dispose()


def _attempt_values(spa_id: uuid.UUID, client_attempt_id: uuid.UUID) -> dict[str, object]:
    return {
        "spa_id": spa_id,
        "client_attempt_id": client_attempt_id,
        "trigger_source": "test",
        "client_release": "task077-client",
        "detector_id": "mediapipe_blazeface_full_range",
        "model_version": "task077-model",
        "jpeg_quality": 82,
        "camera_device_id": "camera-task077",
        "reference_series_ready_at": datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc),
        "local_detection_completed_ms": 140,
        "request_started_ms": 220,
        "proposal_count": 4,
        "settings_revision": 4,
        "visit_date": date(2026, 8, 27),
        "pipeline_revision_id": uuid.uuid4(),
        "pipeline_code": PipelineCode.OPENCV_SFACE,
        "query_source": "reference",
        "threshold": 0.71,
        "quality_settings": {"version": 1},
        "release_id": "task077-server",
        "deadline_ms": 3000,
        "calibration_id": uuid.uuid4(),
    }


def _assembly() -> ResultAssembly:
    photos = tuple(uuid.uuid4() for _ in range(4))
    return ResultAssembly(
        outcome="result",
        session_result_photo_ids=photos,
        teaser_photo_ids=photos,
        n=len(photos),
    )


def _issue_result(
    session: Session,
    *,
    expires_at: datetime,
) -> tuple[PromoAttempt, uuid.UUID, tuple[uuid.UUID, ...], int]:
    spa_id = uuid.uuid4()
    attempt = PromoAttemptRepository(session).create_or_get(
        **_attempt_values(spa_id, uuid.uuid4())
    )
    PromoAttemptRepository(session).mark_search_started(
        attempt,
        now=datetime(2026, 8, 27, 7, 0, 1, tzinfo=timezone.utc),
    )
    result = PromoAttemptRepository(session).publish_result(
        attempt,
        _assembly(),
        qr_ticket_secret="task077-secret",
        qr_issued_at=datetime(2026, 8, 27, 7, 0, 2, tzinfo=timezone.utc),
        display_expires_at=expires_at,
    )
    session.commit()
    return attempt, result.session_id, result.teasers, result.n


def _session_snapshot(session: Session, session_id: uuid.UUID) -> tuple[object, ...]:
    row = session.execute(
        text(
            "SELECT spa_id, visit_date, session_result_photo_ids, teaser_photo_ids, "
            "n, qr_ticket_hash_sha256, qr_issued_at, qr_first_open_expires_at "
            "FROM face_moment.promo_sessions WHERE id = :session_id"
        ),
        {"session_id": session_id},
    ).one_or_none()
    assert row is not None
    return tuple(row)


def test_report_is_idempotent_and_does_not_mutate_immutable_session(
    disposable_display_engine: Engine,
) -> None:
    report_at = datetime(2026, 8, 27, 7, 0, 5, tzinfo=timezone.utc)
    expiry = report_at + timedelta(seconds=10)
    with Session(disposable_display_engine) as session:
        attempt, session_id, teasers, n = _issue_result(
            session,
            expires_at=expiry,
        )
        before = _session_snapshot(session, session_id)
        repository = DisplayOutcomeRepository(session)

        first = repository.record(
            spa_id=attempt.spa_id,
            session_id=session_id,
            report=DisplayReport(
                status="confirmed",
                qr_fully_visible_elapsed_ms=8421,
            ),
            now=report_at,
        )
        session.commit()
        assert first.status == "confirmed"
        assert first.qr_fully_visible_elapsed_ms == 8421
        assert first.display_reported_at == report_at
        assert attempt.display_status == "confirmed"
        assert attempt.qr_fully_visible_elapsed_ms == 8421

        repeated = repository.record(
            spa_id=attempt.spa_id,
            session_id=session_id,
            report=DisplayReport(
                status="confirmed",
                qr_fully_visible_elapsed_ms=9999,
            ),
            now=report_at + timedelta(seconds=1),
        )
        assert repeated == first
        with pytest.raises(DisplayReportConflictError):
            repository.record(
                spa_id=attempt.spa_id,
                session_id=session_id,
                report=DisplayReport(status="failed"),
                now=report_at + timedelta(seconds=2),
            )
        session.commit()

        after = _session_snapshot(session, session_id)
        assert after == before
        persisted = session.get(PromoAttempt, attempt.id)
        assert persisted is not None
        assert tuple(teasers) == tuple(after[3])
        assert persisted.display_status == "confirmed"
        assert persisted.display_reported_at == report_at
        assert persisted.qr_fully_visible_elapsed_ms == 8421
        assert persisted.display_expires_at == expiry


def test_failed_report_and_expired_pending_are_terminal_without_stored_unconfirmed(
    disposable_display_engine: Engine,
) -> None:
    report_at = datetime(2026, 8, 27, 7, 0, 5, tzinfo=timezone.utc)
    expiry = report_at + timedelta(seconds=10)
    with Session(disposable_display_engine) as session:
        attempt, session_id, _, _ = _issue_result(session, expires_at=expiry)
        repository = DisplayOutcomeRepository(session)
        failed = repository.record(
            spa_id=attempt.spa_id,
            session_id=session_id,
            report=DisplayReport(status="failed"),
            now=report_at,
        )
        session.commit()
        assert failed.status == "failed"
        assert failed.qr_fully_visible_elapsed_ms is None
        assert attempt.qr_fully_visible_elapsed_ms is None

    with Session(disposable_display_engine) as session:
        attempt, session_id, _, _ = _issue_result(
            session,
            expires_at=expiry,
        )
        repository = DisplayOutcomeRepository(session)
        effective = repository.read(
            spa_id=attempt.spa_id,
            session_id=session_id,
            now=expiry,
        )
        assert effective.status == "unconfirmed"
        assert session.get(PromoAttempt, attempt.id).display_status == "pending"
        with pytest.raises(DisplayReportConflictError):
            repository.record(
                spa_id=attempt.spa_id,
                session_id=session_id,
                report=DisplayReport(
                    status="confirmed",
                    qr_fully_visible_elapsed_ms=1,
                ),
                now=expiry,
            )
        session.rollback()
        persisted = session.get(PromoAttempt, attempt.id)
        assert persisted is not None
        assert persisted.display_status == "pending"


def test_report_parser_and_scope_reject_invalid_or_foreign_inputs() -> None:
    assert parse_display_report(
        {
            "schema_version": 1,
            "status": "confirmed",
            "qr_fully_visible_elapsed_ms": 0,
        }
    ) == DisplayReport(status="confirmed", qr_fully_visible_elapsed_ms=0)
    assert parse_display_report(
        {"schema_version": 1, "status": "failed"}
    ) == DisplayReport(status="failed")
    for encoded_version in ("1.0", "1e0"):
        with pytest.raises(ValueError):
            parse_display_report(
                json.loads(
                    "{\"schema_version\": "
                    + encoded_version
                    + ", \"status\": \"failed\"}"
                )
            )
    for payload in (
        {"schema_version": 1, "status": "confirmed"},
        {"schema_version": 1, "status": "failed", "qr_fully_visible_elapsed_ms": 1},
        {"schema_version": 1, "status": "confirmed", "qr_fully_visible_elapsed_ms": -1},
        {"schema_version": 1, "status": "confirmed", "qr_fully_visible_elapsed_ms": True},
        {"schema_version": 1, "status": "confirmed", "qr_fully_visible_elapsed_ms": 1, "extra": 1},
    ):
        with pytest.raises(ValueError):
            parse_display_report(payload)


def _display_route(app) -> APIRoute:
    return next(
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == "/api/promo/sessions/{session_id}/display"
    )


def _request(body: bytes, *, content_type: str = "application/json") -> Request:
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "PUT",
            "path": "/api/promo/sessions/00000000-0000-0000-0000-000000000077/display",
            "headers": [
                (b"authorization", b"Bearer fixture-token"),
                (b"content-type", content_type.encode("ascii")),
            ],
            "client": ("127.0.0.1", 1234),
            "scheme": "https",
            "server": ("central.example.test", 443),
        },
        receive=receive,
    )


def test_backend_exposes_exact_authenticated_ack_route_and_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    route = _display_route(app)
    assert route.methods == {"PUT"}
    session_id = uuid.UUID("00000000-0000-0000-0000-000000000077")
    expiry = datetime(2026, 8, 27, 7, 0, 20, tzinfo=timezone.utc)

    class SettingsFixture:
        database_url = "postgresql+psycopg://unused"
        realtime_rate_limit = 10
        realtime_rate_window_seconds = 60

    class DatabaseSession:
        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            pass

    @contextmanager
    def database(_settings: object) -> Iterator[DatabaseSession]:
        yield DatabaseSession()

    monkeypatch.setattr(
        promo_http.Settings,
        "from_env",
        classmethod(lambda cls: SettingsFixture()),
    )
    monkeypatch.setattr(promo_http, "_database_session", database)
    monkeypatch.setattr(
        promo_http,
        "authenticate_display_client",
        lambda *_args, **_kwargs: DisplayClientPrincipal(uuid.uuid4(), uuid.uuid4()),
    )
    monkeypatch.setattr(
        promo_http.DisplayOutcomeRepository,
        "record",
        lambda *_args, **_kwargs: type(
            "Outcome",
            (),
            {
                "session_id": session_id,
                "status": "confirmed",
                "display_expires_at": expiry,
                "qr_fully_visible_elapsed_ms": 8421,
            },
        )(),
    )

    response = asyncio.run(
        route.endpoint(
            _request(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "confirmed",
                        "qr_fully_visible_elapsed_ms": 8421,
                    }
                ).encode()
            ),
            session_id,
        )
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert json.loads(response.body) == {
        "schema_version": 1,
        "session_id": str(session_id),
        "status": "confirmed",
        "display_expires_at": "2026-08-27T07:00:20Z",
        "qr_fully_visible_elapsed_ms": 8421,
    }

    monkeypatch.setattr(
        promo_http,
        "authenticate_display_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            InvalidDisplayClientCredentials()
        ),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            route.endpoint(
                _request(
                    json.dumps(
                        {"schema_version": 1, "status": "failed"}
                    ).encode()
                ),
                session_id,
            )
        )
    assert error.value.status_code == 401
    assert error.value.headers == {"Cache-Control": "no-store"}

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.entrypoints import realtime
from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.promo import (
    ClientTimingReport,
    PromoAttempt,
    PromoAttemptRepository,
    PromoSession,
    ResultAssembly,
    parse_client_timing_report,
    project_core_timeline,
)
from face_moment.serving_control import DisplayClientRepository, IngestTargetRepository
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


REVISION = "0015_promo_attempt_client_timing"
PREDECESSOR = "0014_promo_browser_access"
QR_SECRET = "task083-disposable-qr-secret"


@dataclass(frozen=True, slots=True)
class TimingState:
    app: FastAPI
    engine: Engine
    spa_id: uuid.UUID
    token: str
    foreign_token: str
    migration_observations: dict[str, object]


@pytest.fixture(scope="module")
def timing_state() -> Iterator[TimingState]:
    environment = pytest.MonkeyPatch()
    base_settings = Settings.from_env()
    database_name = f"task083_{uuid.uuid4().hex}"
    probe_url = make_url(base_settings.database_url).set(database=database_name)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {database_name}")
    environment.setenv("DATABASE_URL", probe_url.render_as_string(hide_password=False))
    engine = create_engine(probe_url, pool_pre_ping=True)
    try:
        migration_observations = _exercise_migration(engine)
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime(2026, 8, 28, 0, 0, tzinfo=timezone.utc),
                **PIPELINE_COMPATIBILITY,
            )
            first_target = IngestTargetRepository(session).configure_spa(
                name=f"task083-primary-{database_name}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            second_target = IngestTargetRepository(session).configure_spa(
                name=f"task083-foreign-{database_name}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            first_client = DisplayClientRepository(session).provision(
                spa_id=first_target.spa_id,
                name=f"task083-client-{database_name}",
            )
            second_client = DisplayClientRepository(session).provision(
                spa_id=second_target.spa_id,
                name=f"task083-foreign-client-{database_name}",
            )
            session.commit()
            spa_id = first_target.spa_id
            token = first_client.token_value
            foreign_token = second_client.token_value

        app = realtime.create_app()
        app.state.role_state.update(
            {
                "ready": True,
                "session_factory": lambda: Session(engine),
                "display_client_rate_limiter": DisplayClientRateLimiter(
                    limit=100, window_seconds=60
                ),
            }
        )
        yield TimingState(
            app=app,
            engine=engine,
            spa_id=spa_id,
            token=token,
            foreign_token=foreign_token,
            migration_observations=migration_observations,
        )
    finally:
        engine.dispose()
        environment.undo()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)"
            )
        admin_engine.dispose()


def test_next_linear_migration_round_trip_preserves_core_attempt_truth(
    timing_state: TimingState,
) -> None:
    observations = timing_state.migration_observations
    assert observations["down_revision"] == PREDECESSOR
    assert observations["column_after_upgrade"] is True
    assert observations["constraint_after_upgrade"] is True
    assert observations["column_after_downgrade"] is False
    assert observations["preserved_after_downgrade"] == (
        "no_success",
        "no_proposals",
        220,
    )
    assert observations["marker_after_reupgrade"] is None


def test_edge_routes_timing_child_to_realtime_unauthenticated_no_store(
    timing_state: TimingState,
) -> None:
    caddyfile = Path("deploy/Caddyfile").read_text()
    assert (
        "\t@realtime_attempts path /api/realtime/attempts "
        "/api/realtime/attempts/*/client-timing\n"
        "\n"
        "\troute {"
    ) in caddyfile
    assert (
        "\t\thandle @realtime_attempts {\n"
        "\t\t\trequest_body {\n"
        "\t\t\t\tmax_size 20MiB\n"
        "\t\t\t}\n"
        "\t\t\treverse_proxy realtime:8002 {"
    ) in caddyfile

    status, headers, _ = _request(
        timing_state.app,
        attempt_id=str(uuid.uuid4()),
        token=None,
        payload={"schema_version": 1, "response_received_ms": 842},
    )
    assert status == 401
    assert headers["cache-control"] == "no-store"


def test_terminal_outcome_matrix_accepts_ordered_marker_and_projects_gap(
    timing_state: TimingState,
) -> None:
    _reset_limiter(timing_state)
    outcomes = ("result", "no_proposals", "busy", "deadline", "internal_failure")
    for index, outcome in enumerate(outcomes):
        client_attempt_id = _seed_terminal_attempt(
            timing_state.engine,
            spa_id=timing_state.spa_id,
            outcome=outcome,
        )
        with Session(timing_state.engine) as session:
            attempt = PromoAttemptRepository(session).get_by_admission_key(
                spa_id=timing_state.spa_id,
                client_attempt_id=client_attempt_id,
            )
            before = project_core_timeline(attempt)
            assert before.response_received_ms is None
            assert "response_receipt_missing" in before.issue_tags
            participant_truth = (
                attempt.processing_status,
                attempt.domain_outcome,
                attempt.display_status,
            )

        marker = 842 + index
        status, headers, body = _request(
            timing_state.app,
            attempt_id=str(client_attempt_id),
            token=timing_state.token,
            payload={"schema_version": 1, "response_received_ms": marker},
        )
        assert status == 200
        assert headers["cache-control"] == "no-store"
        assert body == {
            "schema_version": 1,
            "attempt_id": str(client_attempt_id),
            "response_received_ms": marker,
        }
        with Session(timing_state.engine) as session:
            attempt = PromoAttemptRepository(session).get_by_admission_key(
                spa_id=timing_state.spa_id,
                client_attempt_id=client_attempt_id,
            )
            after = project_core_timeline(attempt)
            assert after.response_received_ms == marker
            assert "response_receipt_missing" not in after.issue_tags
            assert (
                attempt.processing_status,
                attempt.domain_outcome,
                attempt.display_status,
            ) == participant_truth


def test_core_timeline_derives_expired_display_unconfirmed_without_mutation(
    timing_state: TimingState,
) -> None:
    client_attempt_id = _seed_terminal_attempt(
        timing_state.engine,
        spa_id=timing_state.spa_id,
        outcome="result",
    )
    with Session(timing_state.engine) as session:
        attempt = PromoAttemptRepository(session).get_by_admission_key(
            spa_id=timing_state.spa_id,
            client_attempt_id=client_attempt_id,
        )
        result_session = session.scalar(
            select(PromoSession).where(PromoSession.attempt_id == attempt.id)
        )
        assert result_session is not None
        assert attempt.display_expires_at is not None

        stored_attempt_truth = (
            attempt.processing_status,
            attempt.domain_outcome,
            attempt.display_status,
            attempt.display_expires_at,
            attempt.display_reported_at,
            attempt.qr_fully_visible_elapsed_ms,
        )
        stored_session_truth = (
            result_session.id,
            tuple(result_session.session_result_photo_ids),
            tuple(result_session.teaser_photo_ids),
            result_session.n,
            result_session.qr_issued_at,
            result_session.qr_first_open_expires_at,
        )
        before_expiry = project_core_timeline(
            attempt,
            now=attempt.display_expires_at - timedelta(microseconds=1),
        )
        at_expiry = project_core_timeline(attempt, now=attempt.display_expires_at)
        after_expiry = project_core_timeline(
            attempt,
            now=attempt.display_expires_at + timedelta(minutes=1),
        )

        assert before_expiry.display_status == "pending"
        assert "display_unconfirmed" not in before_expiry.issue_tags
        assert (
            at_expiry.display_status
            == after_expiry.display_status
            == "unconfirmed"
        )
        assert "display_unconfirmed" in at_expiry.issue_tags
        assert "display_unconfirmed" in after_expiry.issue_tags
        assert not session.dirty

        session.expire_all()
        persisted_attempt = PromoAttemptRepository(session).get_by_admission_key(
            spa_id=timing_state.spa_id,
            client_attempt_id=client_attempt_id,
        )
        persisted_session = session.scalar(
            select(PromoSession).where(PromoSession.attempt_id == persisted_attempt.id)
        )
        assert persisted_session is not None
        assert (
            persisted_attempt.processing_status,
            persisted_attempt.domain_outcome,
            persisted_attempt.display_status,
            persisted_attempt.display_expires_at,
            persisted_attempt.display_reported_at,
            persisted_attempt.qr_fully_visible_elapsed_ms,
        ) == stored_attempt_truth
        assert (
            persisted_session.id,
            tuple(persisted_session.session_result_photo_ids),
            tuple(persisted_session.teaser_photo_ids),
            persisted_session.n,
            persisted_session.qr_issued_at,
            persisted_session.qr_first_open_expires_at,
        ) == stored_session_truth


def test_first_equal_conflicting_foreign_invalid_and_missing_reports_are_safe(
    timing_state: TimingState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _reset_limiter(timing_state)
    client_attempt_id = _seed_terminal_attempt(
        timing_state.engine,
        spa_id=timing_state.spa_id,
        outcome="no_proposals",
    )
    with Session(timing_state.engine) as session:
        count_before = session.scalar(select(func.count()).select_from(PromoAttempt))
        attempt = PromoAttemptRepository(session).get_by_admission_key(
            spa_id=timing_state.spa_id,
            client_attempt_id=client_attempt_id,
        )
        participant_truth = (
            attempt.processing_status,
            attempt.domain_outcome,
            attempt.display_status,
        )

    first = _request(
        timing_state.app,
        attempt_id=str(client_attempt_id),
        token=timing_state.token,
        payload={"schema_version": 1, "response_received_ms": 842},
    )
    equal = _request(
        timing_state.app,
        attempt_id=str(client_attempt_id),
        token=timing_state.token,
        payload={"schema_version": 1, "response_received_ms": 842},
    )
    conflict = _request(
        timing_state.app,
        attempt_id=str(client_attempt_id),
        token=timing_state.token,
        payload={"schema_version": 1, "response_received_ms": 843},
    )
    foreign = _request(
        timing_state.app,
        attempt_id=str(client_attempt_id),
        token=timing_state.foreign_token,
        payload={"schema_version": 1, "response_received_ms": 842},
    )
    unknown_id = uuid.uuid4()
    unknown = _request(
        timing_state.app,
        attempt_id=str(unknown_id),
        token=timing_state.token,
        payload={"schema_version": 1, "response_received_ms": 842},
    )
    invalid = _request(
        timing_state.app,
        attempt_id=str(client_attempt_id),
        token=timing_state.token,
        payload={"schema_version": 1, "response_received_ms": 219},
    )
    invalid_shape = _request(
        timing_state.app,
        attempt_id=str(client_attempt_id),
        token=timing_state.token,
        payload={
            "schema_version": 1,
            "response_received_ms": 842,
            "unknown": True,
        },
    )
    invalid_uuid = _request(
        timing_state.app,
        attempt_id="not-a-uuid",
        token=timing_state.token,
        payload={"schema_version": 1, "response_received_ms": 842},
    )
    unauthenticated = _request(
        timing_state.app,
        attempt_id=str(client_attempt_id),
        token=None,
        payload={"schema_version": 1, "response_received_ms": 842},
    )

    assert first[0] == equal[0] == 200
    assert first[2] == equal[2]
    assert conflict[0] == 409
    assert foreign[0] == unknown[0] == 404
    assert foreign[2] == unknown[2]
    assert invalid[0] == invalid_shape[0] == invalid_uuid[0] == 422
    assert unauthenticated[0] == 401
    for response in (
        first,
        equal,
        conflict,
        foreign,
        unknown,
        invalid,
        invalid_shape,
        invalid_uuid,
        unauthenticated,
    ):
        assert response[1]["cache-control"] == "no-store"

    with Session(timing_state.engine) as session:
        attempt = PromoAttemptRepository(session).get_by_admission_key(
            spa_id=timing_state.spa_id,
            client_attempt_id=client_attempt_id,
        )
        assert attempt.response_received_ms == 842
        assert (
            attempt.processing_status,
            attempt.domain_outcome,
            attempt.display_status,
        ) == participant_truth
        assert session.scalar(select(func.count()).select_from(PromoAttempt)) == count_before
        assert session.scalar(
            select(func.count()).select_from(PromoAttempt).where(
                PromoAttempt.client_attempt_id == unknown_id
            )
        ) == 0

    assert timing_state.token not in caplog.text
    assert timing_state.foreign_token not in caplog.text
    assert str(client_attempt_id) not in caplog.text


def test_nonterminal_and_rate_limited_reports_change_no_owner_state(
    timing_state: TimingState,
) -> None:
    _reset_limiter(timing_state)
    client_attempt_id = _seed_accepted_attempt(
        timing_state.engine, spa_id=timing_state.spa_id
    )
    nonterminal = _request(
        timing_state.app,
        attempt_id=str(client_attempt_id),
        token=timing_state.token,
        payload={"schema_version": 1, "response_received_ms": 842},
    )
    assert nonterminal[0] == 409
    assert nonterminal[1]["cache-control"] == "no-store"
    with Session(timing_state.engine) as session:
        attempt = PromoAttemptRepository(session).get_by_admission_key(
            spa_id=timing_state.spa_id,
            client_attempt_id=client_attempt_id,
        )
        assert attempt.processing_status == "accepted"
        assert attempt.response_received_ms is None

    timing_state.app.state.role_state["display_client_rate_limiter"] = (
        DisplayClientRateLimiter(limit=1, window_seconds=60)
    )
    unknown_id = uuid.uuid4()
    allowed = _request(
        timing_state.app,
        attempt_id=str(unknown_id),
        token=timing_state.token,
        payload={"schema_version": 1, "response_received_ms": 842},
    )
    limited = _request(
        timing_state.app,
        attempt_id=str(unknown_id),
        token=timing_state.token,
        payload={"schema_version": 1, "response_received_ms": 842},
    )
    assert allowed[0] == 404
    assert limited[0] == 429
    assert allowed[1]["cache-control"] == limited[1]["cache-control"] == "no-store"
    with Session(timing_state.engine) as session:
        assert session.scalar(
            select(func.count()).select_from(PromoAttempt).where(
                PromoAttempt.client_attempt_id == unknown_id
            )
        ) == 0


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b'{"schema_version":1,"response_received_ms":true}', "application/json"),
        (b'{"schema_version":2,"response_received_ms":842}', "application/json"),
        (b'{"schema_version":1,"response_received_ms":-1}', "application/json"),
        (b'{"schema_version":1,"response_received_ms":1.5}', "application/json"),
        (
            b'{"schema_version":1,"response_received_ms":842,"response_received_ms":843}',
            "application/json",
        ),
        (b'{"schema_version":1,"response_received_ms":842}', "text/plain"),
    ],
)
def test_exact_v1_parser_rejects_invalid_type_version_range_duplicates_and_media(
    body: bytes, content_type: str
) -> None:
    with pytest.raises(ValueError):
        parse_client_timing_report(body, content_type)


def _exercise_migration(engine: Engine) -> dict[str, object]:
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None
    alembic_command.upgrade(config, PREDECESSOR)
    old_metadata = MetaData()
    old_attempts = Table(
        "promo_attempts",
        old_metadata,
        schema=APP_SCHEMA,
        autoload_with=engine,
    )
    row_id = uuid.uuid4()
    values = _attempt_values(spa_id=uuid.uuid4(), client_attempt_id=uuid.uuid4())
    with engine.begin() as connection:
        connection.execute(
            old_attempts.insert().values(
                id=row_id,
                **values,
                processing_status="no_success",
                domain_outcome="no_proposals",
            )
        )

    alembic_command.upgrade(config, REVISION)
    column_after_upgrade = "response_received_ms" in {
        column["name"]
        for column in inspect(engine).get_columns("promo_attempts", schema=APP_SCHEMA)
    }
    constraint_after_upgrade = "ck_promo_attempts_client_response_order" in {
        constraint["name"]
        for constraint in inspect(engine).get_check_constraints(
            "promo_attempts", schema=APP_SCHEMA
        )
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE face_moment.promo_attempts SET response_received_ms = 842 "
                "WHERE id = :id"
            ),
            {"id": row_id},
        )

    alembic_command.downgrade(config, PREDECESSOR)
    column_after_downgrade = "response_received_ms" in {
        column["name"]
        for column in inspect(engine).get_columns("promo_attempts", schema=APP_SCHEMA)
    }
    with engine.connect() as connection:
        preserved = connection.execute(
            text(
                "SELECT processing_status, domain_outcome, request_started_ms "
                "FROM face_moment.promo_attempts WHERE id = :id"
            ),
            {"id": row_id},
        ).one()

    alembic_command.upgrade(config, REVISION)
    with engine.begin() as connection:
        marker_after_reupgrade = connection.scalar(
            text(
                "SELECT response_received_ms FROM face_moment.promo_attempts "
                "WHERE id = :id"
            ),
            {"id": row_id},
        )
        connection.execute(
            text("DELETE FROM face_moment.promo_attempts WHERE id = :id"),
            {"id": row_id},
        )
    return {
        "down_revision": revision.down_revision,
        "column_after_upgrade": column_after_upgrade,
        "constraint_after_upgrade": constraint_after_upgrade,
        "column_after_downgrade": column_after_downgrade,
        "preserved_after_downgrade": tuple(preserved),
        "marker_after_reupgrade": marker_after_reupgrade,
    }


def _attempt_values(
    *, spa_id: uuid.UUID, client_attempt_id: uuid.UUID
) -> dict[str, object]:
    return {
        "spa_id": spa_id,
        "client_attempt_id": client_attempt_id,
        "trigger_source": "test",
        "client_release": "task083-client",
        "detector_id": "mediapipe_blazeface_full_range",
        "model_version": "task083-model",
        "jpeg_quality": 85,
        "camera_device_id": "task083-camera",
        "reference_series_ready_at": datetime(
            2026, 8, 28, 0, 0, tzinfo=timezone.utc
        ),
        "local_detection_completed_ms": 120,
        "request_started_ms": 220,
        "proposal_count": 4,
        "settings_revision": 4,
        "visit_date": date(2026, 8, 28),
        "pipeline_revision_id": uuid.uuid4(),
        "pipeline_code": PipelineCode.OPENCV_SFACE,
        "query_source": "reference",
        "threshold": 0.7,
        "quality_settings": {"version": 1},
        "release_id": "task083-server",
        "deadline_ms": 3000,
        "calibration_id": None,
    }


def _seed_accepted_attempt(engine: Engine, *, spa_id: uuid.UUID) -> uuid.UUID:
    client_attempt_id = uuid.uuid4()
    with Session(engine) as session:
        PromoAttemptRepository(session).create_or_get(
            **_attempt_values(spa_id=spa_id, client_attempt_id=client_attempt_id)
        )
        session.commit()
    return client_attempt_id


def _seed_terminal_attempt(
    engine: Engine, *, spa_id: uuid.UUID, outcome: str
) -> uuid.UUID:
    client_attempt_id = uuid.uuid4()
    now = datetime(2026, 8, 28, 0, 1, tzinfo=timezone.utc)
    with Session(engine) as session:
        repository = PromoAttemptRepository(session)
        attempt = repository.create_or_get(
            **_attempt_values(spa_id=spa_id, client_attempt_id=client_attempt_id)
        )
        if outcome == "result":
            repository.mark_search_started(attempt, now=now)
            photos = tuple(uuid.uuid4() for _ in range(4))
            repository.publish_result(
                attempt,
                ResultAssembly(
                    outcome="result",
                    session_result_photo_ids=photos,
                    teaser_photo_ids=photos,
                    n=4,
                ),
                qr_ticket_secret=QR_SECRET,
                qr_issued_at=now + timedelta(seconds=1),
                display_expires_at=now + timedelta(minutes=5),
            )
        elif outcome == "no_proposals":
            repository.mark_no_proposals(attempt, now=now)
        elif outcome == "busy":
            repository.mark_busy(attempt, now=now)
        elif outcome == "deadline":
            repository.mark_search_started(attempt, now=now)
            repository.mark_deadline(attempt, now=now + timedelta(seconds=1))
        elif outcome == "internal_failure":
            repository.mark_internal_failure(attempt, now=now)
        else:
            raise AssertionError(f"unsupported fixture outcome: {outcome}")
        session.commit()
    return client_attempt_id


def _reset_limiter(state: TimingState) -> None:
    state.app.state.role_state["display_client_rate_limiter"] = (
        DisplayClientRateLimiter(limit=100, window_seconds=60)
    )


def _request(
    app: FastAPI,
    *,
    attempt_id: str,
    token: str | None,
    payload: dict[str, object] | bytes,
    content_type: str = "application/json",
) -> tuple[int, dict[str, str], dict[str, Any]]:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
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
    path = f"/api/realtime/attempts/{attempt_id}/client-timing"
    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
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
    response_headers = {
        key.decode().casefold(): value.decode() for key, value in start["headers"]
    }
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return int(start["status"]), response_headers, json.loads(response_body or b"{}")

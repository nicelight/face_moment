from __future__ import annotations

from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
import uuid

from alembic import command as alembic_command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.promo import (
    AttemptInvestigationFilters,
    AttemptInvestigationProjection,
    PromoAttempt,
    query_attempts,
)


_STATES = (
    "accepted",
    "searching",
    "result_issued",
    "no_success",
    "interrupted",
    "deadline",
    "internal_failure",
)


@pytest.fixture
def disposable_attempt_query_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Engine]:
    base_settings = Settings.from_env()
    probe_database = f"task088_{uuid.uuid4().hex}"
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


def test_query_applies_exact_conjunctive_filters_and_returns_core_truth(
    disposable_attempt_query_engine: Engine,
) -> None:
    window_start = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)
    target_id = uuid.UUID("80000000-0000-0000-0000-000000000008")
    target_correlation_id = uuid.UUID("90000000-0000-0000-0000-000000000008")

    with Session(disposable_attempt_query_engine) as session:
        attempts = []
        for position, state in enumerate(_STATES):
            attempt_id = target_id if state == "result_issued" else uuid.uuid4()
            correlation_id = (
                target_correlation_id
                if state == "result_issued"
                else uuid.uuid4()
            )
            attempts.append(
                _attempt(
                    attempt_id=attempt_id,
                    correlation_id=correlation_id,
                    created_at=window_start + timedelta(minutes=position),
                    processing_status=state,
                )
            )
        outside_upper = _attempt(
            attempt_id=uuid.uuid4(),
            correlation_id=uuid.uuid4(),
            created_at=window_start + timedelta(hours=1),
            processing_status="result_issued",
        )
        session.add_all((*attempts, outside_upper))
        session.commit()

        owner_before = session.execute(
            select(
                PromoAttempt.id,
                PromoAttempt.processing_status,
                PromoAttempt.domain_outcome,
                PromoAttempt.updated_at,
            ).order_by(PromoAttempt.id)
        ).all()

        target = query_attempts(
            session,
            filters=AttemptInvestigationFilters(
                attempt_id=target_id,
                correlation_id=target_correlation_id,
                created_at_from=window_start,
                created_at_to=window_start + timedelta(hours=1),
                processing_status="result_issued",
            ),
        )

        assert len(target) == 1
        projection = target[0]
        assert isinstance(projection, AttemptInvestigationProjection)
        assert not isinstance(projection, PromoAttempt)
        assert projection.attempt_id == target_id
        assert projection.correlation_id == target_correlation_id
        assert projection.spa_id == attempts[2].spa_id
        assert projection.created_at == window_start + timedelta(minutes=2)
        assert projection.processing_status == "result_issued"
        assert projection.domain_outcome == "result"
        assert projection.timeline.created_at == projection.created_at
        assert projection.timeline.processing_status == projection.processing_status
        assert projection.timeline.domain_outcome == projection.domain_outcome
        assert projection.timeline.reference_series_ready_elapsed_ms == 0
        assert projection.timeline.local_detection_completed_ms == 140
        assert projection.timeline.request_started_ms == 220
        assert projection.timeline.response_received_ms == 360
        assert projection.timeline.slot_decided_at is not None
        assert projection.timeline.search_started_at is not None
        assert projection.timeline.search_finished_at is not None
        assert projection.timeline.display_status == "confirmed"
        assert projection.timeline.qr_fully_visible_elapsed_ms == 9_500

        with pytest.raises(FrozenInstanceError):
            projection.processing_status = "searching"  # type: ignore[misc]

        mismatched_identity = query_attempts(
            session,
            filters=AttemptInvestigationFilters(
                attempt_id=target_id,
                correlation_id=attempts[0].client_attempt_id,
            ),
        )
        assert mismatched_identity == ()

        bounded = query_attempts(
            session,
            filters=AttemptInvestigationFilters(
                created_at_from=window_start,
                created_at_to=window_start + timedelta(hours=1),
            ),
        )
        assert [item.processing_status for item in bounded] == list(
            reversed(_STATES)
        )

        for state in _STATES:
            matching = query_attempts(
                session,
                filters=AttemptInvestigationFilters(processing_status=state),
            )
            assert matching
            assert all(item.processing_status == state for item in matching)

        owner_after = session.execute(
            select(
                PromoAttempt.id,
                PromoAttempt.processing_status,
                PromoAttempt.domain_outcome,
                PromoAttempt.updated_at,
            ).order_by(PromoAttempt.id)
        ).all()
        assert owner_after == owner_before
        assert not session.dirty
        assert not session.new
        assert not session.deleted


def test_query_orders_deterministically_and_caps_at_one_hundred(
    disposable_attempt_query_engine: Engine,
) -> None:
    tied_created_at = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)
    attempt_ids = [uuid.UUID(int=value) for value in range(1, 103)]

    with Session(disposable_attempt_query_engine) as session:
        session.add_all(
            _attempt(
                attempt_id=attempt_id,
                correlation_id=uuid.uuid4(),
                created_at=tied_created_at,
                processing_status="accepted",
            )
            for attempt_id in attempt_ids
        )
        session.commit()

        results = query_attempts(
            session,
            filters=AttemptInvestigationFilters(),
        )

        assert len(results) == 100
        assert [item.attempt_id for item in results] == sorted(
            attempt_ids, reverse=True
        )[:100]


@pytest.mark.parametrize(
    "filters",
    (
        AttemptInvestigationFilters,
    ),
)
def test_filter_type_is_public(filters: type[AttemptInvestigationFilters]) -> None:
    assert filters() == AttemptInvestigationFilters()


def test_filters_reject_non_utc_invalid_state_and_empty_time_range() -> None:
    with pytest.raises(ValueError, match="UTC"):
        AttemptInvestigationFilters(
            created_at_from=datetime(2026, 8, 31, 9, 0),
        )
    with pytest.raises(ValueError, match="UTC"):
        AttemptInvestigationFilters(
            created_at_to=datetime(
                2026,
                8,
                31,
                9,
                0,
                tzinfo=timezone(timedelta(hours=3)),
            ),
        )
    with pytest.raises(ValueError, match="processing_status"):
        AttemptInvestigationFilters(processing_status="unknown")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="later"):
        AttemptInvestigationFilters(
            created_at_from=datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc),
            created_at_to=datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc),
        )


def _attempt(
    *,
    attempt_id: uuid.UUID,
    correlation_id: uuid.UUID,
    created_at: datetime,
    processing_status: str,
) -> PromoAttempt:
    terminal = processing_status not in {"accepted", "searching"}
    domain_outcome = {
        "result_issued": "result",
        "no_success": "busy",
        "interrupted": "interrupted",
        "deadline": "deadline",
    }.get(processing_status)
    return PromoAttempt(
        id=attempt_id,
        spa_id=uuid.uuid4(),
        client_attempt_id=correlation_id,
        trigger_source="test",
        client_release="kiosk-task088",
        detector_id="mediapipe-blazeface-full-range",
        model_version="1",
        jpeg_quality=82,
        camera_device_id="camera-task088",
        reference_series_ready_at=created_at - timedelta(milliseconds=220),
        local_detection_completed_ms=140,
        request_started_ms=220,
        response_received_ms=360 if terminal else None,
        proposal_count=3,
        settings_revision=4,
        visit_date=date(2026, 8, 31),
        pipeline_revision_id=uuid.uuid4(),
        pipeline_code="opencv_sface",
        query_source="reference",
        release_id="server-task088",
        threshold=0.71,
        quality_settings={"version": 1, "minimum_edge": 48},
        calibration_id=None,
        deadline_ms=3_000,
        slot_decided_at=(created_at + timedelta(milliseconds=10)) if terminal else None,
        search_started_at=(created_at + timedelta(milliseconds=20)) if terminal else None,
        search_finished_at=(created_at + timedelta(milliseconds=50)) if terminal else None,
        processing_status=processing_status,
        domain_outcome=domain_outcome,
        display_status="confirmed" if processing_status == "result_issued" else "not_applicable",
        display_expires_at=(created_at + timedelta(seconds=10)) if processing_status == "result_issued" else None,
        display_reported_at=(created_at + timedelta(seconds=1)) if processing_status == "result_issued" else None,
        qr_fully_visible_elapsed_ms=9_500 if processing_status == "result_issued" else None,
        created_at=created_at,
        updated_at=created_at,
    )

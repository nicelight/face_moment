from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
import threading
import time
import uuid

from alembic import command as alembic_command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.processing import PipelineCode
from face_moment.promo import (
    PromoAttempt,
    PromoAttemptRepository,
    RealtimeOrchestrator,
    RealtimeProcessingOutcome,
)
from face_moment.promo.realtime_admission import (
    MultipartPart,
    RealtimeAdmissionPayload,
    admission_values,
)
from face_moment.serving_control.realtime_context import (
    QuerySource,
    RealtimeContext,
)


@dataclass
class RecordingAttemptRepository:
    calls: list[str]

    def mark_busy(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt:
        del now
        self.calls.append("busy")
        attempt.processing_status = "no_success"
        attempt.domain_outcome = "busy"
        return attempt

    def mark_search_started(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt:
        del now
        self.calls.append("search_started")
        attempt.processing_status = "searching"
        return attempt

    def mark_deadline(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt:
        del now
        self.calls.append("deadline")
        attempt.processing_status = "deadline"
        attempt.domain_outcome = "deadline"
        return attempt

    def mark_internal_failure(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt:
        del now
        self.calls.append("internal_failure")
        attempt.processing_status = "internal_failure"
        return attempt


class ManualClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def _attempt(deadline_ms: int = 3000) -> PromoAttempt:
    return PromoAttempt(deadline_ms=deadline_ms, processing_status="accepted")


def _slot() -> threading.BoundedSemaphore:
    return threading.BoundedSemaphore(1)


@pytest.fixture
def disposable_orchestration_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Engine]:
    base_settings = Settings.from_env()
    probe_database = f"task073_{uuid.uuid4().hex}"
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


def _persisted_attempt_values(
    *, spa_id: uuid.UUID, deadline_ms: int = 5000
) -> dict[str, object]:
    return {
        "spa_id": spa_id,
        "client_attempt_id": uuid.uuid4(),
        "trigger_source": "test",
        "client_release": "task073-test",
        "detector_id": "task073-detector",
        "model_version": "task073-model",
        "jpeg_quality": 85,
        "camera_device_id": "task073-camera",
        "reference_series_ready_at": datetime(2026, 8, 22, tzinfo=timezone.utc),
        "local_detection_completed_ms": 1,
        "request_started_ms": 2,
        "proposal_count": 1,
        "settings_revision": 1,
        "visit_date": date(2026, 8, 22),
        "pipeline_revision_id": uuid.uuid4(),
        "pipeline_code": PipelineCode.OPENCV_SFACE,
        "query_source": "reference",
        "threshold": 0.7,
        "quality_settings": {},
        "release_id": "task073-server",
        "deadline_ms": deadline_ms,
    }


def test_held_slot_marks_concurrent_attempt_busy_without_inference_and_allows_fresh_acquisition() -> None:
    repository = RecordingAttemptRepository([])
    orchestrator = RealtimeOrchestrator(repository, slot=_slot())
    owner = _attempt(5000)
    busy = _attempt(5000)
    fresh = _attempt(5000)
    owner_started = threading.Event()
    release_owner = threading.Event()
    processing_calls: list[str] = []

    def owner_process() -> str:
        processing_calls.append("owner")
        owner_started.set()
        assert release_owner.wait(timeout=2)
        return "owner-result"

    def busy_process() -> str:
        processing_calls.append("busy")
        return "must-not-run"

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner_future = executor.submit(orchestrator.run, owner, owner_process)
        assert owner_started.wait(timeout=2)
        busy_future = executor.submit(orchestrator.run, busy, busy_process)
        busy_outcome = busy_future.result(timeout=1)
        assert busy_outcome.outcome == "busy"
        assert busy.processing_status == "no_success"
        assert busy.domain_outcome == "busy"
        assert processing_calls == ["owner"]
        release_owner.set()
        owner_outcome = owner_future.result(timeout=2)

    assert owner_outcome.outcome == "processing"
    assert owner_outcome.value == "owner-result"
    fresh_outcome = orchestrator.run(
        fresh, lambda: processing_calls.append("fresh") or "fresh-result"
    )
    assert fresh_outcome.outcome == "processing"
    assert fresh_outcome.value == "fresh-result"
    assert processing_calls == ["owner", "fresh"]


def test_persisted_concurrency_records_owner_busy_timing_and_fresh_attempt(
    disposable_orchestration_engine: Engine,
) -> None:
    spa_id = uuid.uuid4()
    with Session(disposable_orchestration_engine) as session:
        repository = PromoAttemptRepository(session)
        owner = repository.create_or_get(**_persisted_attempt_values(spa_id=spa_id))
        busy = repository.create_or_get(**_persisted_attempt_values(spa_id=spa_id))
        fresh = repository.create_or_get(**_persisted_attempt_values(spa_id=spa_id))
        owner_id, busy_id, fresh_id = owner.id, busy.id, fresh.id
        session.commit()

    slot = _slot()
    owner_started = threading.Event()
    release_owner = threading.Event()
    processing_calls: list[str] = []

    def owner_process() -> str:
        processing_calls.append("owner")
        owner_started.set()
        assert release_owner.wait(timeout=2)
        return "owner-result"

    def run_attempt(
        attempt_id: uuid.UUID,
        process: Callable[[], str],
    ) -> RealtimeProcessingOutcome[str]:
        with Session(disposable_orchestration_engine) as session:
            attempt = session.get(PromoAttempt, attempt_id)
            assert attempt is not None
            result = RealtimeOrchestrator(
                PromoAttemptRepository(session), slot=slot
            ).run(attempt, process)
            session.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner_future = executor.submit(run_attempt, owner_id, owner_process)
        assert owner_started.wait(timeout=2)
        busy_started = time.monotonic()
        busy_future = executor.submit(
            run_attempt,
            busy_id,
            lambda: processing_calls.append("busy") or "must-not-run",
        )
        busy_outcome = busy_future.result(timeout=1)
        busy_elapsed = time.monotonic() - busy_started
        assert busy_outcome.outcome == "busy"
        assert busy_elapsed < 1
        assert not release_owner.is_set()
        release_owner.set()
        owner_outcome = owner_future.result(timeout=2)

    assert owner_outcome.outcome == "processing"
    fresh_outcome = run_attempt(fresh_id, lambda: "fresh-result")
    assert fresh_outcome.outcome == "processing"
    assert processing_calls == ["owner"]

    with Session(disposable_orchestration_engine) as session:
        rows = {
            row.id: row
            for row in session.scalars(
                select(PromoAttempt).where(
                    PromoAttempt.id.in_((owner_id, busy_id, fresh_id))
                )
            )
        }
    assert rows[owner_id].processing_status == "searching"
    assert rows[owner_id].slot_decided_at is not None
    assert rows[owner_id].search_started_at is not None
    assert rows[busy_id].processing_status == "no_success"
    assert rows[busy_id].domain_outcome == "busy"
    assert rows[busy_id].slot_decided_at is not None
    assert rows[busy_id].search_finished_at is not None
    assert rows[busy_id].search_started_at is None
    assert rows[fresh_id].processing_status == "searching"


def test_late_processing_value_is_discarded_and_attempt_is_deadline() -> None:
    clock = ManualClock()
    repository = RecordingAttemptRepository([])
    orchestrator = RealtimeOrchestrator(repository, slot=_slot(), clock=clock)
    attempt = _attempt(10)
    processing_calls: list[str] = []

    def late_process() -> str:
        processing_calls.append("native")
        clock.value = 0.011
        return "late-result"

    outcome = orchestrator.run(attempt, late_process, admitted_at=0.0)

    assert outcome.outcome == "deadline"
    assert outcome.value is None
    assert attempt.processing_status == "deadline"
    assert attempt.domain_outcome == "deadline"
    assert processing_calls == ["native"]
    assert repository.calls == ["search_started", "deadline"]


def test_persisted_late_processing_marks_deadline_without_a_result(
    disposable_orchestration_engine: Engine,
) -> None:
    spa_id = uuid.uuid4()
    with Session(disposable_orchestration_engine) as session:
        attempt = PromoAttemptRepository(session).create_or_get(
            **_persisted_attempt_values(spa_id=spa_id, deadline_ms=10)
        )
        attempt_id = attempt.id
        session.commit()

    clock = ManualClock()

    def late_process() -> str:
        clock.value = 0.011
        return "late-result"

    with Session(disposable_orchestration_engine) as session:
        persisted = session.get(PromoAttempt, attempt_id)
        assert persisted is not None
        outcome = RealtimeOrchestrator(
            PromoAttemptRepository(session), slot=_slot(), clock=clock
        ).run(persisted, late_process, admitted_at=0.0)
        session.commit()

    assert outcome.outcome == "deadline"
    assert outcome.value is None
    with Session(disposable_orchestration_engine) as session:
        persisted = session.get(PromoAttempt, attempt_id)
        assert persisted is not None
        assert persisted.processing_status == "deadline"
        assert persisted.domain_outcome == "deadline"
        assert persisted.search_finished_at is not None


def test_exception_releases_slot_and_only_fresh_attempt_acquires_afterward() -> None:
    repository = RecordingAttemptRepository([])
    orchestrator = RealtimeOrchestrator(repository, slot=_slot())
    failed = _attempt()
    fresh = _attempt()

    def failing_process() -> None:
        raise RuntimeError("native failure")

    failed_outcome = orchestrator.run(failed, failing_process)
    fresh_outcome = orchestrator.run(fresh, lambda: "fresh-result")

    assert failed_outcome.outcome == "internal_failure"
    assert failed.processing_status == "internal_failure"
    assert fresh_outcome.outcome == "processing"
    assert fresh_outcome.value == "fresh-result"
    assert repository.calls == [
        "search_started",
        "internal_failure",
        "search_started",
    ]


def test_configured_positive_deadline_is_copied_into_admission_values() -> None:
    context = RealtimeContext(
        settings_revision=1,
        spa_id=uuid.uuid4(),
        visit_date=date(2026, 8, 22),
        pipeline_revision_id=uuid.uuid4(),
        pipeline_code=PipelineCode.OPENCV_SFACE,
        query_source=QuerySource.REFERENCE,
        reference_threshold=0.7,
        min_query_face_quality=0.5,
        quality_settings={},
        calibration_id=None,
        release_id="task073-test",
    )
    payload = RealtimeAdmissionPayload(
        attempt_id=uuid.uuid4(),
        trigger_source="test",
        client_release="task073-test",
        detector_id="mediapipe_blazeface_full_range",
        model_version="task073-model",
        jpeg_quality=85,
        camera_device_id="task073-camera",
        reference_series_ready_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
        local_detection_completed_ms=1,
        request_started_ms=2,
        occurrences=(
            MultipartPart(
                name="crop_000",
                filename="crop_000.jpg",
                content_type="image/jpeg",
                body=b"jpeg",
            ),
        ),
    )

    values = admission_values(payload, context, deadline_ms=1250)

    assert values["deadline_ms"] == 1250

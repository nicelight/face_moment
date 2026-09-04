"""TASK-099 ordinary annotation retention evidence."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
import uuid

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.diagnostics.evidence import (
    DiagnosticEvidenceProvider,
    DiagnosticEvidenceRepository,
)
from face_moment.diagnostics.ground_truth_annotations import (
    GroundTruthAnnotation,
    GroundTruthAnnotationProvider,
)
from face_moment.promo.attempt import PromoAttempt
from face_moment.promo.retention import RetentionCleanupOutcome, run_retention_cleanup
from tests.disposable_postgresql import disposable_postgresql_engine


_NOW = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def disposable_annotation_retention_engine() -> Iterator[Engine]:
    with disposable_postgresql_engine("task099") as engine:
        yield engine


def test_scheduled_cleanup_deletes_old_annotations_and_preserves_cutoff_rows(
    disposable_annotation_retention_engine: Engine,
) -> None:
    engine = disposable_annotation_retention_engine
    old_with_evidence = _attempt(_NOW - timedelta(days=91))
    old_without_evidence = _attempt(_NOW - timedelta(days=90, microseconds=1))
    at_cutoff = _attempt(_NOW - timedelta(days=90))
    newer = _attempt(_NOW - timedelta(days=1))
    old_with_evidence_id = old_with_evidence.id
    old_ids = {old_with_evidence.id, old_without_evidence.id}
    retained_ids = {at_cutoff.id, newer.id}

    with Session(engine) as session:
        session.add_all((old_with_evidence, old_without_evidence, at_cutoff, newer))
        session.flush()
        evidence_provider = DiagnosticEvidenceProvider(session)
        assert evidence_provider.write(
            attempt_id=old_with_evidence.id,
            ordinary_manifest=_manifest(old_with_evidence.id),
            completeness="incomplete",
            gap_reason="response_receipt_missing",
            now=old_with_evidence.created_at,
        ).accepted
        annotations = GroundTruthAnnotationProvider(session)
        promoted_annotation = annotations.create(
            attempt_id=old_with_evidence.id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Scheduled Promoted 099",
            outcome="missed",
        )
        annotations.create(
            attempt_id=old_without_evidence.id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Scheduled No Evidence 099",
            outcome="missed",
        )
        annotations.create(
            attempt_id=at_cutoff.id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Equal Cutoff 099",
            outcome="missed",
        )
        annotations.create(
            attempt_id=newer.id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Newer 099",
            outcome="missed",
        )
        assert evidence_provider.promote_subset(
            attempt_id=old_with_evidence.id,
            promoted_subset={
                "schema_version": 1,
                "parameters": {"threshold": 0.72},
            },
            selected_annotation_ids=(promoted_annotation.annotation_id,),
            now=old_with_evidence.created_at,
        ).accepted
        promoted_before = DiagnosticEvidenceRepository(session).require(
            old_with_evidence.id
        ).promoted_subset
        session.commit()

    with Session(engine) as session:
        first = run_retention_cleanup(session, now=_NOW)
        assert first.exit_code == 0
        assert first.core_attempts_deleted == 2
        assert first.ordinary_evidence_expired == 1
        assert first.promoted_subsets_preserved == 1

    with Session(engine) as session:
        remaining_annotation_attempts = set(
            session.scalars(select(GroundTruthAnnotation.attempt_id)).all()
        )
        assert remaining_annotation_attempts.isdisjoint(old_ids)
        assert remaining_annotation_attempts == retained_ids
        promoted_after = DiagnosticEvidenceRepository(session).require(
            old_with_evidence_id
        )
        assert promoted_after.promoted_subset == promoted_before
        assert all(session.get(PromoAttempt, attempt_id) is None for attempt_id in old_ids)
        assert all(
            session.get(PromoAttempt, attempt_id) is not None
            for attempt_id in retained_ids
        )

    with Session(engine) as session:
        repeated = run_retention_cleanup(session, now=_NOW)
        assert repeated.exit_code == 0
        assert repeated.core_attempts_deleted == 0
        assert repeated.ordinary_evidence_expired == 0
        assert repeated.promoted_subsets_preserved == 0
        assert set(session.scalars(select(GroundTruthAnnotation.attempt_id)).all()) == retained_ids


def test_explicit_removal_deletes_annotations_and_preserves_promoted_snapshot(
    disposable_annotation_retention_engine: Engine,
) -> None:
    engine = disposable_annotation_retention_engine
    attempt = _attempt(_NOW)
    attempt_id = attempt.id
    with Session(engine) as session:
        session.add(attempt)
        session.flush()
        evidence_provider = DiagnosticEvidenceProvider(session)
        assert evidence_provider.write(
            attempt_id=attempt_id,
            ordinary_manifest=_manifest(attempt_id),
            completeness="incomplete",
            gap_reason="response_receipt_missing",
            now=_NOW,
        ).accepted
        annotations = GroundTruthAnnotationProvider(session)
        selected = annotations.create(
            attempt_id=attempt_id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Explicit Selected 099",
            outcome="missed",
        )
        annotations.create(
            attempt_id=attempt_id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Explicit Ordinary 099",
            outcome="missed",
        )
        assert evidence_provider.promote_subset(
            attempt_id=attempt_id,
            promoted_subset={"schema_version": 1, "parameters": {"threshold": 0.72}},
            selected_annotation_ids=(selected.annotation_id,),
            now=_NOW,
        ).accepted
        promoted_before = DiagnosticEvidenceRepository(session).require(
            attempt_id
        ).promoted_subset
        session.commit()

    with Session(engine) as session:
        provider = DiagnosticEvidenceProvider(session)
        first = provider.remove_ordinary(attempt_id=attempt_id, now=_NOW)
        assert first.accepted
        session.commit()

    with Session(engine) as session:
        evidence = DiagnosticEvidenceRepository(session).require(attempt_id)
        assert evidence.gap_reason == "ordinary_removed"
        assert evidence.ordinary_manifest is None
        assert evidence.ordinary_expired_at is None
        assert evidence.promoted_subset == promoted_before
        assert not session.scalars(
            select(GroundTruthAnnotation).where(
                GroundTruthAnnotation.attempt_id == attempt_id
            )
        ).all()
        first_updated_at = evidence.updated_at

    with Session(engine) as session:
        repeated = DiagnosticEvidenceProvider(session).remove_ordinary(
            attempt_id=attempt_id,
            now=_NOW + timedelta(seconds=1),
        )
        assert repeated.accepted
        session.commit()

    with Session(engine) as session:
        evidence = DiagnosticEvidenceRepository(session).require(attempt_id)
        assert evidence.updated_at == first_updated_at
        assert evidence.promoted_subset == promoted_before
        assert not session.scalars(
            select(GroundTruthAnnotation).where(
                GroundTruthAnnotation.attempt_id == attempt_id
            )
        ).all()


def test_scheduled_cleanup_serializes_with_in_flight_no_evidence_creation(
    disposable_annotation_retention_engine: Engine,
) -> None:
    engine = disposable_annotation_retention_engine
    attempt = _attempt(_NOW - timedelta(days=91))
    attempt_id = attempt.id
    with Session(engine) as setup_session:
        setup_session.add(attempt)
        setup_session.commit()

    cleanup_reached_barrier = Event()
    cleanup_finished = Event()
    cleanup_outcomes: list[RetentionCleanupOutcome] = []
    cleanup_errors: list[BaseException] = []

    def observe_cleanup_barrier(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if "pg_advisory_xact_lock" in statement:
            cleanup_reached_barrier.set()

    def cleanup() -> None:
        try:
            with Session(engine) as cleanup_session:
                cleanup_outcomes.append(
                    run_retention_cleanup(cleanup_session, now=_NOW)
                )
        except BaseException as error:  # pragma: no cover - surfaced below
            cleanup_errors.append(error)
        finally:
            cleanup_finished.set()

    writer_session = Session(engine)
    cleanup_thread = Thread(target=cleanup)
    try:
        GroundTruthAnnotationProvider(writer_session).create(
            attempt_id=attempt_id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Concurrent No Evidence 099",
            outcome="missed",
        )
        event.listen(engine, "before_cursor_execute", observe_cleanup_barrier)
        cleanup_thread.start()
        assert cleanup_reached_barrier.wait(timeout=5)
        assert not cleanup_finished.wait(timeout=0.2)

        writer_session.commit()
        assert cleanup_finished.wait(timeout=5)
        cleanup_thread.join(timeout=1)
    finally:
        writer_session.rollback()
        writer_session.close()
        event.remove(engine, "before_cursor_execute", observe_cleanup_barrier)
        if cleanup_thread.is_alive():
            cleanup_thread.join(timeout=5)

    assert not cleanup_errors
    assert len(cleanup_outcomes) == 1
    assert cleanup_outcomes[0].exit_code == 0
    assert cleanup_outcomes[0].core_attempts_deleted == 1
    with Session(engine) as inspection_session:
        assert inspection_session.get(PromoAttempt, attempt_id) is None
        assert not inspection_session.scalars(
            select(GroundTruthAnnotation).where(
                GroundTruthAnnotation.attempt_id == attempt_id
            )
        ).all()

    with Session(engine) as rerun_session:
        repeated = run_retention_cleanup(rerun_session, now=_NOW)
        assert repeated.exit_code == 0
        assert repeated.core_attempts_deleted == 0
        assert not rerun_session.scalars(
            select(GroundTruthAnnotation).where(
                GroundTruthAnnotation.attempt_id == attempt_id
            )
        ).all()


def _attempt(created_at: datetime) -> PromoAttempt:
    return PromoAttempt(
        id=uuid.uuid4(),
        spa_id=uuid.uuid4(),
        client_attempt_id=uuid.uuid4(),
        trigger_source="test",
        client_release="task099-test",
        detector_id="task099-detector",
        model_version="task099-model",
        jpeg_quality=82,
        camera_device_id="task099-camera",
        reference_series_ready_at=created_at,
        local_detection_completed_ms=10,
        request_started_ms=20,
        proposal_count=1,
        settings_revision=1,
        visit_date=None,
        pipeline_revision_id=uuid.uuid4(),
        pipeline_code="opencv_sface",
        query_source="reference",
        release_id="task099-release",
        threshold=0.72,
        quality_settings={"version": 1},
        deadline_ms=3000,
        created_at=created_at,
        updated_at=created_at,
    )


def _manifest(attempt_id: uuid.UUID) -> dict[str, object]:
    return {
        "schema_version": 1,
        "identity": {"attempt_id": str(attempt_id)},
        "client": {"client_release": "task099-test"},
        "serving": {"pipeline_code": "opencv_sface"},
        "result": None,
        "display": None,
        "artifacts": [],
    }

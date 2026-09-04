"""TASK-098 selected annotation promotion and whole-subset deletion evidence."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
import os
from threading import Event, Thread
import uuid

from alembic import command as alembic_command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.diagnostics import (
    DiagnosticEvidenceProvider,
    DiagnosticEvidenceRepository,
    GroundTruthAnnotationProvider,
)
from face_moment.infrastructure.settings import Settings
from face_moment.promo.attempt import PromoAttempt


_NOW = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def disposable_promotion_engine() -> Iterator[Engine]:
    base_url = Settings.from_env().database_url
    probe_database = f"task098_{uuid.uuid4().hex}"
    probe_url = make_url(base_url).set(database=probe_database)
    admin_engine = create_engine(
        base_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {probe_database}")
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = probe_url.render_as_string(hide_password=False)
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        yield engine
    finally:
        engine.dispose()
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)"
            )
        admin_engine.dispose()


def test_selected_current_annotations_promote_exactly_and_delete_idempotently(
    disposable_promotion_engine: Engine,
) -> None:
    attempt = _attempt()
    with Session(disposable_promotion_engine) as session:
        session.add(attempt)
        session.flush()
        manifest = _manifest(attempt.id)
        DiagnosticEvidenceRepository(session).write_bundle(
            attempt_id=attempt.id,
            ordinary_manifest=manifest,
            completeness="incomplete",
            gap_reason="response_receipt_missing",
        )
        annotation_provider = GroundTruthAnnotationProvider(session)
        selected = annotation_provider.create(
            attempt_id=attempt.id,
            target_kind="detection",
            detection_occurrence_index=1,
            participant_name="Synthetic Selected 098",
            outcome="correct",
        )
        unselected = annotation_provider.create(
            attempt_id=attempt.id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Unselected 098",
            outcome="missed",
        )

        evidence_provider = DiagnosticEvidenceProvider(session)
        promoted = evidence_provider.promote_subset(
            attempt_id=attempt.id,
            promoted_subset={
                "schema_version": 1,
                "parameters": {"threshold": 0.72},
            },
            selected_annotation_ids=(selected.annotation_id,),
            now=_NOW,
        )
        assert promoted.accepted
        stored = DiagnosticEvidenceRepository(session).require(attempt.id)
        assert stored.promoted_subset == {
            "schema_version": 1,
            "parameters": {"threshold": 0.72},
            "annotations": [
                {
                    "annotation_id": str(selected.annotation_id),
                    "attempt_id": str(attempt.id),
                    "target_kind": "detection",
                    "detection_occurrence_index": 1,
                    "participant_name": "Synthetic Selected 098",
                    "outcome": "correct",
                }
            ],
        }
        assert str(unselected.annotation_id) not in str(stored.promoted_subset)
        assert "Synthetic Unselected 098" not in str(stored.promoted_subset)
        assert stored.promoted_at == _NOW
        assert stored.ordinary_manifest == manifest

        deleted = evidence_provider.delete_promoted_subset(
            attempt_id=attempt.id,
            now=_NOW + timedelta(seconds=1),
        )
        assert deleted.accepted
        first_delete = DiagnosticEvidenceRepository(session).require(attempt.id)
        assert first_delete.promoted_subset is None
        assert first_delete.promoted_at is None
        assert first_delete.ordinary_manifest == manifest

        repeated = evidence_provider.delete_promoted_subset(
            attempt_id=attempt.id,
            now=_NOW + timedelta(seconds=2),
        )
        assert repeated.accepted
        after_repeat = DiagnosticEvidenceRepository(session).require(attempt.id)
        assert after_repeat.promoted_subset is None
        assert after_repeat.promoted_at is None
        assert after_repeat.updated_at == first_delete.updated_at
        assert {
            row.annotation_id
            for row in annotation_provider.list(attempt_id=attempt.id)
        } == {selected.annotation_id, unselected.annotation_id}
        session.commit()


@pytest.mark.parametrize("terminal_state", ["removed", "expired"])
def test_promotion_waits_for_terminal_ordinary_state_and_rejects(
    disposable_promotion_engine: Engine,
    terminal_state: str,
) -> None:
    attempt = _attempt()
    attempt_id = attempt.id
    with Session(disposable_promotion_engine) as session:
        session.add(attempt)
        session.flush()
        DiagnosticEvidenceRepository(session).write_bundle(
            attempt_id=attempt_id,
            ordinary_manifest=_manifest(attempt_id),
            completeness="incomplete",
            gap_reason="response_receipt_missing",
        )
        annotation_id = GroundTruthAnnotationProvider(session).create(
            attempt_id=attempt_id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name=f"Synthetic Terminal {terminal_state} 098",
            outcome="missed",
        ).annotation_id
        session.commit()

    reached_evidence_lock = Event()
    promotion_finished = Event()
    outcomes = []
    failures: list[BaseException] = []

    def observe_promotion_lock(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        context: object,
        _executemany: bool,
    ) -> None:
        options = getattr(context, "execution_options", {})
        if (
            options.get("task098_promotion_retry")
            and "diagnostic_evidence" in statement
            and "FOR UPDATE" in statement
        ):
            reached_evidence_lock.set()

    def promote() -> None:
        try:
            with Session(disposable_promotion_engine) as session:
                session.connection(
                    execution_options={"task098_promotion_retry": True}
                )
                outcomes.append(
                    DiagnosticEvidenceProvider(session).promote_subset(
                        attempt_id=attempt_id,
                        promoted_subset={
                            "schema_version": 1,
                            "parameters": {"threshold": 0.72},
                        },
                        selected_annotation_ids=(annotation_id,),
                        now=_NOW + timedelta(seconds=2),
                    )
                )
        except BaseException as error:
            failures.append(error)
        finally:
            promotion_finished.set()

    event.listen(
        disposable_promotion_engine,
        "before_cursor_execute",
        observe_promotion_lock,
    )
    transition_session = Session(disposable_promotion_engine)
    worker = Thread(target=promote)
    try:
        repository = DiagnosticEvidenceRepository(transition_session)
        if terminal_state == "removed":
            repository.remove_ordinary(
                attempt_id=attempt_id,
                now=_NOW + timedelta(seconds=1),
            )
        else:
            assert repository.mark_ordinary_expired(
                attempt_id=attempt_id,
                now=_NOW + timedelta(seconds=1),
            )

        worker.start()
        assert reached_evidence_lock.wait(timeout=5)
        assert not promotion_finished.wait(timeout=0.2)
        transition_session.commit()
        assert promotion_finished.wait(timeout=5)
        worker.join(timeout=1)
    finally:
        transition_session.rollback()
        transition_session.close()
        event.remove(
            disposable_promotion_engine,
            "before_cursor_execute",
            observe_promotion_lock,
        )
        if worker.is_alive():
            worker.join(timeout=5)

    assert not failures
    assert len(outcomes) == 1
    assert not outcomes[0].accepted
    assert outcomes[0].error_code == "invalid_or_conflicting_evidence"
    with Session(disposable_promotion_engine) as session:
        evidence = DiagnosticEvidenceRepository(session).require(attempt_id)
        assert evidence.promoted_subset is None
        assert evidence.promoted_at is None
        if terminal_state == "removed":
            assert evidence.gap_reason == "ordinary_removed"
        else:
            assert evidence.ordinary_expired_at == _NOW + timedelta(seconds=1)
        remaining_annotation_ids = {
            annotation.annotation_id
            for annotation in GroundTruthAnnotationProvider(session).list(
                attempt_id=attempt_id
            )
        }
        if terminal_state == "removed":
            assert remaining_annotation_ids == set()
        else:
            assert remaining_annotation_ids == {annotation_id}


def _manifest(attempt_id: uuid.UUID) -> dict[str, object]:
    return {
        "schema_version": 1,
        "identity": {
            "attempt_id": str(attempt_id),
            "client_attempt_id": str(uuid.uuid4()),
        },
        "detections": [
            {"occurrence_index": 0},
            {"occurrence_index": 1},
        ],
        "artifacts": [],
    }


def _attempt() -> PromoAttempt:
    return PromoAttempt(
        id=uuid.uuid4(),
        spa_id=uuid.uuid4(),
        client_attempt_id=uuid.uuid4(),
        trigger_source="test",
        client_release="task098-client",
        detector_id="task098-detector",
        model_version="task098-model",
        jpeg_quality=85,
        camera_device_id="task098-camera",
        reference_series_ready_at=_NOW - timedelta(milliseconds=200),
        local_detection_completed_ms=100,
        request_started_ms=200,
        response_received_ms=300,
        proposal_count=2,
        settings_revision=1,
        visit_date=date(2026, 9, 4),
        pipeline_revision_id=uuid.uuid4(),
        pipeline_code="opencv_sface",
        query_source="reference",
        release_id="task098-release",
        threshold=0.7,
        quality_settings={"version": 1},
        calibration_id=None,
        deadline_ms=3_000,
        slot_decided_at=_NOW,
        search_started_at=_NOW,
        search_finished_at=_NOW,
        processing_status="result_issued",
        domain_outcome="result",
        display_status="confirmed",
        display_expires_at=_NOW + timedelta(seconds=15),
        display_reported_at=_NOW,
        qr_fully_visible_elapsed_ms=9_000,
        created_at=_NOW,
        updated_at=_NOW,
    )

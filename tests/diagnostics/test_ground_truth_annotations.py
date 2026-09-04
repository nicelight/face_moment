"""TASK-096 normalized ground-truth annotation provider evidence."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
import os
from threading import Event, Thread
import uuid

from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from face_moment.diagnostics.evidence import DiagnosticEvidenceRepository
from face_moment.diagnostics.ground_truth_annotations import (
    GroundTruthAnnotation,
    GroundTruthAnnotationConflictError,
    GroundTruthAnnotationError,
    GroundTruthAnnotationNotFoundError,
    GroundTruthAnnotationProvider,
)
from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings
from face_moment.promo.attempt import PromoAttempt


_REVISION = "0020_annotation_name_whitespace"
_PREDECESSOR = "0019_ground_truth_annotations"
_NOW = datetime(2026, 9, 4, 7, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def disposable_annotation_engine() -> Iterator[Engine]:
    base_url = Settings.from_env().database_url
    probe_database = f"task096_{uuid.uuid4().hex}"
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
        alembic_command.upgrade(Config("alembic.ini"), _PREDECESSOR)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO face_moment.staff_users "
                    "(id, username, password_hash, role) "
                    "VALUES (:id, 'task096-predecessor', 'synthetic-hash', 'developer')"
                ),
                {"id": uuid.uuid4()},
            )
        alembic_command.upgrade(Config("alembic.ini"), _REVISION)
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


def test_next_linear_migration_has_exact_owner_shape_and_safe_downgrade(
    disposable_annotation_engine: Engine,
) -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert scripts.get_revision(_REVISION).down_revision == _PREDECESSOR
    assert scripts.get_heads() == [_REVISION]

    inspector = inspect(disposable_annotation_engine)
    assert {
        column["name"]
        for column in inspector.get_columns(
            "ground_truth_annotations", schema=APP_SCHEMA
        )
    } == {
        "annotation_id",
        "attempt_id",
        "target_kind",
        "detection_occurrence_index",
        "participant_name",
        "outcome",
    }
    assert not inspector.get_foreign_keys(
        "ground_truth_annotations", schema=APP_SCHEMA
    )
    assert {
        constraint["name"]
        for constraint in inspector.get_check_constraints(
            "ground_truth_annotations", schema=APP_SCHEMA
        )
    } == {
        "ck_ground_truth_annotations_outcome",
        "ck_ground_truth_annotations_participant_name",
        "ck_ground_truth_annotations_target_kind",
        "ck_ground_truth_annotations_target_outcome_shape",
    }
    indexes = {
        index["name"]: index
        for index in inspector.get_indexes(
            "ground_truth_annotations", schema=APP_SCHEMA
        )
    }
    assert set(indexes) == {"uq_ground_truth_annotations_detection_target"}
    assert indexes["uq_ground_truth_annotations_detection_target"]["unique"]

    alembic_command.downgrade(Config("alembic.ini"), _PREDECESSOR)
    assert "ground_truth_annotations" in inspect(
        disposable_annotation_engine
    ).get_table_names(schema=APP_SCHEMA)
    with disposable_annotation_engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT count(*) FROM face_moment.staff_users "
                "WHERE username = 'task096-predecessor'"
            )
        ) == 1
    alembic_command.upgrade(Config("alembic.ini"), _REVISION)


def test_provider_create_correct_remove_list_and_restart_snapshot(
    disposable_annotation_engine: Engine,
) -> None:
    attempt = _attempt(proposal_count=3)
    attempt_id = attempt.id
    original_core = (
        attempt.processing_status,
        attempt.domain_outcome,
        attempt.client_attempt_id,
    )
    with Session(disposable_annotation_engine) as session:
        session.add(attempt)
        session.flush()
        original_manifest = _manifest(attempt.id, occurrences=(0, 2))
        DiagnosticEvidenceRepository(session).write_bundle(
            attempt_id=attempt.id,
            ordinary_manifest=original_manifest,
            completeness="incomplete",
            gap_reason="response_receipt_missing",
        )
        provider = GroundTruthAnnotationProvider(session)
        detection = provider.create(
            attempt_id=attempt.id,
            target_kind="detection",
            detection_occurrence_index=2,
            participant_name="  Участник 096  ",
            outcome="correct",
        )
        first_missed = provider.create(
            attempt_id=attempt.id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Miss A",
            outcome="missed",
        )
        second_missed = provider.create(
            attempt_id=attempt.id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Miss B",
            outcome="missed",
        )
        assert detection.participant_name == "Участник 096"

        with pytest.raises(GroundTruthAnnotationConflictError):
            provider.create(
                attempt_id=attempt.id,
                target_kind="detection",
                detection_occurrence_index=2,
                participant_name="Synthetic Duplicate",
                outcome="false",
            )

        corrected = provider.correct(
            attempt_id=attempt.id,
            annotation_id=detection.annotation_id,
            participant_name="Synthetic Corrected",
            outcome="false",
        )
        assert corrected.annotation_id == detection.annotation_id
        assert corrected.target_kind == detection.target_kind
        assert corrected.detection_occurrence_index == 2
        assert corrected.outcome == "false"

        listed = provider.list(attempt_id=attempt.id)
        assert [row.annotation_id for row in listed] == sorted(
            row.annotation_id for row in listed
        )
        assert {row.annotation_id for row in listed} == {
            detection.annotation_id,
            first_missed.annotation_id,
            second_missed.annotation_id,
        }
        snapshot = provider.calculation_snapshot(attempt_id=attempt.id)
        assert snapshot.attempt_id == attempt.id
        assert snapshot.annotations == listed
        with pytest.raises(FrozenInstanceError):
            snapshot.attempt_id = uuid.uuid4()  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            listed[0].participant_name = "mutation"  # type: ignore[misc]

        provider.remove(
            attempt_id=attempt.id,
            annotation_id=first_missed.annotation_id,
        )
        assert {row.annotation_id for row in provider.list(attempt_id=attempt.id)} == {
            detection.annotation_id,
            second_missed.annotation_id,
        }
        evidence = DiagnosticEvidenceRepository(session).require(attempt.id)
        assert evidence.ordinary_manifest == original_manifest
        assert "participant_name" not in str(evidence.ordinary_manifest)
        assert (
            attempt.processing_status,
            attempt.domain_outcome,
            attempt.client_attempt_id,
        ) == original_core
        session.commit()

    with Session(disposable_annotation_engine) as restarted:
        snapshot = GroundTruthAnnotationProvider(restarted).calculation_snapshot(
            attempt_id=attempt_id
        )
        assert {row.annotation_id for row in snapshot.annotations} == {
            detection.annotation_id,
            second_missed.annotation_id,
        }
        core = restarted.get(PromoAttempt, attempt_id)
        assert core is not None
        assert (
            core.processing_status,
            core.domain_outcome,
            core.client_attempt_id,
        ) == original_core


@pytest.mark.parametrize("participant_name", ("\t", "\N{NO-BREAK SPACE}"))
def test_database_rejects_unicode_whitespace_only_participant_name(
    disposable_annotation_engine: Engine,
    participant_name: str,
) -> None:
    with disposable_annotation_engine.connect() as connection:
        with pytest.raises(IntegrityError):
            with connection.begin():
                connection.execute(
                    text(
                        "INSERT INTO face_moment.ground_truth_annotations "
                        "(annotation_id, attempt_id, target_kind, "
                        "detection_occurrence_index, participant_name, outcome) "
                        "VALUES (:annotation_id, :attempt_id, 'person', NULL, "
                        ":participant_name, 'missed')"
                    ),
                    {
                        "annotation_id": uuid.uuid4(),
                        "attempt_id": uuid.uuid4(),
                        "participant_name": participant_name,
                    },
                )


def test_absence_is_empty_while_person_missed_needs_no_evidence(
    disposable_annotation_engine: Engine,
) -> None:
    attempt = _attempt(proposal_count=0)
    with Session(disposable_annotation_engine) as session:
        session.add(attempt)
        session.commit()
        provider = GroundTruthAnnotationProvider(session)
        assert provider.calculation_snapshot(attempt_id=attempt.id).annotations == ()

        missed = provider.create(
            attempt_id=attempt.id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Person Without Detection",
            outcome="missed",
        )
        assert provider.calculation_snapshot(attempt_id=attempt.id).annotations == (
            missed,
        )
        session.commit()


@pytest.mark.parametrize(
    ("target_kind", "occurrence", "name", "outcome"),
    (
        ("detection", None, "Synthetic", "correct"),
        ("detection", -1, "Synthetic", "correct"),
        ("detection", 0, "Synthetic", "missed"),
        ("person", 0, "Synthetic", "missed"),
        ("person", None, "Synthetic", "correct"),
        ("person", None, "   ", "missed"),
        ("person", None, "x" * 201, "missed"),
    ),
)
def test_provider_rejects_invalid_pairs_and_values(
    disposable_annotation_engine: Engine,
    target_kind: str,
    occurrence: int | None,
    name: str,
    outcome: str,
) -> None:
    attempt = _attempt(proposal_count=1)
    with Session(disposable_annotation_engine) as session:
        session.add(attempt)
        session.flush()
        DiagnosticEvidenceRepository(session).write_bundle(
            attempt_id=attempt.id,
            ordinary_manifest=_manifest(attempt.id, occurrences=(0,)),
            completeness="incomplete",
            gap_reason="response_receipt_missing",
        )
        with pytest.raises(GroundTruthAnnotationError):
            GroundTruthAnnotationProvider(session).create(
                attempt_id=attempt.id,
                target_kind=target_kind,
                detection_occurrence_index=occurrence,
                participant_name=name,
                outcome=outcome,
            )
        assert not session.scalars(
            select(GroundTruthAnnotation).where(
                GroundTruthAnnotation.attempt_id == attempt.id
            )
        ).all()
        session.rollback()


def test_provider_rejects_missing_detection_attempt_and_wrong_annotation_owner(
    disposable_annotation_engine: Engine,
) -> None:
    first = _attempt(proposal_count=2)
    second = _attempt(proposal_count=1)
    with Session(disposable_annotation_engine) as session:
        session.add_all((first, second))
        session.flush()
        DiagnosticEvidenceRepository(session).write_bundle(
            attempt_id=first.id,
            ordinary_manifest=_manifest(first.id, occurrences=(0,)),
            completeness="incomplete",
            gap_reason="response_receipt_missing",
        )
        provider = GroundTruthAnnotationProvider(session)
        with pytest.raises(GroundTruthAnnotationError, match="does not exist"):
            provider.create(
                attempt_id=first.id,
                target_kind="detection",
                detection_occurrence_index=1,
                participant_name="Synthetic Missing Detection",
                outcome="false",
            )
        with pytest.raises(GroundTruthAnnotationNotFoundError):
            provider.create(
                attempt_id=uuid.uuid4(),
                target_kind="person",
                detection_occurrence_index=None,
                participant_name="Synthetic Missing Attempt",
                outcome="missed",
            )
        annotation = provider.create(
            attempt_id=first.id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name="Synthetic Owner A",
            outcome="missed",
        )
        with pytest.raises(GroundTruthAnnotationNotFoundError):
            provider.correct(
                attempt_id=second.id,
                annotation_id=annotation.annotation_id,
                participant_name="Synthetic Owner B",
                outcome="missed",
            )
        session.rollback()


@pytest.mark.parametrize("state", ("expired", "removed"))
def test_expired_or_removed_ordinary_state_rejects_every_new_write(
    disposable_annotation_engine: Engine,
    state: str,
) -> None:
    attempt = _attempt(proposal_count=1)
    with Session(disposable_annotation_engine) as session:
        session.add(attempt)
        session.flush()
        evidence = DiagnosticEvidenceRepository(session)
        evidence.write_bundle(
            attempt_id=attempt.id,
            ordinary_manifest=_manifest(attempt.id, occurrences=(0,)),
            completeness="incomplete",
            gap_reason="response_receipt_missing",
        )
        provider = GroundTruthAnnotationProvider(session)
        annotation = provider.create(
            attempt_id=attempt.id,
            target_kind="person",
            detection_occurrence_index=None,
            participant_name=f"Synthetic {state}",
            outcome="missed",
        )
        if state == "expired":
            evidence.expire_ordinary(attempt_id=attempt.id, now=_NOW)
        else:
            evidence.remove_ordinary(attempt_id=attempt.id, now=_NOW)

        with pytest.raises(GroundTruthAnnotationError, match=state):
            provider.create(
                attempt_id=attempt.id,
                target_kind="person",
                detection_occurrence_index=None,
                participant_name="Synthetic Rejected Create",
                outcome="missed",
            )
        with pytest.raises(GroundTruthAnnotationError, match=state):
            provider.correct(
                attempt_id=attempt.id,
                annotation_id=annotation.annotation_id,
                participant_name="Synthetic Rejected Correct",
                outcome="missed",
            )
        with pytest.raises(GroundTruthAnnotationError, match=state):
            provider.remove(
                attempt_id=attempt.id,
                annotation_id=annotation.annotation_id,
            )
        stored_annotation = session.get(
            GroundTruthAnnotation, annotation.annotation_id
        )
        if state == "removed":
            assert stored_annotation is None
        else:
            assert stored_annotation is not None
        session.rollback()


def test_create_waiting_on_removal_rejects_without_persisting_annotation(
    disposable_annotation_engine: Engine,
) -> None:
    attempt = _attempt(proposal_count=0)
    attempt_id = attempt.id
    with Session(disposable_annotation_engine) as setup_session:
        setup_session.add(attempt)
        setup_session.flush()
        DiagnosticEvidenceRepository(setup_session).write_bundle(
            attempt_id=attempt_id,
            ordinary_manifest=_manifest(attempt_id, occurrences=()),
            completeness="incomplete",
            gap_reason="response_receipt_missing",
        )
        setup_session.commit()

    writer_reached_lock = Event()
    writer_finished = Event()
    writer_errors: list[BaseException] = []
    writer_rejections: list[str] = []

    def observe_writer_lock(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        context: object,
        _executemany: bool,
    ) -> None:
        execution_options = getattr(context, "execution_options", {})
        if (
            execution_options.get("task096_annotation_writer")
            and "diagnostic_evidence" in statement
            and "FOR UPDATE" in statement
        ):
            writer_reached_lock.set()

    event.listen(
        disposable_annotation_engine,
        "before_cursor_execute",
        observe_writer_lock,
    )

    def create_annotation() -> None:
        try:
            with Session(disposable_annotation_engine) as writer_session:
                writer_session.connection(
                    execution_options={"task096_annotation_writer": True}
                )
                try:
                    GroundTruthAnnotationProvider(writer_session).create(
                        attempt_id=attempt_id,
                        target_kind="person",
                        detection_occurrence_index=None,
                        participant_name="Synthetic Concurrent Rejected",
                        outcome="missed",
                    )
                except GroundTruthAnnotationError as error:
                    writer_rejections.append(str(error))
                    writer_session.rollback()
                else:
                    writer_session.commit()
        except BaseException as error:  # pragma: no cover - surfaced below
            writer_errors.append(error)
        finally:
            writer_finished.set()

    remover_session = Session(disposable_annotation_engine)
    writer_thread = Thread(target=create_annotation)
    try:
        DiagnosticEvidenceRepository(remover_session).remove_ordinary(
            attempt_id=attempt_id,
            now=_NOW,
        )
        writer_thread.start()
        assert writer_reached_lock.wait(timeout=5)
        assert not writer_finished.wait(timeout=0.2)
        remover_session.commit()
        assert writer_finished.wait(timeout=5)
        writer_thread.join(timeout=1)
    finally:
        remover_session.rollback()
        remover_session.close()
        event.remove(
            disposable_annotation_engine,
            "before_cursor_execute",
            observe_writer_lock,
        )
        if writer_thread.is_alive():
            writer_thread.join(timeout=5)

    assert not writer_errors
    assert writer_rejections == ["ordinary evidence has been removed"]
    with Session(disposable_annotation_engine) as inspection_session:
        evidence = DiagnosticEvidenceRepository(inspection_session).require(attempt_id)
        assert evidence.gap_reason == "ordinary_removed"
        assert not inspection_session.scalars(
            select(GroundTruthAnnotation).where(
                GroundTruthAnnotation.attempt_id == attempt_id
            )
        ).all()


def test_database_checks_reject_invalid_direct_writes(
    disposable_annotation_engine: Engine,
) -> None:
    with pytest.raises(IntegrityError):
        with disposable_annotation_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO face_moment.ground_truth_annotations "
                    "(annotation_id, attempt_id, target_kind, "
                    "detection_occurrence_index, participant_name, outcome) "
                    "VALUES (:annotation_id, :attempt_id, 'person', 0, "
                    "'Synthetic', 'missed')"
                ),
                {"annotation_id": uuid.uuid4(), "attempt_id": uuid.uuid4()},
            )


def _manifest(
    attempt_id: uuid.UUID, *, occurrences: tuple[int, ...]
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "identity": {
            "attempt_id": str(attempt_id),
            "client_attempt_id": str(uuid.uuid4()),
        },
        "detections": [
            {"occurrence_index": occurrence} for occurrence in occurrences
        ],
        "artifacts": [],
    }


def _attempt(*, proposal_count: int) -> PromoAttempt:
    return PromoAttempt(
        id=uuid.uuid4(),
        spa_id=uuid.uuid4(),
        client_attempt_id=uuid.uuid4(),
        trigger_source="test",
        client_release="task096-client",
        detector_id="task096-detector",
        model_version="task096-model",
        jpeg_quality=85,
        camera_device_id="task096-camera",
        reference_series_ready_at=_NOW - timedelta(milliseconds=200),
        local_detection_completed_ms=100,
        request_started_ms=200,
        response_received_ms=300,
        proposal_count=proposal_count,
        settings_revision=1,
        visit_date=date(2026, 9, 4),
        pipeline_revision_id=uuid.uuid4(),
        pipeline_code="opencv_sface",
        query_source="reference",
        release_id="task096-release",
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

"""Disposable proof for the durable Calibration run core (FT-011-AC-003)."""

from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
import uuid

from alembic import command as alembic_command
from alembic.config import Config
import cv2
import numpy as np
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.diagnostics.calibration_runs import (
    CalibrationRunError,
    CalibrationRun,
    CalibrationRunRepository,
    CalibrationRunService,
    CalibrationRunStatus,
    CalibrationSelectionConflictError,
    DatasetMismatchError,
    _compose_balance_recommendation,
)
from face_moment.diagnostics.ground_truth_annotations import GroundTruthAnnotationProvider
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.promo.attempt import PromoAttempt
from face_moment.serving_control.ingest_target import IngestTargetRepository
from tests.disposable_postgresql import disposable_postgresql_engine


class _Store:
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values
        self.reads: list[str] = []

    def read(self, *, key: str) -> bytes:
        self.reads.append(key)
        return self.values[key]


class _Adapter:
    def __init__(self, revision_id: uuid.UUID, result_count: int) -> None:
        self.pipeline_revision_id = revision_id
        self._result_count = result_count
        self.inputs: list[np.ndarray] = []

    def process_photo(self, photo: np.ndarray) -> tuple[object, ...]:
        self.inputs.append(photo)
        return tuple(object() for _ in range(self._result_count))


def test_kiss_recommendation_rejects_mixed_attempt_provenance() -> None:
    sface_id = uuid.uuid4()
    buffalo_id = uuid.uuid4()

    def snapshot(
        *, second_revision_id: uuid.UUID = sface_id, second_threshold: float = 0.7
    ) -> dict[str, object]:
        first_attempt_id = uuid.uuid4()
        second_attempt_id = uuid.uuid4()
        return {
            "serving_values": {
                "pipeline_revision_id": str(sface_id),
                "pipeline_code": "opencv_sface",
                "min_query_face_quality": 0.51,
                "quality_settings": {"version": 1},
            },
            "pipeline_revisions": {
                "sface": str(sface_id),
                "buffalo_m": str(buffalo_id),
            },
            "selected_attempt_ids": [str(first_attempt_id), str(second_attempt_id)],
            "attempts": [
                {
                    "attempt_id": str(first_attempt_id),
                    "pipeline_revision_id": str(sface_id),
                    "pipeline_code": "opencv_sface",
                    "reference_threshold": 0.7,
                    "annotations": [{"outcome": "correct"}],
                },
                {
                    "attempt_id": str(second_attempt_id),
                    "pipeline_revision_id": str(second_revision_id),
                    "pipeline_code": "opencv_sface",
                    "reference_threshold": second_threshold,
                    "annotations": [{"outcome": "false"}],
                },
            ],
        }

    assert _compose_balance_recommendation(snapshot()) is not None
    assert (
        _compose_balance_recommendation(
            snapshot(second_revision_id=buffalo_id)
        )
        is None
    )
    assert _compose_balance_recommendation(snapshot(second_threshold=0.8)) is None


def test_legacy_snapshot_without_selection_has_no_fresh_recommendation() -> None:
    sface_id = uuid.uuid4()
    snapshot = {
        "serving_values": {
            "pipeline_revision_id": str(sface_id),
            "pipeline_code": PipelineCode.OPENCV_SFACE.value,
            "reference_threshold": 0.7,
            "min_query_face_quality": 0.51,
            "quality_settings": {},
        },
        "pipeline_revisions": {
            "sface": str(sface_id),
            "buffalo_m": str(uuid.uuid4()),
        },
        "attempts": [
            {
                "attempt_id": str(uuid.uuid4()),
                "pipeline_revision_id": str(sface_id),
                "pipeline_code": PipelineCode.OPENCV_SFACE.value,
                "reference_threshold": 0.7,
                "annotations": [{"outcome": "correct"}],
            }
        ],
    }

    # The old persisted shape has no authoritative total selected sample.
    assert _compose_balance_recommendation(snapshot) is None


def _jpeg() -> bytes:
    encoded, payload = cv2.imencode(".jpg", np.zeros((12, 20, 3), dtype=np.uint8))
    assert encoded
    return bytes(payload)


def _revision(session: Session, code: PipelineCode, label: str):
    return PipelineRevisionRepository(session).publish_eligible(
        pipeline_code=code,
        validated_at=datetime.now(UTC),
        detector_id=f"task100-{label}-detector",
        detector_version="v1",
        recognizer_id=f"task100-{label}-recognizer",
        recognizer_version="v1",
        weights_sha256=hashlib.sha256(label.encode()).hexdigest(),
        preprocessing_version="task100-preprocess-v1",
        alignment_version="task100-align-v1",
        normalization_version="task100-normalize-v1",
        embedding_dimension=3,
    )


def _photo(session: Session, *, spa_id: uuid.UUID, revision_id: uuid.UUID, key: str, payload: bytes) -> Photo:
    photo = Photo(
        spa_id=spa_id,
        visit_date=date(2026, 9, 4),
        captured_at=datetime(2026, 9, 4, tzinfo=UTC),
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        uploader_id=uuid.uuid4(),
        checksum_sha256=hashlib.sha256(payload).digest(),
        original_object_key=key,
        original_byte_size=len(payload),
        width=20,
        height=12,
        admission_pipeline_revision_id=revision_id,
    )
    session.add(photo)
    session.flush()
    return photo


def _attempt(*, spa_id: uuid.UUID, revision_id: uuid.UUID) -> PromoAttempt:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    return PromoAttempt(
        id=uuid.uuid4(), spa_id=spa_id, client_attempt_id=uuid.uuid4(), trigger_source="test",
        client_release="task100-client", detector_id="task100-detector", model_version="task100-model",
        jpeg_quality=85, camera_device_id="task100-camera",
        reference_series_ready_at=now - timedelta(milliseconds=200),
        local_detection_completed_ms=100, request_started_ms=200, response_received_ms=300,
        proposal_count=0, settings_revision=1, visit_date=date(2026, 9, 4),
        pipeline_revision_id=revision_id, pipeline_code="opencv_sface", query_source="reference",
        release_id="task100-release", threshold=0.7, quality_settings={"version": 1},
        calibration_id=None, deadline_ms=3_000, slot_decided_at=now, search_started_at=now,
        search_finished_at=now, processing_status="result_issued", domain_outcome="result",
        display_status="confirmed", display_expires_at=now + timedelta(seconds=15),
        display_reported_at=now, qr_fully_visible_elapsed_ms=9_000, created_at=now, updated_at=now,
    )


def _request(
    service: CalibrationRunService,
    photo: Photo,
    sface_id: uuid.UUID,
    buffalo_id: uuid.UUID,
    attempt_id: uuid.UUID,
) -> CalibrationRun:
    return service.request(
        requested_by_staff_id=uuid.uuid4(),
        photo_ids=(photo.id,),
        selected_attempt_ids=(attempt_id,),
        sface_revision_id=sface_id,
        buffalo_revision_id=buffalo_id,
        serving_values={"threshold": 0.5},
        candidate_values={"thresholds": [0.4, 0.5]},
    )


def test_calibration_run_retains_attempt_without_persisted_annotations_as_exclusion() -> None:
    payload = _jpeg()
    with disposable_postgresql_engine("task100_missing_ground_truth") as engine:
        with Session(engine) as session:
            sface = _revision(session, PipelineCode.OPENCV_SFACE, "sface")
            buffalo = _revision(session, PipelineCode.INSIGHTFACE_BUFFALO_M, "buffalo")
            spa = IngestTargetRepository(session).configure_spa(
                name="Task 100", timezone="Asia/Dushanbe", serving_pipeline_revision_id=sface.id
            )
            photo = _photo(
                session,
                spa_id=spa.spa_id,
                revision_id=sface.id,
                key="task100/missing-ground-truth.jpg",
                payload=payload,
            )
            missing_ground_truth = _attempt(spa_id=spa.spa_id, revision_id=sface.id)
            session.add(missing_ground_truth)
            session.flush()

            run = CalibrationRunService(session).request(
                requested_by_staff_id=uuid.uuid4(),
                photo_ids=(photo.id,),
                selected_attempt_ids=(missing_ground_truth.id,),
                sface_revision_id=sface.id,
                buffalo_revision_id=buffalo.id,
                serving_values={"threshold": 0.5},
                candidate_values={"thresholds": [0.4, 0.5]},
            )
            assert run.dataset_snapshot["selected_attempt_ids"] == [
                str(missing_ground_truth.id)
            ]
            assert run.dataset_snapshot["attempts"] == []
            assert run.dataset_snapshot["selection_exclusions"] == [
                {
                    "attempt_id": str(missing_ground_truth.id),
                    "reason": "missing_ground_truth",
                }
            ]
            assert session.query(CalibrationRun).count() == 1


def test_mixed_calibration_selection_freezes_full_ids_and_applicable_annotations() -> None:
    payload = _jpeg()
    with disposable_postgresql_engine("task12_mixed_selection") as engine:
        with Session(engine) as session:
            sface = _revision(session, PipelineCode.OPENCV_SFACE, "sface")
            buffalo = _revision(session, PipelineCode.INSIGHTFACE_BUFFALO_M, "buffalo")
            spa = IngestTargetRepository(session).configure_spa(
                name="Task 12 mixed", timezone="Asia/Dushanbe", serving_pipeline_revision_id=sface.id
            )
            photo = _photo(
                session, spa_id=spa.spa_id, revision_id=sface.id,
                key="task12/mixed.jpg", payload=payload,
            )
            annotated = _attempt(spa_id=spa.spa_id, revision_id=sface.id)
            unannotated = _attempt(spa_id=spa.spa_id, revision_id=sface.id)
            session.add_all((annotated, unannotated))
            session.flush()
            annotation = GroundTruthAnnotationProvider(session).create(
                attempt_id=annotated.id,
                target_kind="person",
                detection_occurrence_index=None,
                participant_name="Task 12 participant",
                outcome="missed",
            )
            service = CalibrationRunService(session)
            run = service.request(
                requested_by_staff_id=uuid.uuid4(),
                photo_ids=(photo.id,),
                selected_attempt_ids=(annotated.id, unannotated.id),
                sface_revision_id=sface.id,
                buffalo_revision_id=buffalo.id,
                serving_values={
                    "pipeline_revision_id": str(sface.id),
                    "pipeline_code": PipelineCode.OPENCV_SFACE.value,
                    "reference_threshold": 0.7,
                    "min_query_face_quality": 0.51,
                    "quality_settings": {},
                },
                candidate_values={"reference_thresholds": [0.7]},
            )
            frozen_snapshot = deepcopy(run.dataset_snapshot)
            # Live annotation changes after request cannot alter this run.
            late_annotation = GroundTruthAnnotationProvider(session).create(
                attempt_id=unannotated.id,
                target_kind="person",
                detection_occurrence_index=None,
                participant_name="Late participant",
                outcome="missed",
            )
            assert late_annotation.attempt_id == unannotated.id
            assert run.dataset_snapshot == frozen_snapshot

            completed = service.execute(
                run_id=run.id,
                sface_adapter=_Adapter(sface.id, 1),
                buffalo_adapter=_Adapter(buffalo.id, 1),
                object_store=_Store({photo.original_object_key: payload}),
            )
            assert completed.result_bundle is not None
            profile = completed.result_bundle["threshold_profiles"][0]
            assert profile["selected_attempt_count"] == 2
            assert profile["applicable_attempt_count"] == 1
            assert profile["profiles"]["balance"]["proposal"][
                "annotated_sample_size"
            ] == 1
            assert completed.dataset_snapshot["selected_attempt_ids"] == [
                str(annotated.id), str(unannotated.id)
            ]
            assert completed.dataset_snapshot["selection_exclusions"] == [
                {"attempt_id": str(unannotated.id), "reason": "missing_ground_truth"}
            ]
            assert completed.dataset_snapshot["attempts"][0]["annotations"][0][
                "annotation_id"
            ] == str(annotation.annotation_id)
            run_id = run.id
            frozen_sha256 = run.dataset_sha256
            annotated_id = annotated.id
            unannotated_id = unannotated.id
            session.commit()

        with Session(engine) as fresh_session:
            persisted = CalibrationRunRepository(fresh_session).require(run_id)
            assert persisted.dataset_sha256 == frozen_sha256
            assert persisted.dataset_snapshot["selected_attempt_ids"] == [
                str(annotated_id), str(unannotated_id)
            ]
            assert persisted.dataset_snapshot["selection_exclusions"] == [
                {"attempt_id": str(unannotated_id), "reason": "missing_ground_truth"}
            ]
            persisted_profile = persisted.result_bundle["threshold_profiles"][0]
            assert persisted_profile["selected_attempt_count"] == 2
            assert persisted_profile["applicable_attempt_count"] == 1


def test_all_unannotated_calibration_selection_is_visible_without_recommendation() -> None:
    payload = _jpeg()
    with disposable_postgresql_engine("task12_all_unannotated") as engine:
        with Session(engine) as session:
            sface = _revision(session, PipelineCode.OPENCV_SFACE, "sface")
            buffalo = _revision(session, PipelineCode.INSIGHTFACE_BUFFALO_M, "buffalo")
            spa = IngestTargetRepository(session).configure_spa(
                name="Task 12 all unannotated", timezone="Asia/Dushanbe", serving_pipeline_revision_id=sface.id
            )
            photo = _photo(
                session, spa_id=spa.spa_id, revision_id=sface.id,
                key="task12/all-unannotated.jpg", payload=payload,
            )
            attempts = tuple(
                _attempt(spa_id=spa.spa_id, revision_id=sface.id) for _ in range(2)
            )
            session.add_all(attempts)
            session.flush()
            run = CalibrationRunService(session).request(
                requested_by_staff_id=uuid.uuid4(),
                photo_ids=(photo.id,),
                selected_attempt_ids=tuple(attempt.id for attempt in attempts),
                sface_revision_id=sface.id,
                buffalo_revision_id=buffalo.id,
                serving_values={
                    "pipeline_revision_id": str(sface.id),
                    "pipeline_code": PipelineCode.OPENCV_SFACE.value,
                    "reference_threshold": 0.7,
                    "min_query_face_quality": 0.51,
                    "quality_settings": {},
                },
                candidate_values={"reference_thresholds": [0.7]},
            )
            completed = CalibrationRunService(session).execute(
                run_id=run.id,
                sface_adapter=_Adapter(sface.id, 0),
                buffalo_adapter=_Adapter(buffalo.id, 0),
                object_store=_Store({photo.original_object_key: payload}),
            )
            assert completed.result_bundle is not None
            profile = completed.result_bundle["threshold_profiles"][0]
            assert profile["selected_attempt_count"] == 2
            assert profile["applicable_attempt_count"] == 0
            assert all(
                item["proposal"] is None
                for item in profile["profiles"].values()
            )
            assert "serving_recommendations" not in completed.result_bundle
            assert completed.dataset_snapshot["attempts"] == []
            assert len(completed.dataset_snapshot["selection_exclusions"]) == 2
            run_id = run.id
            frozen_sha256 = run.dataset_sha256
            attempt_ids = tuple(attempt.id for attempt in attempts)
            session.commit()

        with Session(engine) as fresh_session:
            persisted = CalibrationRunRepository(fresh_session).require(run_id)
            assert persisted.dataset_sha256 == frozen_sha256
            assert persisted.dataset_snapshot["selected_attempt_ids"] == [
                str(attempt_id) for attempt_id in attempt_ids
            ]
            assert len(persisted.dataset_snapshot["selection_exclusions"]) == 2
            persisted_profile = persisted.result_bundle["threshold_profiles"][0]
            assert persisted_profile["selected_attempt_count"] == 2
            assert persisted_profile["applicable_attempt_count"] == 0


def test_selection_rejects_duplicate_and_cross_spa_attempt_ids() -> None:
    payload = _jpeg()
    with disposable_postgresql_engine("task12_selection_validation") as engine:
        with Session(engine) as session:
            sface = _revision(session, PipelineCode.OPENCV_SFACE, "sface")
            buffalo = _revision(session, PipelineCode.INSIGHTFACE_BUFFALO_M, "buffalo")
            spa = IngestTargetRepository(session).configure_spa(
                name="Task 12 validation", timezone="Asia/Dushanbe", serving_pipeline_revision_id=sface.id
            )
            photo = _photo(
                session, spa_id=spa.spa_id, revision_id=sface.id,
                key="task12/validation.jpg", payload=payload,
            )
            attempt = _attempt(spa_id=spa.spa_id, revision_id=sface.id)
            foreign_attempt = _attempt(spa_id=uuid.uuid4(), revision_id=sface.id)
            session.add_all((attempt, foreign_attempt))
            session.flush()
            service = CalibrationRunService(session)
            kwargs = {
                "requested_by_staff_id": uuid.uuid4(),
                "photo_ids": (photo.id,),
                "sface_revision_id": sface.id,
                "buffalo_revision_id": buffalo.id,
            }
            with pytest.raises(CalibrationSelectionConflictError, match="must be unique"):
                service.request_from_selection(
                    **kwargs, selected_attempt_ids=(attempt.id, attempt.id)
                )
            with pytest.raises(
                CalibrationSelectionConflictError,
                match="selected Attempts must belong to the selected SPA",
            ):
                service.request_from_selection(
                    **kwargs, selected_attempt_ids=(foreign_attempt.id,)
                )


def test_calibration_run_is_immutable_and_uses_same_verified_photo_once_for_both_adapters() -> None:
    payload = _jpeg()
    with disposable_postgresql_engine("task100_calibration") as engine:
        with Session(engine) as session:
            sface = _revision(session, PipelineCode.OPENCV_SFACE, "sface")
            buffalo = _revision(session, PipelineCode.INSIGHTFACE_BUFFALO_M, "buffalo")
            spa = IngestTargetRepository(session).configure_spa(name="Task 100", timezone="Asia/Dushanbe", serving_pipeline_revision_id=sface.id)
            photo = _photo(session, spa_id=spa.spa_id, revision_id=sface.id, key="task100/original.jpg", payload=payload)
            attempt = _attempt(spa_id=spa.spa_id, revision_id=sface.id)
            session.add(attempt)
            session.flush()
            annotation = GroundTruthAnnotationProvider(session).create(
                attempt_id=attempt.id,
                target_kind="person",
                detection_occurrence_index=None,
                participant_name="Synthetic Calibration Participant",
                outcome="missed",
            )
            service = CalibrationRunService(session)
            run = _request(service, photo, sface.id, buffalo.id, attempt.id)
            original_snapshot = run.dataset_snapshot
            store = _Store({photo.original_object_key: payload})
            sface_adapter = _Adapter(sface.id, 1)
            buffalo_adapter = _Adapter(buffalo.id, 2)
            completed = service.execute(run_id=run.id, sface_adapter=sface_adapter, buffalo_adapter=buffalo_adapter, object_store=store)
            session.commit()

            assert completed.status == CalibrationRunStatus.COMPLETE
            assert completed.dataset_snapshot == original_snapshot
            assert store.reads == [photo.original_object_key]
            assert sface_adapter.inputs[0] is buffalo_adapter.inputs[0]
            assert completed.result_bundle is not None
            assert [row["photos"][0]["face_count"] for row in completed.result_bundle["pipeline_results"]] == [1, 2]
            assert completed.dataset_snapshot["attempts"] == [
                {
                    "attempt_id": str(attempt.id),
                    "pipeline_revision_id": str(sface.id),
                    "pipeline_code": "opencv_sface",
                    "reference_threshold": 0.7,
                    "annotations": [
                        {
                            "annotation_id": str(annotation.annotation_id),
                            "attempt_id": str(attempt.id),
                            "target_kind": "person",
                            "detection_occurrence_index": None,
                            "participant_name": "Synthetic Calibration Participant",
                            "outcome": "missed",
                        }
                    ],
                }
            ]
            assert "embedding" not in str(completed.result_bundle)
            assert "task100/original.jpg" not in str(completed.dataset_snapshot)


def test_unavailable_dataset_fails_without_changing_the_frozen_selection() -> None:
    payload = _jpeg()
    with disposable_postgresql_engine("task100_unavailable") as engine:
        with Session(engine) as session:
            sface = _revision(session, PipelineCode.OPENCV_SFACE, "sface")
            buffalo = _revision(session, PipelineCode.INSIGHTFACE_BUFFALO_M, "buffalo")
            spa = IngestTargetRepository(session).configure_spa(name="Task 100", timezone="Asia/Dushanbe", serving_pipeline_revision_id=sface.id)
            photo = _photo(session, spa_id=spa.spa_id, revision_id=sface.id, key="task100/unavailable.jpg", payload=payload)
            attempt = _attempt(spa_id=spa.spa_id, revision_id=sface.id)
            session.add(attempt)
            session.flush()
            GroundTruthAnnotationProvider(session).create(
                attempt_id=attempt.id,
                target_kind="person",
                detection_occurrence_index=None,
                participant_name="Synthetic Unavailable Participant",
                outcome="missed",
            )
            service = CalibrationRunService(session)
            run = _request(service, photo, sface.id, buffalo.id, attempt.id)
            snapshot = run.dataset_snapshot
            failed = service.execute(run_id=run.id, sface_adapter=_Adapter(sface.id, 1), buffalo_adapter=_Adapter(buffalo.id, 1), object_store=_Store({photo.original_object_key: b"changed"}))
            assert failed.status == CalibrationRunStatus.FAILED
            assert failed.error_code == "dataset_unavailable"
            assert failed.dataset_snapshot == snapshot
            assert failed.result_bundle is None


def test_only_complete_equal_dataset_runs_are_comparable_and_migration_downgrades() -> None:
    with disposable_postgresql_engine("task100_compare") as engine:
        inspector = inspect(engine)
        assert "calibration_runs" in inspector.get_table_names(schema="face_moment")
        assert {column["name"] for column in inspector.get_columns("calibration_runs", schema="face_moment")} == {
            "id", "requested_by_staff_id", "status", "dataset_snapshot", "dataset_sha256",
            "result_bundle", "error_code", "created_at", "started_at", "finished_at",
        }
        with Session(engine) as session:
            repository = CalibrationRunRepository(session)
            snapshot = {"photos": [{"photo_id": str(uuid.uuid4()), "sha256": "0" * 64}], "attempts": [{"attempt_id": str(uuid.uuid4()), "annotations": []}]}
            before = repository.create_requested(requested_by_staff_id=uuid.uuid4(), dataset_snapshot=snapshot)
            repository.start(before.id)
            repository.complete(before.id, result_bundle={"pipeline_results": []})
            after = repository.create_requested(requested_by_staff_id=uuid.uuid4(), dataset_snapshot=snapshot)
            repository.start(after.id)
            repository.complete(after.id, result_bundle={"pipeline_results": []})
            assert repository.compare_complete(before_run_id=before.id, after_run_id=after.id).dataset_sha256 == before.dataset_sha256
            mismatch = repository.create_requested(requested_by_staff_id=uuid.uuid4(), dataset_snapshot={**snapshot, "photos": []})
            repository.start(mismatch.id)
            repository.complete(mismatch.id, result_bundle={"pipeline_results": []})
            with pytest.raises(DatasetMismatchError, match="dataset_mismatch"):
                repository.compare_complete(before_run_id=before.id, after_run_id=mismatch.id)
            session.execute(
                text(
                    "INSERT INTO face_moment.staff_users (id, username, password_hash, role) "
                    "VALUES (:id, 'task100-predecessor', 'synthetic-hash', 'developer')"
                ),
                {"id": uuid.uuid4()},
            )
            session.commit()
        alembic_command.downgrade(Config("alembic.ini"), "0020_annotation_name_whitespace")
        assert "calibration_runs" not in inspect(engine).get_table_names(schema="face_moment")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM face_moment.staff_users WHERE username = 'task100-predecessor'")) == 1


@pytest.fixture(scope="module")
def comparison_engine() -> Iterator[Engine]:
    with disposable_postgresql_engine("calibration11_compare") as engine:
        yield engine


def _comparison_data() -> dict[str, object]:
    return {
        "spa_id": str(uuid.uuid4()),
        "photos": [
            {"photo_id": str(uuid.uuid4()), "sha256": "0" * 64},
            {"photo_id": str(uuid.uuid4()), "sha256": "1" * 64},
        ],
        "attempts": [{
            "attempt_id": str(uuid.uuid4()),
            "pipeline_revision_id": str(uuid.uuid4()),
            "pipeline_code": "opencv_sface",
            "reference_threshold": 0.7,
            "annotations": [{"annotation_id": str(uuid.uuid4()), "outcome": "correct"}],
            # These names are removable only at the snapshot's top level.
            "pipeline_revisions": {"historical": "v1"},
            "serving_values": {"historical": 0.7},
            "candidate_values": [0.6, 0.7],
        }],
        "extra_dataset_field": {"version": 1},
    }


def _full_input(data: dict[str, object]) -> dict[str, object]:
    return {
        **deepcopy(data),
        "pipeline_revisions": {"sface": str(uuid.uuid4()), "buffalo_m": str(uuid.uuid4())},
        "serving_values": {"settings_revision": 1, "reference_threshold": 0.6},
        "candidate_values": {"reference_thresholds": [0.5, 0.6]},
    }


def _input_fingerprint(snapshot: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _stored_legacy_run(
    session: Session, snapshot: dict[str, object], *, status: CalibrationRunStatus = CalibrationRunStatus.COMPLETE
) -> CalibrationRun:
    # Insert the pre-fix storage shape directly, bypassing the new creation path.
    terminal = status in (
        CalibrationRunStatus.COMPLETE, CalibrationRunStatus.FAILED, CalibrationRunStatus.INTERRUPTED,
    )
    run = CalibrationRun(
        id=uuid.uuid4(), requested_by_staff_id=uuid.uuid4(), status=status,
        dataset_snapshot=deepcopy(snapshot), dataset_sha256=_input_fingerprint(snapshot),
        started_at=datetime.now(UTC) if status != CalibrationRunStatus.REQUESTED else None,
        finished_at=datetime.now(UTC) if terminal else None,
        error_code="synthetic_failure" if terminal and status != CalibrationRunStatus.COMPLETE else None,
    )
    if status == CalibrationRunStatus.COMPLETE:
        run.result_bundle = {"pipeline_results": [{"label": "before"}]}
    session.add(run)
    session.flush()
    return run


@pytest.mark.parametrize("changed_settings", ["pipeline_revisions", "serving_values", "candidate_values", "all"])
def test_comparison_uses_same_frozen_data_across_legacy_and_new_run_settings(
    comparison_engine: Engine, changed_settings: str,
) -> None:
    data = _comparison_data()
    before_snapshot = _full_input(data)
    after_snapshot = deepcopy(before_snapshot)
    changes = {
        "pipeline_revisions": {"sface": str(uuid.uuid4()), "buffalo_m": str(uuid.uuid4())},
        "serving_values": {"settings_revision": 2, "reference_threshold": 0.8},
        "candidate_values": {"reference_thresholds": [0.7, 0.8]},
    }
    after_snapshot.update(changes if changed_settings == "all" else {
        changed_settings: changes[changed_settings]
    })
    with Session(comparison_engine) as session:
        before = _stored_legacy_run(session, before_snapshot)
        repository = CalibrationRunRepository(session)
        after = repository.create_requested(
            requested_by_staff_id=uuid.uuid4(), dataset_snapshot=after_snapshot,
        )
        repository.start(after.id)
        repository.complete(after.id, result_bundle={"pipeline_results": [{"label": "after"}]})
        before_id, after_id = before.id, after.id
        assert before.dataset_sha256 != after.dataset_sha256
        session.commit()

    with Session(comparison_engine) as session:
        comparison = CalibrationRunRepository(session).compare_complete(
            before_run_id=before_id, after_run_id=after_id,
        )
        assert comparison.dataset_sha256 == _input_fingerprint(data)
        assert comparison.before_result == {"pipeline_results": [{"label": "before"}]}
        assert comparison.after_result == {"pipeline_results": [{"label": "after"}]}
        assert not session.dirty
        session.commit()

    with Session(comparison_engine) as session:
        for run_id, snapshot, label in (
            (before_id, before_snapshot, "before"), (after_id, after_snapshot, "after"),
        ):
            persisted = CalibrationRunRepository(session).require(run_id)
            assert persisted.dataset_snapshot == snapshot
            assert persisted.dataset_sha256 == _input_fingerprint(snapshot)
            assert persisted.result_bundle == {"pipeline_results": [{"label": label}]}


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("photos", 0, "photo_id"), "different-photo"),
        (("photos", 0, "sha256"), "2" * 64),
        (("spa_id",), "different-spa"),
        (("attempts", 0, "attempt_id"), "different-attempt"),
        (("attempts", 0, "annotations", 0, "outcome"), "false"),
        (("attempts", 0, "pipeline_revision_id"), "different-historical-revision"),
        (("attempts", 0, "pipeline_code"), "insightface_buffalo_m"),
        (("attempts", 0, "reference_threshold"), 0.8),
        (("attempts", 0, "pipeline_revisions"), {"historical": "v2"}),
        (("attempts", 0, "serving_values"), {"historical": 0.8}),
        (("attempts", 0, "candidate_values"), [0.7, 0.8]),
        (("extra_dataset_field", "version"), 2),
        (("new_dataset_field",), {"selection": "retained"}),
    ],
)
def test_comparison_rejects_every_changed_data_field_including_nested_evaluation_names(
    comparison_engine: Engine, path: tuple[str | int, ...], replacement: object,
) -> None:
    snapshot = _full_input(_comparison_data())
    changed = deepcopy(snapshot)
    target = changed
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = replacement
    with Session(comparison_engine) as session:
        before = _stored_legacy_run(session, snapshot)
        after = _stored_legacy_run(session, changed)
        with pytest.raises(DatasetMismatchError, match="^dataset_mismatch$"):
            CalibrationRunRepository(session).compare_complete(
                before_run_id=before.id, after_run_id=after.id,
            )
        assert before.dataset_snapshot == snapshot
        assert after.dataset_snapshot == changed
        assert not session.dirty


def test_comparison_preserves_frozen_array_order(comparison_engine: Engine) -> None:
    snapshot = _full_input(_comparison_data())
    reordered = deepcopy(snapshot)
    reordered["photos"] = list(reversed(reordered["photos"]))
    with Session(comparison_engine) as session:
        before = _stored_legacy_run(session, snapshot)
        after = _stored_legacy_run(session, reordered)
        with pytest.raises(DatasetMismatchError, match="^dataset_mismatch$"):
            CalibrationRunRepository(session).compare_complete(
                before_run_id=before.id, after_run_id=after.id,
            )


def test_comparison_requires_both_runs_complete_before_dataset_identity(
    comparison_engine: Engine,
) -> None:
    snapshot = _full_input(_comparison_data())
    with Session(comparison_engine) as session:
        complete = _stored_legacy_run(session, snapshot)
        for status in (
            CalibrationRunStatus.REQUESTED, CalibrationRunStatus.RUNNING,
            CalibrationRunStatus.FAILED, CalibrationRunStatus.INTERRUPTED,
        ):
            incomplete = _stored_legacy_run(session, {"different_data": True}, status=status)
            for before_id, after_id in ((complete.id, incomplete.id), (incomplete.id, complete.id)):
                with pytest.raises(CalibrationRunError, match="only complete Calibration runs"):
                    CalibrationRunRepository(session).compare_complete(
                        before_run_id=before_id, after_run_id=after_id,
                    )

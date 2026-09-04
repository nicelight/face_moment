"""Disposable proof for the durable Calibration run core (FT-011-AC-003)."""

from datetime import UTC, date, datetime, timedelta
import hashlib
import uuid

from alembic import command as alembic_command
from alembic.config import Config
import cv2
import numpy as np
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from face_moment.diagnostics.calibration_runs import (
    CalibrationRunError,
    CalibrationRun,
    CalibrationRunRepository,
    CalibrationRunService,
    CalibrationRunStatus,
    DatasetMismatchError,
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


def test_calibration_run_rejects_attempt_without_persisted_annotations() -> None:
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

            with pytest.raises(
                CalibrationRunError,
                match="Calibration requires applicable annotated Attempts",
            ):
                CalibrationRunService(session).request(
                    requested_by_staff_id=uuid.uuid4(),
                    photo_ids=(photo.id,),
                    selected_attempt_ids=(missing_ground_truth.id,),
                    sface_revision_id=sface.id,
                    buffalo_revision_id=buffalo.id,
                    serving_values={"threshold": 0.5},
                    candidate_values={"thresholds": [0.4, 0.5]},
                )
            assert session.query(CalibrationRun).count() == 0

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
            mismatch = repository.create_requested(requested_by_staff_id=uuid.uuid4(), dataset_snapshot={**snapshot, "candidate_values": [0.7]})
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

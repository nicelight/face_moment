"""Disposable shared-worker proof for Calibration interruption recovery."""

from __future__ import annotations

from datetime import UTC, date, datetime
import hashlib
import multiprocessing
import os
import uuid

import cv2
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.diagnostics.calibration_runs import (
    CalibrationRun,
    CalibrationRunRepository,
    CalibrationRunService,
    CalibrationRunStatus,
)
from face_moment.diagnostics.ground_truth_annotations import GroundTruthAnnotationProvider
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing.initial_pending import InitialPendingRepository, PhotoPipelineState
from face_moment.processing.model_admission import ModelAdmissionError
from face_moment.processing.persistence import ProcessingRuntimeStatus
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.processing.worker_runtime import BackgroundPhotoWorker
from face_moment.promo.attempt import PromoAttempt
from face_moment.serving_control import IngestTargetRepository
from face_moment.serving_control.ingest_target import Spa
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.processing.test_photo_orchestration import disposable_processing_state
from tests.processing.test_shared_worker import _NoFaceOrchestrator


class _Store:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self._payloads = payloads

    def read(self, *, key: str) -> bytes:
        return self._payloads[key]


class _Adapter:
    def __init__(self, revision_id: uuid.UUID, label: str, events: list[str]) -> None:
        self.pipeline_revision_id = revision_id
        self._label = label
        self._events = events

    def process_photo(self, photo: np.ndarray[object, object]) -> tuple[object, ...]:
        assert photo.shape == (12, 20, 3)
        return ()

    def __del__(self) -> None:
        self._events.append(f"release:{self._label}")


def _jpeg(*, fill: int = 0) -> bytes:
    encoded, payload = cv2.imencode(
        ".jpg", np.full((12, 20, 3), fill, dtype=np.uint8)
    )
    assert encoded
    return bytes(payload)


def _revision(session: Session, code: PipelineCode, label: str):
    return PipelineRevisionRepository(session).publish_eligible(
        pipeline_code=code,
        validated_at=datetime.now(UTC),
        detector_id=f"task101-{label}-detector",
        detector_version="v1",
        recognizer_id=f"task101-{label}-recognizer",
        recognizer_version="v1",
        weights_sha256=hashlib.sha256(label.encode()).hexdigest(),
        preprocessing_version="task101-preprocess-v1",
        alignment_version="task101-align-v1",
        normalization_version="task101-normalize-v1",
        embedding_dimension=3,
    )


def _requested_run(
    session: Session,
    *,
    photo: Photo,
    attempt_id: uuid.UUID,
    sface_id: uuid.UUID,
    buffalo_id: uuid.UUID,
) -> CalibrationRun:
    return CalibrationRunService(session).request(
        requested_by_staff_id=uuid.uuid4(),
        photo_ids=(photo.id,),
        selected_attempt_ids=(attempt_id,),
        sface_revision_id=sface_id,
        buffalo_revision_id=buffalo_id,
        serving_values={"threshold": 0.5},
        candidate_values={"thresholds": [0.5]},
    )


def _exit_during_live_calibration(
    database_url: str,
    bound_pipeline_revision_id: uuid.UUID,
    claimed: object,
    crash: object,
) -> None:
    """Terminate after the durable claim and before the worker operation begins."""

    engine = create_engine(database_url)

    def claim() -> uuid.UUID | None:
        with Session(engine) as session:
            run_id = CalibrationRunService(session).claim_next_requested()
            claimed.set()  # type: ignore[attr-defined]
            assert crash.wait(timeout=10)  # type: ignore[attr-defined]
            os._exit(23)
        return run_id

    def execute(run_id: uuid.UUID) -> None:
        raise AssertionError(f"unexpected claimed Calibration evaluation: {run_id}")

    BackgroundPhotoWorker(
        session_factory=lambda: Session(engine),
        orchestrator=_NoFaceOrchestrator(engine),  # type: ignore[arg-type]
        bound_pipeline_revision_id=bound_pipeline_revision_id,
        claim_requested_calibration=claim,
        execute_claimed_calibration=execute,
    ).process_one()


def test_worker_claims_one_requested_calibration_and_releases_for_photo(
    disposable_processing_state: tuple[object, object, str, list[str]],
) -> None:
    """The existing singleton owns the Calibration hold; it is not a second loop."""

    engine, _, _, _ = disposable_processing_state
    revision_id = uuid.uuid4()
    events: list[str] = []

    worker = BackgroundPhotoWorker(
        session_factory=lambda: Session(engine),  # type: ignore[arg-type]
        orchestrator=_NoFaceOrchestrator(engine),  # type: ignore[arg-type]
        bound_pipeline_revision_id=revision_id,
        claim_requested_calibration=lambda: uuid.uuid4(),
        execute_claimed_calibration=lambda run_id: events.append(f"calibration:{run_id}"),
    )

    assert worker.process_one() is True
    assert len(events) == 1 and events[0].startswith("calibration:")
    with Session(engine) as session:  # type: ignore[arg-type]
        runtime = session.get(ProcessingRuntimeStatus, 1)
    assert runtime is not None
    assert runtime.current_operation == "idle"
    assert runtime.operation_started_at is None


def test_selected_adapters_are_sequential_asset_failures_release_and_restart_interrupts() -> None:
    payload = _jpeg()
    with disposable_postgresql_engine("task101_calibration_worker") as engine:
        with Session(engine) as session:
            sface = _revision(session, PipelineCode.OPENCV_SFACE, "sface")
            buffalo = _revision(session, PipelineCode.INSIGHTFACE_BUFFALO_M, "buffalo")
            target = IngestTargetRepository(session).configure_spa(
                name="Task 101", timezone="Asia/Dushanbe", serving_pipeline_revision_id=sface.id
            )
            photo = Photo(
                spa_id=target.spa_id,
                visit_date=date(2026, 9, 5),
                captured_at=datetime(2026, 9, 5, tzinfo=UTC),
                captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
                uploader_id=uuid.uuid4(),
                checksum_sha256=hashlib.sha256(payload).digest(),
                original_object_key="task101/original.jpg",
                original_byte_size=len(payload), width=20, height=12,
                admission_pipeline_revision_id=sface.id,
            )
            session.add(photo)
            session.flush()
            InitialPendingRepository(session).create_initial_pending(
                photo_id=photo.id, pipeline_revision_id=sface.id
            )
            attempt = PromoAttempt(
                id=uuid.uuid4(), spa_id=target.spa_id, client_attempt_id=uuid.uuid4(),
                trigger_source="test", client_release="task101", detector_id="test",
                model_version="test", jpeg_quality=85, camera_device_id="test",
                reference_series_ready_at=datetime(2026, 9, 5, tzinfo=UTC),
                local_detection_completed_ms=1, request_started_ms=2, response_received_ms=3,
                proposal_count=0, settings_revision=1, visit_date=date(2026, 9, 5),
                pipeline_revision_id=sface.id, pipeline_code="opencv_sface", query_source="reference",
                release_id="test", threshold=0.5, quality_settings={}, calibration_id=None,
                deadline_ms=3000, slot_decided_at=datetime(2026, 9, 5, tzinfo=UTC),
                search_started_at=datetime(2026, 9, 5, tzinfo=UTC),
                search_finished_at=datetime(2026, 9, 5, tzinfo=UTC), processing_status="result_issued",
                domain_outcome="result", display_status="confirmed",
                display_expires_at=datetime(2026, 9, 5, tzinfo=UTC),
                display_reported_at=datetime(2026, 9, 5, tzinfo=UTC), qr_fully_visible_elapsed_ms=1,
                created_at=datetime(2026, 9, 5, tzinfo=UTC), updated_at=datetime(2026, 9, 5, tzinfo=UTC),
            )
            session.add(attempt)
            session.flush()
            GroundTruthAnnotationProvider(session).create(
                attempt_id=attempt.id, target_kind="person", detection_occurrence_index=None,
                participant_name="Task 101", outcome="missed",
            )
            run = _requested_run(session, photo=photo, attempt_id=attempt.id, sface_id=sface.id, buffalo_id=buffalo.id)
            run_id = run.id
            photo_id = photo.id
            attempt_id = attempt.id
            spa_id = target.spa_id
            session.commit()

        events: list[str] = []
        fail_buffalo = [False]
        fail_buffalo_with_cv2 = [False]
        recovery_payload = _jpeg(fill=1)
        store = _Store(
            {
                "task101/original.jpg": payload,
                "task101/recovery.jpg": recovery_payload,
            }
        )

        def claim() -> uuid.UUID | None:
            with Session(engine) as session:
                return CalibrationRunService(session).claim_next_requested()

        def execute(run_id: uuid.UUID) -> None:
            with Session(engine) as session:
                def bind(revision: object) -> _Adapter:
                    revision_id = getattr(revision, "id")
                    label = "sface" if revision_id == sface.id else "buffalo"
                    events.append(f"bind:{label}")
                    if fail_buffalo[0] and label == "buffalo":
                        raise ModelAdmissionError("configured read-only asset mismatch")
                    if fail_buffalo_with_cv2[0] and label == "buffalo":
                        raise cv2.error("direct Calibration adapter failed")
                    return _Adapter(revision_id, label, events)
                CalibrationRunService(session).execute_claimed(
                    run_id=run_id, bind_selected_adapter=bind, object_store=store
                )
                session.commit()

        def interrupt() -> None:
            with Session(engine) as session:
                CalibrationRunRepository(session).interrupt_running()
                session.commit()

        worker = BackgroundPhotoWorker(
            session_factory=lambda: Session(engine), orchestrator=_NoFaceOrchestrator(engine),  # type: ignore[arg-type]
            bound_pipeline_revision_id=sface.id, claim_requested_calibration=claim,
            execute_claimed_calibration=execute, interrupt_running_calibrations=interrupt,
        )
        assert worker.process_one() is True
        assert events == ["bind:sface", "release:sface", "bind:buffalo", "release:buffalo"]
        with Session(engine) as session:
            completed = session.get(CalibrationRun, run_id)
            runtime = session.get(ProcessingRuntimeStatus, 1)
            assert completed is not None and completed.status == CalibrationRunStatus.COMPLETE
            assert runtime is not None and runtime.current_operation == "idle"
            spa = session.get(Spa, spa_id)
            assert spa is not None and spa.serving_pipeline_revision_id == sface.id

        with Session(engine) as session:
            photo = session.get(Photo, photo_id)
            assert photo is not None
            unavailable = _requested_run(
                session, photo=photo, attempt_id=attempt_id, sface_id=sface.id, buffalo_id=buffalo.id
            )
            unavailable_id = unavailable.id
            session.commit()
        fail_buffalo[0] = True
        assert worker.process_one() is True
        fail_buffalo[0] = False
        with Session(engine) as session:
            unavailable = session.get(CalibrationRun, unavailable_id)
            runtime = session.get(ProcessingRuntimeStatus, 1)
            spa = session.get(Spa, spa_id)
            assert unavailable is not None and unavailable.status == CalibrationRunStatus.FAILED
            assert unavailable.error_code == "model_unavailable"
            assert runtime is not None and runtime.current_operation == "idle"
            assert spa is not None and spa.serving_pipeline_revision_id == sface.id

        with Session(engine) as session:
            photo = session.get(Photo, photo_id)
            assert photo is not None
            direct_adapter_failure = _requested_run(
                session, photo=photo, attempt_id=attempt_id, sface_id=sface.id, buffalo_id=buffalo.id
            )
            direct_adapter_failure_id = direct_adapter_failure.id
            session.commit()
        fail_buffalo_with_cv2[0] = True
        assert worker.process_one() is True
        fail_buffalo_with_cv2[0] = False
        with Session(engine) as session:
            direct_adapter_failure = session.get(CalibrationRun, direct_adapter_failure_id)
            runtime = session.get(ProcessingRuntimeStatus, 1)
            spa = session.get(Spa, spa_id)
            assert direct_adapter_failure is not None
            assert direct_adapter_failure.status == CalibrationRunStatus.FAILED
            assert direct_adapter_failure.error_code == "model_unavailable"
            assert runtime is not None and runtime.current_operation == "idle"
            assert spa is not None and spa.serving_pipeline_revision_id == sface.id

        assert worker.process_one() is True
        with Session(engine) as session:
            state = session.get(PhotoPipelineState, (photo_id, sface.id))
            assert state is not None and state.status == "no_faces"
            recovery_photo = Photo(
                spa_id=spa_id,
                visit_date=date(2026, 9, 5),
                captured_at=datetime(2026, 9, 5, tzinfo=UTC),
                captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
                uploader_id=uuid.uuid4(),
                checksum_sha256=hashlib.sha256(recovery_payload).digest(),
                original_object_key="task101/recovery.jpg",
                original_byte_size=len(recovery_payload),
                width=20,
                height=12,
                admission_pipeline_revision_id=sface.id,
            )
            session.add(recovery_photo)
            session.flush()
            InitialPendingRepository(session).create_initial_pending(
                photo_id=recovery_photo.id, pipeline_revision_id=sface.id
            )
            crashing = _requested_run(
                session,
                photo=recovery_photo,
                attempt_id=attempt_id,
                sface_id=sface.id,
                buffalo_id=buffalo.id,
            )
            crashing_id = crashing.id
            recovery_photo_id = recovery_photo.id
            session.commit()

        process_context = multiprocessing.get_context("fork")
        claimed = process_context.Event()
        crash = process_context.Event()
        process = process_context.Process(
            target=_exit_during_live_calibration,
            args=(engine.url.render_as_string(hide_password=False), sface.id, claimed, crash),
        )
        process.start()
        try:
            assert claimed.wait(timeout=10)
            with Session(engine) as session:
                running = session.get(CalibrationRun, crashing_id)
                runtime = session.get(ProcessingRuntimeStatus, 1)
                assert running is not None and running.status == CalibrationRunStatus.RUNNING
                assert runtime is not None and runtime.current_operation == "idle"
            crash.set()
            process.join(timeout=10)
            assert process.exitcode == 23
        finally:
            crash.set()
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)

        crashing_worker = BackgroundPhotoWorker(
            session_factory=lambda: Session(engine),
            orchestrator=_NoFaceOrchestrator(engine),  # type: ignore[arg-type]
            bound_pipeline_revision_id=sface.id,
            claim_requested_calibration=claim,
            execute_claimed_calibration=execute,
            interrupt_running_calibrations=interrupt,
        )
        assert crashing_worker.recover_startup() == 0
        with Session(engine) as session:
            interrupted = session.get(CalibrationRun, crashing_id)
            runtime = session.get(ProcessingRuntimeStatus, 1)
            assert interrupted is not None and interrupted.status == CalibrationRunStatus.INTERRUPTED
            assert interrupted.error_code == "worker_interrupted"
            assert runtime is not None and runtime.current_operation == "idle"
            assert CalibrationRunService(session).has_requested() is False

        assert crashing_worker.process_one() is True
        with Session(engine) as session:
            resumed = session.get(PhotoPipelineState, (recovery_photo_id, sface.id))
            assert resumed is not None and resumed.status == "no_faces"
            explicit_rerun = _requested_run(
                session,
                photo=session.get(Photo, recovery_photo_id),
                attempt_id=attempt_id,
                sface_id=sface.id,
                buffalo_id=buffalo.id,
            )
            explicit_rerun_id = explicit_rerun.id
            session.commit()

        assert crashing_worker.process_one() is True
        with Session(engine) as session:
            rerun = session.get(CalibrationRun, explicit_rerun_id)
            assert rerun is not None and rerun.status == CalibrationRunStatus.COMPLETE
            assert session.query(CalibrationRun).count() == 5

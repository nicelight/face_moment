from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import multiprocessing
import os
import uuid

import cv2
import numpy as np
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing.derivatives import (
    DerivativeEncoding,
    DerivativeEncodingConfig,
    PrivatePhotoDerivativeCreator,
)
from face_moment.processing.initial_pending import InitialPendingRepository, PhotoPipelineState
from face_moment.processing.photo_orchestration import PhotoProcessingOrchestrator
from face_moment.processing.persistence import PhotoFace, ProcessingRuntimeStatus
from face_moment.processing.revisions import (
    PipelineCode,
    PipelineRevisionRepository,
)
from face_moment.processing.terminal_publication import TerminalFace
from face_moment.processing.worker_claims import WorkerClaimRepository
from face_moment.processing.worker_runtime import BackgroundPhotoWorker
from face_moment.serving_control import IngestTargetRepository
from face_moment.serving_control.ingest_target import Spa
from tests.processing.test_photo_orchestration import disposable_processing_state


class _TerminalAdapter:
    def __init__(self, pipeline_revision_id: uuid.UUID) -> None:
        self.pipeline_revision_id = pipeline_revision_id

    def process_for_terminal(self, photo: np.ndarray[tuple[int, int, int], np.dtype[np.uint8]]) -> tuple[TerminalFace, ...]:
        assert photo.shape == (12, 20, 3)
        return (
            TerminalFace(
                face_index=0,
                bbox_x=1.0,
                bbox_y=2.0,
                bbox_w=5.0,
                bbox_h=6.0,
                landmarks_json=[
                    [1.0, 2.0],
                    [4.0, 2.0],
                    [3.0, 4.0],
                    [2.0, 6.0],
                    [5.0, 6.0],
                ],
                detection_confidence=0.95,
                embedding=(0.6, 0.8, 0.0),
            ),
        )


def _worker_for_database(
    database_url: str, *, bound_pipeline_revision_id: uuid.UUID | None = None
) -> BackgroundPhotoWorker:
    os.environ["DATABASE_URL"] = database_url
    settings = Settings.from_env()
    engine = create_engine(database_url, pool_pre_ping=True)
    with Session(engine) as session:
        revision_id = bound_pipeline_revision_id or session.scalar(
            select(PhotoPipelineState.pipeline_revision_id).limit(1)
        )
        assert revision_id is not None
    adapter = _TerminalAdapter(revision_id)
    object_store = PrivateObjectStore(settings)
    orchestrator = PhotoProcessingOrchestrator(
        session_factory=lambda: Session(engine),
        object_store=object_store,
        sface_adapter=adapter,
        buffalo_adapter=adapter,
        derivative_creator=PrivatePhotoDerivativeCreator(
            object_store,
            encoding=DerivativeEncodingConfig(
                preview=DerivativeEncoding(maximum_edge=20, jpeg_quality=82),
                thumbnail=DerivativeEncoding(maximum_edge=10, jpeg_quality=75),
            ),
        ),
    )
    return BackgroundPhotoWorker(
        session_factory=lambda: Session(engine),
        orchestrator=orchestrator,
        bound_pipeline_revision_id=revision_id,
    )


def _claim_then_exit(database_url: str, result_queue: multiprocessing.Queue[object]) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            revision_id = session.scalar(
                select(PhotoPipelineState.pipeline_revision_id).limit(1)
            )
            assert revision_id is not None
            claim = WorkerClaimRepository(
                session, bound_pipeline_revision_id=revision_id
            ).claim_oldest_pending()
            assert claim is not None
            session.commit()
            result_queue.put(str(claim.photo_id))
    finally:
        engine.dispose()


def _restart_and_drain(database_url: str, result_queue: multiprocessing.Queue[object]) -> None:
    worker = _worker_for_database(database_url)
    result_queue.put(worker.recover_startup())
    processed = 0
    while worker.process_one():
        processed += 1
    result_queue.put(processed)


def _jpeg() -> bytes:
    encoded, payload = cv2.imencode(".jpg", np.zeros((12, 20, 3), dtype=np.uint8))
    assert encoded
    return bytes(payload)


def _worker_for_fixture(
    *,
    engine: Engine,
    object_store: PrivateObjectStore,
    pipeline_revision_id: uuid.UUID,
) -> BackgroundPhotoWorker:
    adapter = _TerminalAdapter(pipeline_revision_id)
    orchestrator = PhotoProcessingOrchestrator(
        session_factory=lambda: Session(engine),
        object_store=object_store,
        sface_adapter=adapter,
        buffalo_adapter=adapter,
        derivative_creator=PrivatePhotoDerivativeCreator(
            object_store,
            encoding=DerivativeEncodingConfig(
                preview=DerivativeEncoding(maximum_edge=20, jpeg_quality=82),
                thumbnail=DerivativeEncoding(maximum_edge=10, jpeg_quality=75),
            ),
        ),
    )
    return BackgroundPhotoWorker(
        session_factory=lambda: Session(engine),
        orchestrator=orchestrator,
        bound_pipeline_revision_id=pipeline_revision_id,
    )


def test_real_worker_process_restart_recovers_and_drains_active_and_queued_work(
    disposable_processing_state: tuple[Engine, PrivateObjectStore, str, list[str]],
) -> None:
    engine, object_store, run_prefix, derivative_prefixes = disposable_processing_state
    marker = uuid.uuid4().hex
    photo_ids: list[uuid.UUID] = []

    with Session(engine) as session:
        revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=datetime.now(timezone.utc),
            detector_id="task-026-detector",
            detector_version="v1",
            recognizer_id="task-026-recognizer",
            recognizer_version="v1",
            weights_sha256="0" * 64,
            preprocessing_version="task-026-preprocessing-v1",
            alignment_version="task-026-alignment-v1",
            normalization_version="task-026-normalization-v1",
            embedding_dimension=3,
        )
        target = IngestTargetRepository(session).configure_spa(
            name=f"task-026-{marker}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=revision.id,
        )
        for label in ("active", "queued"):
            photo = Photo(
                spa_id=target.spa_id,
                visit_date=date(2026, 8, 14),
                captured_at=datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc),
                captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
                uploader_id=uuid.uuid4(),
                checksum_sha256=hashlib.sha256(f"{label}-{marker}".encode()).digest(),
                original_object_key=f"{run_prefix}{label}/original.jpg",
                original_byte_size=123,
                width=20,
                height=12,
            )
            session.add(photo)
            session.flush()
            InitialPendingRepository(session).create_initial_pending(
                photo_id=photo.id,
                pipeline_revision_id=revision.id,
            )
            photo_ids.append(photo.id)
            derivative_prefixes.append(
                f"private/derivatives/{photo.id}/{revision.id}/"
            )
        session.commit()

    for photo_id, label in zip(photo_ids, ("active", "queued"), strict=True):
        object_store.put(key=f"{run_prefix}{label}/original.jpg", body=_jpeg())

    context = multiprocessing.get_context("fork")
    first_result = context.Queue()
    predecessor = context.Process(
        target=_claim_then_exit,
        args=(engine.url.render_as_string(hide_password=False), first_result),
    )
    predecessor.start()
    predecessor.join(timeout=30)
    assert predecessor.exitcode == 0
    assert uuid.UUID(str(first_result.get(timeout=5))) in photo_ids

    with Session(engine) as session:
        before_restart = {
            state.photo_id: (state.status, state.attempt_count)
            for state in session.scalars(select(PhotoPipelineState))
            if state.photo_id in photo_ids
        }
    assert sorted(status for status, _attempts in before_restart.values()) == [
        "pending",
        "processing",
    ]

    restart_result = context.Queue()
    restarted = context.Process(
        target=_restart_and_drain,
        args=(engine.url.render_as_string(hide_password=False), restart_result),
    )
    restarted.start()
    restarted.join(timeout=60)
    assert restarted.exitcode == 0
    assert restart_result.get(timeout=5) == 1
    assert restart_result.get(timeout=5) == 2

    with Session(engine) as session:
        states = {
            state.photo_id: state
            for state in session.scalars(select(PhotoPipelineState))
            if state.photo_id in photo_ids
        }
        faces = tuple(
            session.scalars(select(PhotoFace).where(PhotoFace.photo_id.in_(photo_ids)))
        )
        runtime = session.get(ProcessingRuntimeStatus, 1)

    assert set(states) == set(photo_ids)
    assert {state.status for state in states.values()} == {"ready"}
    assert sorted(state.attempt_count for state in states.values()) == [1, 2]
    assert len(faces) == 2
    assert runtime is not None
    assert runtime.last_recovered_count == 1
    assert runtime.current_operation == "idle"
    assert runtime.operation_started_at is None
    for state in states.values():
        assert state.preview_object_key is not None
        assert state.thumbnail_object_key is not None
        assert object_store.read(key=state.preview_object_key)
        assert object_store.read(key=state.thumbnail_object_key)


def test_bound_worker_stops_claiming_after_committed_revision_changes_until_restart(
    disposable_processing_state: tuple[Engine, PrivateObjectStore, str, list[str]],
) -> None:
    engine, object_store, run_prefix, derivative_prefixes = disposable_processing_state
    marker = uuid.uuid4().hex

    with Session(engine) as session:
        revision_a = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=datetime.now(timezone.utc),
            detector_id="task-026-a-detector",
            detector_version="v1",
            recognizer_id="task-026-a-recognizer",
            recognizer_version="v1",
            weights_sha256="a" * 64,
            preprocessing_version="task-026-preprocessing-v1",
            alignment_version="task-026-alignment-v1",
            normalization_version="task-026-normalization-v1",
            embedding_dimension=3,
        )
        revision_b = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=datetime.now(timezone.utc),
            detector_id="task-026-b-detector",
            detector_version="v1",
            recognizer_id="task-026-b-recognizer",
            recognizer_version="v1",
            weights_sha256="b" * 64,
            preprocessing_version="task-026-preprocessing-v1",
            alignment_version="task-026-alignment-v1",
            normalization_version="task-026-normalization-v1",
            embedding_dimension=3,
        )
        target = IngestTargetRepository(session).configure_spa(
            name=f"task-026-switch-{marker}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=revision_a.id,
        )
        photo_ids: dict[str, uuid.UUID] = {}
        for label, revision_id in (("a", revision_a.id), ("b", revision_b.id)):
            photo = Photo(
                spa_id=target.spa_id,
                visit_date=date(2026, 8, 14),
                captured_at=datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc),
                captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
                uploader_id=uuid.uuid4(),
                checksum_sha256=hashlib.sha256(f"{label}-{marker}".encode()).digest(),
                original_object_key=f"{run_prefix}{label}/original.jpg",
                original_byte_size=123,
                width=20,
                height=12,
            )
            session.add(photo)
            session.flush()
            InitialPendingRepository(session).create_initial_pending(
                photo_id=photo.id,
                pipeline_revision_id=revision_id,
            )
            photo_ids[label] = photo.id
            derivative_prefixes.append(
                f"private/derivatives/{photo.id}/{revision_id}/"
            )
        session.commit()

    object_store.put(key=f"{run_prefix}a/original.jpg", body=_jpeg())
    object_store.put(key=f"{run_prefix}b/original.jpg", body=_jpeg())
    bound_a_worker = _worker_for_fixture(
        engine=engine,
        object_store=object_store,
        pipeline_revision_id=revision_a.id,
    )

    with Session(engine) as session:
        spa = session.get(Spa, target.spa_id)
        assert spa is not None
        spa.serving_pipeline_revision_id = revision_b.id
        session.commit()

    assert bound_a_worker.process_one() is False

    with Session(engine) as session:
        states_before_restart = {
            state.photo_id: (state.status, state.attempt_count)
            for state in session.scalars(select(PhotoPipelineState))
            if state.photo_id in photo_ids.values()
        }
    assert states_before_restart == {
        photo_ids["a"]: ("pending", 0),
        photo_ids["b"]: ("pending", 0),
    }

    restarted_b_worker = _worker_for_fixture(
        engine=engine,
        object_store=object_store,
        pipeline_revision_id=revision_b.id,
    )
    assert restarted_b_worker.process_one() is True
    assert restarted_b_worker.process_one() is False

    with Session(engine) as session:
        state_a = session.get(PhotoPipelineState, (photo_ids["a"], revision_a.id))
        state_b = session.get(PhotoPipelineState, (photo_ids["b"], revision_b.id))
    assert state_a is not None
    assert state_b is not None
    assert (state_a.status, state_a.attempt_count) == ("pending", 0)
    assert (state_b.status, state_b.attempt_count) == ("ready", 1)

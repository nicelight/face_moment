from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import uuid

import cv2
import numpy as np
import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing.derivatives import (
    DerivativeEncoding,
    DerivativeEncodingConfig,
    PrivatePhotoDerivativeCreator,
)
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.photo_orchestration import PhotoProcessingOrchestrator
from face_moment.processing.persistence import PhotoFace, ProcessingRuntimeStatus
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.processing.terminal_publication import TerminalFace
from face_moment.processing.worker_claims import WorkerClaimRepository
from face_moment.serving_control import IngestTargetRepository


_CANONICAL_RUNTIME = (None, None, 0, "idle", None)


@dataclass(frozen=True, slots=True)
class _ClaimedFixture:
    marker: str
    photo_id: uuid.UUID
    pipeline_revision_id: uuid.UUID
    spa_id: uuid.UUID
    original_key: str


class _RecordingAdapter:
    def __init__(
        self,
        *,
        pipeline_revision_id: uuid.UUID,
        label: str,
        terminal_faces: tuple[TerminalFace, ...] = (),
        failure: Exception | None = None,
    ) -> None:
        self.pipeline_revision_id = pipeline_revision_id
        self.label = label
        self.terminal_faces = terminal_faces
        self.failure = failure
        self.calls: list[str] = []

    def process_for_terminal(
        self, photo: np.ndarray[tuple[int, int, int], np.dtype[np.uint8]]
    ) -> tuple[TerminalFace, ...]:
        assert photo.shape == (12, 20, 3)
        self.calls.append(self.label)
        if self.failure is not None:
            raise self.failure
        return self.terminal_faces


@pytest.fixture
def disposable_processing_state(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[Engine, PrivateObjectStore, str, list[str]]]:
    base_settings = Settings.from_env()
    probe_database = f"task024_{uuid.uuid4().hex}"
    probe_url = make_url(base_settings.database_url).set(database=probe_database)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {probe_database}"))
    monkeypatch.setenv("DATABASE_URL", probe_url.render_as_string(hide_password=False))
    settings = Settings.from_env()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    object_store = PrivateObjectStore(settings)
    run_prefix = f"task024/{uuid.uuid4().hex}/"
    derivative_prefixes: list[str] = []

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        ensure_bucket(settings)
        assert _runtime_snapshot(engine) == _CANONICAL_RUNTIME
        yield engine, object_store, run_prefix, derivative_prefixes
    finally:
        for prefix in derivative_prefixes:
            for key in object_store.list_keys(prefix=prefix):
                object_store.delete(key=key)
            assert object_store.list_keys(prefix=prefix) == set()
        for key in object_store.list_keys(prefix=run_prefix):
            object_store.delete(key=key)
        assert object_store.list_keys(prefix=run_prefix) == set()
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {probe_database} WITH (FORCE)"))
        admin_engine.dispose()


def _runtime_snapshot(engine: Engine) -> tuple[object, ...]:
    with Session(engine) as session:
        runtime = session.get(ProcessingRuntimeStatus, 1)
        assert runtime is not None
        return (
            runtime.worker_started_at,
            runtime.last_recovery_at,
            runtime.last_recovered_count,
            runtime.current_operation,
            runtime.operation_started_at,
        )


def _synthetic_jpeg() -> bytes:
    image = np.zeros((12, 20, 3), dtype=np.uint8)
    encoded, payload = cv2.imencode(".jpg", image)
    assert encoded
    return bytes(payload)


def _terminal_face() -> TerminalFace:
    return TerminalFace(
        face_index=0,
        bbox_x=1.0,
        bbox_y=2.0,
        bbox_w=5.0,
        bbox_h=6.0,
        landmarks_json=[[1.0, 2.0], [4.0, 2.0], [3.0, 4.0], [2.0, 6.0], [5.0, 6.0]],
        detection_confidence=0.95,
        embedding=(0.6, 0.8, 0.0),
    )


def _claimed_fixture(
    engine: Engine,
    object_store: PrivateObjectStore,
    *,
    run_prefix: str,
    derivative_prefixes: list[str],
    pipeline_code: PipelineCode,
) -> _ClaimedFixture:
    marker = uuid.uuid4().hex
    original_key = f"{run_prefix}{marker}/original.jpg"
    with Session(engine) as session:
        revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=pipeline_code,
            validated_at=datetime.now(timezone.utc),
            detector_id="task024-detector",
            detector_version="v1",
            recognizer_id="task024-recognizer",
            recognizer_version="v1",
            weights_sha256="0" * 64,
            preprocessing_version="task024-preprocessing-v1",
            alignment_version="task024-alignment-v1",
            normalization_version="task024-normalization-v1",
            embedding_dimension=3,
        )
        target = IngestTargetRepository(session).configure_spa(
            name=f"task024-{marker}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=revision.id,
        )
        photo = Photo(
            spa_id=target.spa_id,
            visit_date=date(2026, 8, 13),
            captured_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
            captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
            uploader_id=uuid.uuid4(),
            checksum_sha256=hashlib.sha256(marker.encode()).digest(),
            original_object_key=original_key,
            original_byte_size=123,
            width=20,
            height=12,
        )
        session.add(photo)
        session.flush()
        from face_moment.processing.initial_pending import InitialPendingRepository

        InitialPendingRepository(session).create_initial_pending(
            photo_id=photo.id,
            pipeline_revision_id=revision.id,
        )
        session.commit()
        fixture = _ClaimedFixture(
            marker=marker,
            photo_id=photo.id,
            pipeline_revision_id=revision.id,
            spa_id=target.spa_id,
            original_key=original_key,
        )
        derivative_prefixes.append(
            f"private/derivatives/{fixture.photo_id}/{fixture.pipeline_revision_id}/"
        )

    object_store.put(key=fixture.original_key, body=_synthetic_jpeg())
    with Session(engine) as session:
        claim = WorkerClaimRepository(
            session, bound_pipeline_revision_id=fixture.pipeline_revision_id
        ).claim_oldest_pending()
        assert claim is not None
        assert (claim.photo_id, claim.pipeline_revision_id) == (
            fixture.photo_id,
            fixture.pipeline_revision_id,
        )
        session.commit()
    return fixture


def _creator(object_store: PrivateObjectStore) -> PrivatePhotoDerivativeCreator:
    return PrivatePhotoDerivativeCreator(
        object_store,
        encoding=DerivativeEncodingConfig(
            preview=DerivativeEncoding(maximum_edge=8, jpeg_quality=65),
            thumbnail=DerivativeEncoding(maximum_edge=4, jpeg_quality=45),
        ),
    )


def _state(engine: Engine, fixture: _ClaimedFixture) -> PhotoPipelineState:
    with Session(engine) as session:
        state = session.get(
            PhotoPipelineState,
            (fixture.photo_id, fixture.pipeline_revision_id),
        )
        assert state is not None
        session.expunge(state)
        return state


@pytest.mark.parametrize(
    ("pipeline_code", "selected_label", "other_label"),
    (
        (PipelineCode.OPENCV_SFACE, "sface", "buffalo"),
        (PipelineCode.INSIGHTFACE_BUFFALO_M, "buffalo", "sface"),
    ),
)
def test_orchestration_uses_only_the_claimed_revision_adapter_and_publishes_ready(
    disposable_processing_state: tuple[Engine, PrivateObjectStore, str, list[str]],
    pipeline_code: PipelineCode,
    selected_label: str,
    other_label: str,
) -> None:
    engine, object_store, run_prefix, derivative_prefixes = disposable_processing_state
    fixture = _claimed_fixture(
        engine,
        object_store,
        run_prefix=run_prefix,
        derivative_prefixes=derivative_prefixes,
        pipeline_code=pipeline_code,
    )
    selected = _RecordingAdapter(
        pipeline_revision_id=fixture.pipeline_revision_id,
        label=selected_label,
        terminal_faces=(_terminal_face(),),
    )
    other = _RecordingAdapter(
        pipeline_revision_id=uuid.uuid4(), label=other_label, terminal_faces=()
    )
    sface, buffalo = (
        (selected, other)
        if pipeline_code is PipelineCode.OPENCV_SFACE
        else (other, selected)
    )

    result = PhotoProcessingOrchestrator(
        session_factory=lambda: Session(engine),
        object_store=object_store,
        sface_adapter=sface,
        buffalo_adapter=buffalo,
        derivative_creator=_creator(object_store),
    ).process_claimed(
        photo_id=fixture.photo_id,
        pipeline_revision_id=fixture.pipeline_revision_id,
    )

    state = _state(engine, fixture)
    assert result == state.status == "ready"
    assert selected.calls == [selected_label]
    assert other.calls == []
    assert state.preview_object_key is not None
    assert state.thumbnail_object_key is not None
    assert object_store.read(key=state.preview_object_key)
    assert object_store.read(key=state.thumbnail_object_key)
    with Session(engine) as session:
        assert len(
            tuple(
                session.scalars(
                    select(PhotoFace).where(PhotoFace.photo_id == fixture.photo_id)
                )
            )
        ) == 1
    assert _runtime_snapshot(engine) == _CANONICAL_RUNTIME


def test_orchestration_publishes_no_faces_without_derivatives(
    disposable_processing_state: tuple[Engine, PrivateObjectStore, str, list[str]],
) -> None:
    engine, object_store, run_prefix, derivative_prefixes = disposable_processing_state
    fixture = _claimed_fixture(
        engine,
        object_store,
        run_prefix=run_prefix,
        derivative_prefixes=derivative_prefixes,
        pipeline_code=PipelineCode.OPENCV_SFACE,
    )
    sface = _RecordingAdapter(
        pipeline_revision_id=fixture.pipeline_revision_id, label="sface"
    )
    buffalo = _RecordingAdapter(pipeline_revision_id=uuid.uuid4(), label="buffalo")

    result = PhotoProcessingOrchestrator(
        session_factory=lambda: Session(engine),
        object_store=object_store,
        sface_adapter=sface,
        buffalo_adapter=buffalo,
        derivative_creator=_creator(object_store),
    ).process_claimed(
        photo_id=fixture.photo_id,
        pipeline_revision_id=fixture.pipeline_revision_id,
    )

    state = _state(engine, fixture)
    assert result == state.status == "no_faces"
    assert (state.preview_object_key, state.thumbnail_object_key) == (None, None)
    assert sface.calls == ["sface"]
    assert buffalo.calls == []
    assert _runtime_snapshot(engine) == _CANONICAL_RUNTIME


def test_orchestration_delegates_an_injected_failure_to_the_claim_boundary(
    disposable_processing_state: tuple[Engine, PrivateObjectStore, str, list[str]],
) -> None:
    engine, object_store, run_prefix, derivative_prefixes = disposable_processing_state
    fixture = _claimed_fixture(
        engine,
        object_store,
        run_prefix=run_prefix,
        derivative_prefixes=derivative_prefixes,
        pipeline_code=PipelineCode.OPENCV_SFACE,
    )
    sface = _RecordingAdapter(
        pipeline_revision_id=fixture.pipeline_revision_id,
        label="sface",
        failure=RuntimeError("injected adapter failure"),
    )
    buffalo = _RecordingAdapter(pipeline_revision_id=uuid.uuid4(), label="buffalo")

    result = PhotoProcessingOrchestrator(
        session_factory=lambda: Session(engine),
        object_store=object_store,
        sface_adapter=sface,
        buffalo_adapter=buffalo,
        derivative_creator=_creator(object_store),
    ).process_claimed(
        photo_id=fixture.photo_id,
        pipeline_revision_id=fixture.pipeline_revision_id,
    )

    state = _state(engine, fixture)
    assert result == state.status == "pending"
    assert state.last_error == "processing failed"
    assert state.preview_object_key is None
    assert state.thumbnail_object_key is None
    assert object_store.list_keys(
        prefix=f"private/derivatives/{fixture.photo_id}/{fixture.pipeline_revision_id}/"
    ) == set()
    assert sface.calls == ["sface"]
    assert buffalo.calls == []
    assert _runtime_snapshot(engine) == _CANONICAL_RUNTIME

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import uuid

import cv2
import numpy as np
import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing import (
    InitialPendingRepository,
    PipelineCode,
    PipelineRevisionRepository,
)
from face_moment.processing.derivatives import (
    DerivativeEncoding,
    DerivativeEncodingConfig,
    PrivatePhotoDerivativeCreator,
)
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace, ProcessingRuntimeStatus
from face_moment.processing.terminal_publication import (
    TerminalFace,
    TerminalPublicationRepository,
)
from face_moment.processing.worker_claims import WorkerClaimRepository
from face_moment.serving_control import IngestTargetRepository
from face_moment.serving_control.ingest_target import Spa
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@dataclass(frozen=True, slots=True)
class _Fixture:
    marker: str
    photo_id: uuid.UUID
    pipeline_revision_id: uuid.UUID
    spa_id: uuid.UUID
    original_key: str


_CANONICAL_RUNTIME = (None, None, 0, "idle", None)


def _synthetic_jpeg() -> bytes:
    image = np.zeros((12, 20, 3), dtype=np.uint8)
    image[:, :10] = (12, 35, 220)
    image[:, 10:] = (210, 145, 25)
    encoded, payload = cv2.imencode(
        ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 96]
    )
    assert encoded
    return bytes(payload)


def _face() -> TerminalFace:
    return TerminalFace(
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
        embedding=(1.0,) + (0.0,) * 127,
    )


def _creator(object_store: PrivateObjectStore) -> PrivatePhotoDerivativeCreator:
    return PrivatePhotoDerivativeCreator(
        object_store,
        encoding=DerivativeEncodingConfig(
            preview=DerivativeEncoding(maximum_edge=8, jpeg_quality=65),
            thumbnail=DerivativeEncoding(maximum_edge=4, jpeg_quality=45),
        ),
    )


def _fixture(engine: Engine, object_store: PrivateObjectStore) -> _Fixture:
    marker = uuid.uuid4().hex
    original_key = f"task023/{marker}/original.jpg"
    with Session(engine) as session:  # type: ignore[arg-type]
        revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=datetime.now(timezone.utc) + timedelta(days=1),
            **PIPELINE_COMPATIBILITY,
        )
        target = IngestTargetRepository(session).configure_spa(
            name=f"task-023-{marker}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=revision.id,
        )
        photo = Photo(
            spa_id=target.spa_id,
            visit_date=date(2026, 8, 12),
            captured_at=datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc),
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
        InitialPendingRepository(session).create_initial_pending(
            photo_id=photo.id,
            pipeline_revision_id=revision.id,
        )
        state = session.get(PhotoPipelineState, (photo.id, revision.id))
        assert state is not None
        state.status_changed_at = datetime(1970, 1, 1, tzinfo=timezone.utc)
        photo_id = photo.id
        pipeline_revision_id = revision.id
        spa_id = target.spa_id
        session.commit()

    object_store.put(key=original_key, body=_synthetic_jpeg())
    with Session(engine) as session:
        claim = WorkerClaimRepository(
            session, bound_pipeline_revision_id=pipeline_revision_id
        ).claim_oldest_pending()
        assert claim is not None
        assert claim.photo_id == photo_id
        session.commit()
    return _Fixture(
        marker=marker,
        photo_id=photo_id,
        pipeline_revision_id=pipeline_revision_id,
        spa_id=spa_id,
        original_key=original_key,
    )


def _state_snapshot(engine: Engine, fixture: _Fixture) -> tuple[object, ...]:
    with Session(engine) as session:
        state = session.get(
            PhotoPipelineState, (fixture.photo_id, fixture.pipeline_revision_id)
        )
        assert state is not None
        faces = tuple(
            session.scalars(
                select(PhotoFace)
                .where(
                    PhotoFace.photo_id == fixture.photo_id,
                    PhotoFace.pipeline_revision_id == fixture.pipeline_revision_id,
                )
                .order_by(PhotoFace.face_index)
            )
        )
        runtime = session.get(ProcessingRuntimeStatus, 1)
        assert runtime is not None
        return (
            state.status,
            state.attempt_count,
            state.status_changed_at,
            state.searchable_at,
            state.last_error,
            state.preview_object_key,
            state.thumbnail_object_key,
            tuple(
                (
                    face.id,
                    face.face_index,
                    face.bbox_x,
                    face.bbox_y,
                    face.bbox_w,
                    face.bbox_h,
                    face.detection_confidence,
                    face.created_at,
                )
                for face in faces
            ),
            runtime.current_operation,
            runtime.operation_started_at,
        )


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


def _checksums(
    object_store: PrivateObjectStore, preview_key: str, thumbnail_key: str
) -> tuple[str, str]:
    return (
        hashlib.sha256(object_store.read(key=preview_key)).hexdigest(),
        hashlib.sha256(object_store.read(key=thumbnail_key)).hexdigest(),
    )


def _face_shape(snapshot: tuple[object, ...]) -> tuple[object, ...]:
    faces = snapshot[7]
    assert isinstance(faces, tuple)
    return tuple((face[1], *face[2:7]) for face in faces)


def _cleanup(engine: Engine, object_store: PrivateObjectStore, fixture: _Fixture) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "DELETE FROM face_moment.photo_faces WHERE photo_id = %s",
            (fixture.photo_id,),
        )
        connection.exec_driver_sql(
            "DELETE FROM face_moment.photo_pipeline_states WHERE photo_id = %s",
            (fixture.photo_id,),
        )
        connection.exec_driver_sql(
            "DELETE FROM face_moment.photos WHERE id = %s", (fixture.photo_id,)
        )
        connection.exec_driver_sql(
            "DELETE FROM face_moment.spas WHERE id = %s", (fixture.spa_id,)
        )
        connection.exec_driver_sql(
            "DELETE FROM face_moment.pipeline_revisions WHERE id = %s",
            (fixture.pipeline_revision_id,),
        )
    for key in object_store.list_keys(prefix=f"task023/{fixture.marker}/"):
        object_store.delete(key=key)
    derivative_prefix = (
        f"private/derivatives/{fixture.photo_id}/{fixture.pipeline_revision_id}/"
    )
    for key in object_store.list_keys(prefix=derivative_prefix):
        object_store.delete(key=key)
    assert object_store.list_keys(prefix=f"task023/{fixture.marker}/") == set()
    assert object_store.list_keys(prefix=derivative_prefix) == set()


def _cleanup_abandoned_task_residue(
    engine: Engine, object_store: PrivateObjectStore
) -> None:
    """Remove only stale rows/objects from an interrupted copy of this fixture."""

    with Session(engine) as session:
        stale = tuple(
            session.execute(
                select(
                    Photo.id,
                    Photo.original_object_key,
                    PhotoPipelineState.pipeline_revision_id,
                    Spa.id,
                )
                .join(PhotoPipelineState, PhotoPipelineState.photo_id == Photo.id)
                .join(Spa, Spa.id == Photo.spa_id)
                .where(Spa.name.like("task-023-%"))
            )
        )
    for photo_id, original_key, pipeline_revision_id, spa_id in stale:
        _cleanup(
            engine,
            object_store,
            _Fixture(
                marker=original_key.split("/")[1],
                photo_id=photo_id,
                pipeline_revision_id=pipeline_revision_id,
                spa_id=spa_id,
                original_key=original_key,
            ),
        )


def _return_invalid_fixture_claim_to_pending(engine: Engine, fixture: _Fixture) -> None:
    """Use the existing claim boundary to restore this fixture's idle baseline."""

    with Session(engine) as session:
        returned = WorkerClaimRepository(
            session,
            bound_pipeline_revision_id=fixture.pipeline_revision_id,
        ).record_failure(
            photo_id=fixture.photo_id,
            pipeline_revision_id=fixture.pipeline_revision_id,
        )
        assert returned.status == "pending"
        runtime = session.get(ProcessingRuntimeStatus, 1)
        assert runtime is not None
        assert runtime.current_operation == "idle"
        assert runtime.operation_started_at is None
        session.commit()


def test_terminal_publication_converges_after_repeat_and_precommit_interruption() -> None:
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    settings = Settings.from_env()
    ensure_bucket(settings)
    object_store = PrivateObjectStore(settings)
    normal: _Fixture | None = None
    interrupted: _Fixture | None = None

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        _cleanup_abandoned_task_residue(engine, object_store)
        normal = _fixture(engine, object_store)
        normal_derivatives = _creator(object_store).create(
            photo_id=normal.photo_id,
            pipeline_revision_id=normal.pipeline_revision_id,
            original_object_key=normal.original_key,
        )
        normal_checksums = _checksums(
            object_store,
            normal_derivatives.preview_object_key,
            normal_derivatives.thumbnail_object_key,
        )
        with Session(engine) as session:
            TerminalPublicationRepository(session).publish_ready(
                photo_id=normal.photo_id,
                pipeline_revision_id=normal.pipeline_revision_id,
                faces=(_face(),),
                derivatives=normal_derivatives,
            )
            session.commit()
        normal_terminal = _state_snapshot(engine, normal)

        interrupted = _fixture(engine, object_store)
        interrupted_derivatives = _creator(object_store).create(
            photo_id=interrupted.photo_id,
            pipeline_revision_id=interrupted.pipeline_revision_id,
            original_object_key=interrupted.original_key,
        )
        interrupted_checksums = _checksums(
            object_store,
            interrupted_derivatives.preview_object_key,
            interrupted_derivatives.thumbnail_object_key,
        )
        with Session(engine) as session:
            TerminalPublicationRepository(session).publish_ready(
                photo_id=interrupted.photo_id,
                pipeline_revision_id=interrupted.pipeline_revision_id,
                faces=(_face(),),
                derivatives=interrupted_derivatives,
            )
            session.rollback()
        precommit_snapshot = _state_snapshot(engine, interrupted)
        assert precommit_snapshot[0] == "processing"
        assert precommit_snapshot[7] == ()
        assert precommit_snapshot[8:] == ("photo_processing", precommit_snapshot[9])

        resumed_derivatives = _creator(object_store).create(
            photo_id=interrupted.photo_id,
            pipeline_revision_id=interrupted.pipeline_revision_id,
            original_object_key=interrupted.original_key,
        )
        assert resumed_derivatives == interrupted_derivatives
        assert _checksums(
            object_store,
            resumed_derivatives.preview_object_key,
            resumed_derivatives.thumbnail_object_key,
        ) == interrupted_checksums
        with Session(engine) as session:
            TerminalPublicationRepository(session).publish_ready(
                photo_id=interrupted.photo_id,
                pipeline_revision_id=interrupted.pipeline_revision_id,
                faces=(_face(),),
                derivatives=resumed_derivatives,
            )
            session.commit()
        interrupted_terminal = _state_snapshot(engine, interrupted)
        assert interrupted_terminal[0] == normal_terminal[0] == "ready"
        assert interrupted_terminal[1] == normal_terminal[1] == 1
        assert interrupted_terminal[4] == normal_terminal[4] is None
        assert _face_shape(interrupted_terminal) == _face_shape(normal_terminal)
        assert interrupted_terminal[8:] == normal_terminal[8:] == ("idle", None)
        assert interrupted_checksums == normal_checksums

        before_repeat = _state_snapshot(engine, interrupted)
        with Session(engine) as session:
            TerminalPublicationRepository(session).publish_ready(
                photo_id=interrupted.photo_id,
                pipeline_revision_id=interrupted.pipeline_revision_id,
                faces=(_face(),),
                derivatives=resumed_derivatives,
            )
            session.commit()
        assert _state_snapshot(engine, interrupted) == before_repeat
    finally:
        if normal is not None:
            _cleanup(engine, object_store, normal)
        if interrupted is not None:
            _cleanup(engine, object_store, interrupted)
        engine.dispose()


def test_no_faces_terminal_publication_has_no_faces_or_derivative_references() -> None:
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    settings = Settings.from_env()
    ensure_bucket(settings)
    object_store = PrivateObjectStore(settings)
    fixture: _Fixture | None = None

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        _cleanup_abandoned_task_residue(engine, object_store)
        fixture = _fixture(engine, object_store)
        with Session(engine) as session:
            TerminalPublicationRepository(session).publish_no_faces(
                photo_id=fixture.photo_id,
                pipeline_revision_id=fixture.pipeline_revision_id,
            )
            session.commit()
        terminal = _state_snapshot(engine, fixture)
        assert terminal[:7] == (
            "no_faces",
            1,
            terminal[2],
            None,
            None,
            None,
            None,
        )
        assert terminal[7:] == ((), "idle", None)

        with Session(engine) as session:
            TerminalPublicationRepository(session).publish_no_faces(
                photo_id=fixture.photo_id,
                pipeline_revision_id=fixture.pipeline_revision_id,
            )
            session.commit()
        assert _state_snapshot(engine, fixture) == terminal
    finally:
        if fixture is not None:
            _cleanup(engine, object_store, fixture)
        engine.dispose()


@pytest.mark.parametrize(
    "invalid_face",
    (
        replace(_face(), landmarks_json=None),
        replace(
            _face(),
            landmarks_json=[
                [float("nan"), 2.0],
                [4.0, 2.0],
                [3.0, 4.0],
                [2.0, 6.0],
                [5.0, 6.0],
            ],
        ),
        replace(_face(), bbox_x=17.0, bbox_w=4.0),
    ),
    ids=("missing-landmarks", "non-finite-landmarks", "out-of-photo-bbox"),
)
def test_terminal_publication_rejects_invalid_face_without_terminal_mutation(
    invalid_face: TerminalFace,
) -> None:
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    settings = Settings.from_env()
    ensure_bucket(settings)
    object_store = PrivateObjectStore(settings)
    fixture: _Fixture | None = None
    runtime_baseline = _runtime_snapshot(engine)
    assert runtime_baseline == _CANONICAL_RUNTIME

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        _cleanup_abandoned_task_residue(engine, object_store)
        fixture = _fixture(engine, object_store)
        derivatives = _creator(object_store).create(
            photo_id=fixture.photo_id,
            pipeline_revision_id=fixture.pipeline_revision_id,
            original_object_key=fixture.original_key,
        )
        object_checksums = _checksums(
            object_store,
            derivatives.preview_object_key,
            derivatives.thumbnail_object_key,
        )
        before = _state_snapshot(engine, fixture)

        with Session(engine) as session:
            with pytest.raises(ValueError):
                TerminalPublicationRepository(session).publish_ready(
                    photo_id=fixture.photo_id,
                    pipeline_revision_id=fixture.pipeline_revision_id,
                    faces=(invalid_face,),
                    derivatives=derivatives,
                )
            session.rollback()

        after = _state_snapshot(engine, fixture)
        assert after == before
        assert after[0] not in {"ready", "no_faces"}
        assert _checksums(
            object_store,
            derivatives.preview_object_key,
            derivatives.thumbnail_object_key,
        ) == object_checksums
    finally:
        if fixture is not None:
            _return_invalid_fixture_claim_to_pending(engine, fixture)
            _cleanup(engine, object_store, fixture)
        assert _runtime_snapshot(engine) == runtime_baseline
        engine.dispose()

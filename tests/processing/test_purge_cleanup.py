from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.diagnostics.evidence import DiagnosticEvidence
from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing import ProcessingPurgeCleanup
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.promo.attempt import PromoAttempt
from face_moment.promo.session import PromoSession
from face_moment.serving_control.ingest_target import IngestTargetRepository, Spa


@dataclass(frozen=True, slots=True)
class _Fixture:
    marker: str
    photo_id: uuid.UUID
    spa_id: uuid.UUID
    revision_ids: tuple[uuid.UUID, uuid.UUID]
    original_key: str
    derivative_keys: tuple[str, ...]
    attempt_id: uuid.UUID
    session_id: uuid.UUID
    evidence_id: uuid.UUID
    photo_snapshot: tuple[object, ...]
    foreign_snapshot: tuple[object, ...]


@pytest.fixture
def disposable_purge_cleanup_state(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[Engine, PrivateObjectStore, _Fixture]]:
    base_settings = Settings.from_env()
    database_name = f"task109_{uuid.uuid4().hex}"
    database_url = make_url(base_settings.database_url).set(database=database_name)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {database_name}"))
    monkeypatch.setenv(
        "DATABASE_URL", database_url.render_as_string(hide_password=False)
    )
    settings = Settings.from_env()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    object_store = PrivateObjectStore(settings)
    fixture: _Fixture | None = None

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        ensure_bucket(settings)
        fixture = _create_fixture(engine, object_store)
        yield engine, object_store, fixture
    finally:
        if fixture is not None:
            _delete_prefixed_objects(object_store, prefix=f"task109/{fixture.marker}/")
            for revision_id in fixture.revision_ids:
                _delete_prefixed_objects(
                    object_store,
                    prefix=f"private/derivatives/{fixture.photo_id}/{revision_id}/",
                )
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)"))
        admin_engine.dispose()


def _create_fixture(engine: Engine, object_store: PrivateObjectStore) -> _Fixture:
    marker = uuid.uuid4().hex
    original_key = f"task109/{marker}/original.jpg"
    now = datetime(2026, 9, 5, 0, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        first_revision = _publish_revision(session, marker=marker, suffix="first")
        second_revision = _publish_revision(session, marker=marker, suffix="second")
        target = IngestTargetRepository(session).configure_spa(
            name=f"task109-{marker}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=first_revision,
        )
        photo = Photo(
            spa_id=target.spa_id,
            visit_date=date(2026, 9, 5),
            captured_at=now,
            captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
            admission_pipeline_revision_id=first_revision,
            uploader_id=uuid.uuid4(),
            checksum_sha256=hashlib.sha256(marker.encode()).digest(),
            original_object_key=original_key,
            original_byte_size=101,
            width=20,
            height=12,
            is_active=False,
        )
        session.add(photo)
        session.flush()
        derivative_keys = _add_processing_rows(
            session,
            photo_id=photo.id,
            revision_ids=(first_revision, second_revision),
            marker=marker,
            now=now,
        )
        attempt = _attempt(now=now)
        promo_session = _promo_session(attempt=attempt, photo_id=photo.id, now=now)
        evidence = DiagnosticEvidence(
            attempt_id=attempt.id,
            completeness="complete",
            gap_reason=None,
            issue_tags=["task109"],
            ordinary_manifest={"marker": marker},
            finalized_at=now,
        )
        session.add_all((attempt, promo_session, evidence))
        session.commit()
        session.refresh(photo)
        session.refresh(evidence)
        fixture = _Fixture(
            marker=marker,
            photo_id=photo.id,
            spa_id=target.spa_id,
            revision_ids=(first_revision, second_revision),
            original_key=original_key,
            derivative_keys=derivative_keys,
            attempt_id=attempt.id,
            session_id=promo_session.id,
            evidence_id=evidence.id,
            photo_snapshot=_photo_snapshot(photo),
            foreign_snapshot=_foreign_snapshot(
                session,
                attempt_id=attempt.id,
                session_id=promo_session.id,
                evidence_id=evidence.id,
                spa_id=target.spa_id,
            ),
        )
    object_store.put(key=original_key, body=b"task109-original")
    for key in fixture.derivative_keys:
        object_store.put(key=key, body=f"task109-{key}".encode())
    return fixture


def _publish_revision(session: Session, *, marker: str, suffix: str) -> uuid.UUID:
    return PipelineRevisionRepository(session).publish_eligible(
        pipeline_code=PipelineCode.OPENCV_SFACE,
        detector_id=f"task109-detector-{suffix}",
        detector_version="v1",
        recognizer_id=f"task109-recognizer-{suffix}",
        recognizer_version="v1",
        weights_sha256=hashlib.sha256(f"{marker}-{suffix}".encode()).hexdigest(),
        preprocessing_version="task109-preprocessing-v1",
        alignment_version="task109-alignment-v1",
        normalization_version="task109-normalization-v1",
        embedding_dimension=3,
        validated_at=datetime(2026, 9, 5, 0, 0, tzinfo=timezone.utc),
    ).id


def _add_processing_rows(
    session: Session,
    *,
    photo_id: uuid.UUID,
    revision_ids: tuple[uuid.UUID, uuid.UUID],
    marker: str,
    now: datetime,
) -> tuple[str, ...]:
    keys: list[str] = []
    for index, revision_id in enumerate(revision_ids):
        preview_key = f"private/derivatives/{photo_id}/{revision_id}/preview.jpg"
        thumbnail_key = f"private/derivatives/{photo_id}/{revision_id}/thumbnail.jpg"
        keys.extend((preview_key, thumbnail_key))
        session.add(
            PhotoPipelineState(
                photo_id=photo_id,
                pipeline_revision_id=revision_id,
                status="ready",
                attempt_count=index + 1,
                status_changed_at=now,
                searchable_at=now,
                preview_object_key=preview_key,
                thumbnail_object_key=thumbnail_key,
            )
        )
        session.add(
            PhotoFace(
                photo_id=photo_id,
                pipeline_revision_id=revision_id,
                face_index=0,
                bbox_x=1.0,
                bbox_y=1.0,
                bbox_w=2.0,
                bbox_h=2.0,
                landmarks_json=[[1.0, 1.0]] * 5,
                detection_confidence=0.9,
                embedding=[1.0, 0.0, 0.0],
            )
        )
    session.flush()
    return tuple(keys)


def _attempt(*, now: datetime) -> PromoAttempt:
    return PromoAttempt(
        id=uuid.uuid4(),
        spa_id=uuid.uuid4(),
        client_attempt_id=uuid.uuid4(),
        trigger_source="test",
        client_release="task109",
        detector_id="task109-detector",
        model_version="v1",
        jpeg_quality=80,
        camera_device_id="task109-camera",
        reference_series_ready_at=now,
        local_detection_completed_ms=1,
        request_started_ms=2,
        proposal_count=1,
        settings_revision=1,
        visit_date=None,
        pipeline_revision_id=uuid.uuid4(),
        pipeline_code="opencv_sface",
        query_source="reference",
        release_id="task109",
        threshold=0.7,
        quality_settings={"version": 1},
        deadline_ms=3_000,
        created_at=now,
        updated_at=now,
    )


def _promo_session(*, attempt: PromoAttempt, photo_id: uuid.UUID, now: datetime) -> PromoSession:
    photos = [photo_id, uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    return PromoSession(
        id=uuid.uuid4(),
        attempt_id=attempt.id,
        spa_id=attempt.spa_id,
        visit_date=None,
        session_result_photo_ids=photos,
        teaser_photo_ids=photos,
        n=4,
        qr_ticket_hash_sha256=hashlib.sha256(b"task109-ticket").digest(),
        qr_issued_at=now,
        qr_first_open_expires_at=now.replace(hour=1),
        created_at=now,
    )


def _photo_snapshot(photo: Photo) -> tuple[object, ...]:
    return (
        photo.id,
        photo.spa_id,
        photo.admission_pipeline_revision_id,
        photo.original_object_key,
        photo.is_active,
        photo.accepted_at,
    )


def _foreign_snapshot(
    session: Session,
    *,
    attempt_id: uuid.UUID,
    session_id: uuid.UUID,
    evidence_id: uuid.UUID,
    spa_id: uuid.UUID,
) -> tuple[object, ...]:
    attempt = session.get(PromoAttempt, attempt_id)
    promo_session = session.get(PromoSession, session_id)
    evidence = session.get(DiagnosticEvidence, evidence_id)
    spa = session.get(Spa, spa_id)
    assert attempt is not None and promo_session is not None and evidence is not None
    assert spa is not None
    return (
        attempt.id,
        attempt.processing_status,
        promo_session.id,
        tuple(promo_session.session_result_photo_ids),
        tuple(promo_session.teaser_photo_ids),
        promo_session.n,
        evidence.id,
        evidence.completeness,
        evidence.ordinary_manifest,
        spa.id,
        spa.serving_pipeline_revision_id,
        spa.settings_revision,
    )


def _assert_retained_state(
    engine: Engine, fixture: _Fixture
) -> None:
    with Session(engine) as session:
        photo = session.get(Photo, fixture.photo_id)
        assert photo is not None
        assert _photo_snapshot(photo) == fixture.photo_snapshot
        assert _foreign_snapshot(
            session,
            attempt_id=fixture.attempt_id,
            session_id=fixture.session_id,
            evidence_id=fixture.evidence_id,
            spa_id=fixture.spa_id,
        ) == fixture.foreign_snapshot


def _delete_prefixed_objects(object_store: PrivateObjectStore, *, prefix: str) -> None:
    for key in object_store.list_keys(prefix=prefix):
        object_store.delete(key=key)
    assert object_store.list_keys(prefix=prefix) == set()


def test_processing_cleanup_is_complete_idempotent_and_ownership_safe(
    disposable_purge_cleanup_state: tuple[Engine, PrivateObjectStore, _Fixture],
) -> None:
    engine, object_store, fixture = disposable_purge_cleanup_state

    with Session(engine) as session:
        result = ProcessingPurgeCleanup(session, object_store).cleanup(
            photo_id=fixture.photo_id
        )
        assert result.photo_id == fixture.photo_id
        assert result.derivative_object_keys == tuple(sorted(fixture.derivative_keys))
        assert (result.deleted_face_count, result.deleted_state_count) == (2, 2)
        session.rollback()

    assert all(
        key not in object_store.list_keys(prefix=key)
        for key in fixture.derivative_keys
    )
    _assert_retained_state(engine, fixture)
    with Session(engine) as session:
        assert session.scalars(
            select(PhotoPipelineState).where(PhotoPipelineState.photo_id == fixture.photo_id)
        ).all()
        assert session.scalars(
            select(PhotoFace).where(PhotoFace.photo_id == fixture.photo_id)
        ).all()

    with Session(engine) as session:
        result = ProcessingPurgeCleanup(session, object_store).cleanup(
            photo_id=fixture.photo_id
        )
        assert result.derivative_object_keys == tuple(sorted(fixture.derivative_keys))
        assert (result.deleted_face_count, result.deleted_state_count) == (2, 2)
        session.commit()

    _assert_retained_state(engine, fixture)
    assert object_store.read(key=fixture.original_key) == b"task109-original"
    assert all(
        key not in object_store.list_keys(prefix=key)
        for key in fixture.derivative_keys
    )
    with Session(engine) as session:
        assert not session.scalars(
            select(PhotoPipelineState).where(PhotoPipelineState.photo_id == fixture.photo_id)
        ).all()
        assert not session.scalars(
            select(PhotoFace).where(PhotoFace.photo_id == fixture.photo_id)
        ).all()
        repeated = ProcessingPurgeCleanup(session, object_store).cleanup(
            photo_id=fixture.photo_id
        )
        assert repeated.derivative_object_keys == ()
        assert (repeated.deleted_face_count, repeated.deleted_state_count) == (0, 0)
        session.commit()

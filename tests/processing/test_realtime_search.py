from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import uuid

import cv2
import numpy as np
import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, make_url
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing import (
    ExactCompatibleSearchRepository,
    PipelineCode,
    PipelineRevisionRepository,
    RealtimeSearchService,
)
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace
from face_moment.processing.reference_query import (
    PreparedReferenceQuery,
    ReferenceOccurrence,
    ReferenceQualityObservation,
)
from face_moment.processing.revisions import EligiblePipelineRevision
from face_moment.serving_control import QuerySource
from face_moment.serving_control.ingest_target import IngestTargetRepository
from face_moment.serving_control.realtime_context import RealtimeContext
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@dataclass(frozen=True, slots=True)
class _Fixture:
    engine: Engine
    object_store: PrivateObjectStore
    prefix: str
    spa_id: uuid.UUID
    other_spa_id: uuid.UUID
    revision: EligiblePipelineRevision
    other_revision: EligiblePipelineRevision
    eligible_photo_id: uuid.UUID
    second_photo_id: uuid.UUID


class _SelectionEngine:
    def __init__(
        self,
        *,
        revision_id: uuid.UUID,
        scores: Mapping[int, float],
        embeddings: Mapping[int, tuple[float, ...]],
    ) -> None:
        self.revision_id = revision_id
        self.scores = scores
        self.embeddings = embeddings
        self.inspect_calls: list[int] = []
        self.prepare_calls: list[int] = []

    def inspect_reference_crop(
        self,
        crop: np.ndarray,
        quality_settings: Mapping[str, object],
    ) -> ReferenceQualityObservation:
        del quality_settings
        index = int(crop[0, 0, 0])
        self.inspect_calls.append(index)
        score = self.scores[index]
        return ReferenceQualityObservation(
            reference_quality_score=score,
            native_face_count=1 if score > 0 else 0,
            gate_observations=(("fixture_quality", score),),
        )

    def prepare_reference_query(
        self, crop: np.ndarray
    ) -> PreparedReferenceQuery | None:
        index = int(crop[0, 0, 0])
        self.prepare_calls.append(index)
        return PreparedReferenceQuery(
            pipeline_revision_id=self.revision_id,
            embedding=np.asarray(self.embeddings[index], dtype=np.float32),
        )


class _RecordingObjectStore:
    def __init__(self, delegate: PrivateObjectStore) -> None:
        self.delegate = delegate
        self.read_calls: list[str] = []

    def read(self, *, key: str) -> bytes:
        self.read_calls.append(key)
        return self.delegate.read(key=key)


@pytest.fixture
def disposable_realtime_search(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_Fixture]:
    base_settings = Settings.from_env()
    database_name = f"task070_{uuid.uuid4().hex}"
    database_url = make_url(base_settings.database_url).set(database=database_name)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {database_name}")
    monkeypatch.setenv(
        "DATABASE_URL", database_url.render_as_string(hide_password=False)
    )
    settings = Settings.from_env()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    object_store = PrivateObjectStore(settings)
    prefix = f"task070/{uuid.uuid4().hex}/"
    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        ensure_bucket(settings)
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime(2026, 8, 22, 9, tzinfo=timezone.utc),
                **PIPELINE_COMPATIBILITY,
            )
            other_revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
                validated_at=datetime(2026, 8, 22, 9, tzinfo=timezone.utc),
                **PIPELINE_COMPATIBILITY,
            )
            target = IngestTargetRepository(session).configure_spa(
                name=f"task070-target-{uuid.uuid4().hex}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            other_spa = IngestTargetRepository(session).configure_spa(
                name=f"task070-other-{uuid.uuid4().hex}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            eligible_photo_id, eligible_key = _add_photo(
                session,
                marker="eligible",
                spa_id=target.spa_id,
                revision_id=revision.id,
                embedding=_embedding(1.0, 0.0),
                prefix=prefix,
                add_second_face=True,
            )
            second_photo_id, second_key = _add_photo(
                session,
                marker="second",
                spa_id=target.spa_id,
                revision_id=revision.id,
                embedding=_embedding(0.8, 0.6),
                prefix=prefix,
            )
            _add_photo(
                session,
                marker="inactive",
                spa_id=target.spa_id,
                revision_id=revision.id,
                embedding=_embedding(1.0, 0.0),
                prefix=prefix,
                is_active=False,
            )
            _add_photo(
                session,
                marker="other-spa",
                spa_id=other_spa.spa_id,
                revision_id=revision.id,
                embedding=_embedding(1.0, 0.0),
                prefix=prefix,
            )
            _add_photo(
                session,
                marker="other-date",
                spa_id=target.spa_id,
                revision_id=revision.id,
                embedding=_embedding(1.0, 0.0),
                prefix=prefix,
                visit_date=date(2026, 8, 21),
            )
            _add_photo(
                session,
                marker="other-revision",
                spa_id=target.spa_id,
                revision_id=other_revision.id,
                embedding=_embedding(1.0, 0.0),
                prefix=prefix,
            )
            _add_photo(
                session,
                marker="not-ready",
                spa_id=target.spa_id,
                revision_id=revision.id,
                embedding=_embedding(1.0, 0.0),
                prefix=prefix,
                state_status="processing",
            )
            _add_photo(
                session,
                marker="missing-preview",
                spa_id=target.spa_id,
                revision_id=revision.id,
                embedding=_embedding(1.0, 0.0),
                prefix=prefix,
                has_preview=False,
            )
            session.commit()
        object_store.put(key=eligible_key, body=_jpeg(20))
        object_store.put(key=second_key, body=_jpeg(60))
        yield _Fixture(
            engine=engine,
            object_store=object_store,
            prefix=prefix,
            spa_id=target.spa_id,
            other_spa_id=other_spa.spa_id,
            revision=revision,
            other_revision=other_revision,
            eligible_photo_id=eligible_photo_id,
            second_photo_id=second_photo_id,
        )
    finally:
        for key in object_store.list_keys(prefix=prefix):
            object_store.delete(key=key)
        assert object_store.list_keys(prefix=prefix) == set()
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)"
            )
        admin_engine.dispose()


def _jpeg(value: int) -> bytes:
    image = np.full((32, 32, 3), value, dtype=np.uint8)
    image[::2, ::2] = (value + 30) % 255
    encoded, payload = cv2.imencode(".jpg", image)
    assert encoded
    return bytes(payload)


def _embedding(first: float, second: float) -> tuple[float, ...]:
    return (first, second) + (0.0,) * 126


def _add_photo(
    session: Session,
    *,
    marker: str,
    spa_id: uuid.UUID,
    revision_id: uuid.UUID,
    embedding: tuple[float, ...],
    prefix: str,
    visit_date: date = date(2026, 8, 22),
    is_active: bool = True,
    state_status: str = "ready",
    has_preview: bool = True,
    add_second_face: bool = False,
) -> tuple[uuid.UUID, str]:
    key = f"{prefix}{marker}.jpg"
    photo = Photo(
        spa_id=spa_id,
        visit_date=visit_date,
        captured_at=datetime(2026, 8, 22, 9, tzinfo=timezone.utc),
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        admission_pipeline_revision_id=revision_id,
        uploader_id=uuid.uuid4(),
        checksum_sha256=hashlib.sha256(marker.encode()).digest(),
        original_object_key=f"{prefix}{marker}-original.jpg",
        original_byte_size=123,
        width=32,
        height=32,
        is_active=is_active,
    )
    session.add(photo)
    session.flush()
    state = PhotoPipelineState(
        photo_id=photo.id,
        pipeline_revision_id=revision_id,
        status=state_status,
        preview_object_key=key if has_preview else None,
        thumbnail_object_key=key if has_preview else None,
    )
    session.add(state)
    session.add(
        PhotoFace(
            photo_id=photo.id,
            pipeline_revision_id=revision_id,
            face_index=0,
            bbox_x=1.0,
            bbox_y=1.0,
            bbox_w=10.0,
            bbox_h=10.0,
            landmarks_json=[[1.0, 1.0]] * 5,
            detection_confidence=0.9,
            embedding=list(embedding),
        )
    )
    if add_second_face:
        session.add(
            PhotoFace(
                photo_id=photo.id,
                pipeline_revision_id=revision_id,
                face_index=1,
                bbox_x=1.0,
                bbox_y=1.0,
                bbox_w=10.0,
                bbox_h=10.0,
                landmarks_json=[[1.0, 1.0]] * 5,
                detection_confidence=0.9,
                embedding=list(_embedding(0.0, 1.0)),
            )
        )
    session.flush()
    return photo.id, key


def _context(fixture: _Fixture, *, threshold: float = 0.75) -> RealtimeContext:
    return RealtimeContext(
        settings_revision=1,
        spa_id=fixture.spa_id,
        visit_date=date(2026, 8, 22),
        pipeline_revision_id=fixture.revision.id,
        pipeline_code=PipelineCode.OPENCV_SFACE,
        query_source=QuerySource.REFERENCE,
        reference_threshold=threshold,
        min_query_face_quality=0.75,
        quality_settings={"version": 1},
        calibration_id=None,
        release_id="task070-test",
    )


def _occurrences(count: int) -> tuple[ReferenceOccurrence, ...]:
    return tuple(
        ReferenceOccurrence(
            occurrence_index=index,
            crop=np.full((2, 2, 3), index, dtype=np.uint8),
        )
        for index in range(count)
    )


def test_exact_search_filters_scope_groups_faces_and_orders_ties(
    disposable_realtime_search: _Fixture,
) -> None:
    fixture = disposable_realtime_search
    with Session(fixture.engine) as session:
        matches = ExactCompatibleSearchRepository(session).search(
            spa_id=fixture.spa_id,
            visit_date=date(2026, 8, 22),
            pipeline_revision_id=fixture.revision.id,
            query_embedding=_embedding(1.0, 0.0),
            reference_threshold=0.75,
        )

    assert [match.photo_id for match in matches] == [
        fixture.eligible_photo_id,
        fixture.second_photo_id,
    ]
    assert [match.cosine_similarity for match in matches] == pytest.approx(
        [1.0, 0.8]
    )
    assert all(match.pipeline_revision_id == fixture.revision.id for match in matches)
    assert all(match.preview_object_key.startswith(fixture.prefix) for match in matches)


def test_service_searches_accepted_detections_independently_and_caches_phash(
    disposable_realtime_search: _Fixture,
) -> None:
    fixture = disposable_realtime_search
    engine = _SelectionEngine(
        revision_id=fixture.revision.id,
        scores={0: 0.95, 1: 0.90, 2: 0.40},
        embeddings={
            0: _embedding(1.0, 0.0),
            1: _embedding(1.0, 0.0),
            2: _embedding(0.0, 1.0),
        },
    )
    with Session(fixture.engine) as session:
        repository = ExactCompatibleSearchRepository(session)
        object_store = _RecordingObjectStore(fixture.object_store)
        result = RealtimeSearchService(repository, object_store).search(
            context=_context(fixture),
            engine=engine,
            occurrences=_occurrences(3),
        )

    assert engine.inspect_calls == [0, 1, 2]
    assert engine.prepare_calls == [0, 1]
    assert [item.occurrence_index for item in result.detections] == [0, 1, 2]
    assert [len(item.matches) for item in result.detections] == [2, 2, 0]
    assert result.detections[2].quality_gate_passed is False
    assert result.detections[2].rejection_reason == "low_quality"
    assert result.detections[0].matches[0].phash64 == result.detections[1].matches[0].phash64
    assert len(object_store.read_calls) == 2


def test_phash_is_deterministic_and_rejects_invalid_preview() -> None:
    from face_moment.processing.realtime_search import opencv_phash64_v1

    payload = _jpeg(120)
    assert opencv_phash64_v1(payload) == opencv_phash64_v1(payload)
    assert 0 <= opencv_phash64_v1(payload) < 2**64
    with pytest.raises(ValueError, match="cannot be decoded"):
        opencv_phash64_v1(b"not-a-jpeg")

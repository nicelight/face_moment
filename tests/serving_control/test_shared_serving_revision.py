"""Shared revision invariants against real, disposable PostgreSQL."""
from datetime import UTC, datetime
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.serving_control.ingest_target import (
    CommittedServingTargetUnavailableError, IngestTargetRepository, Spa,
)
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY
from tests.serving_control.test_serving_revision_switch import _add_photo


def test_shared_revision_creation_conflict_global_switch_and_other_venue_guard():
    with disposable_postgresql_engine('shared_revision') as engine:
        with Session(engine) as session:
            repo = IngestTargetRepository(session)
            with pytest.raises(CommittedServingTargetUnavailableError):
                repo.resolve_committed_serving_revision()
            revisions = [PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE, validated_at=datetime.now(UTC),
                **PIPELINE_COMPATIBILITY) for _ in range(2)]
            a, b = [revision.id for revision in revisions]
            venues = [repo.configure_spa(timezone=zone, serving_pipeline_revision_id=a)
                      for zone in ('UTC', 'Asia/Dushanbe')]
            first, second = [venue.spa_id for venue in venues]
            assert repo.resolve_committed_serving_revision().id == a
            with pytest.raises(CommittedServingTargetUnavailableError):
                repo.configure_spa(timezone='UTC', serving_pipeline_revision_id=b)
            photo_id = _add_photo(session, spa_id=second, revision_id=a, marker=uuid.uuid4().hex)
            session.commit()
        with Session(engine) as session:
            result = IngestTargetRepository(session).switch_serving_revision(
                spa_id=first, target_pipeline_revision_id=b)
            assert result.reason == 'current_revision_has_active_processing'
            assert set(session.scalars(select(Spa.serving_pipeline_revision_id))) == {a}
            session.get(PhotoPipelineState, (photo_id, a)).status = 'no_faces'
            session.commit()
        with Session(engine) as session:
            result = IngestTargetRepository(session).switch_serving_revision(
                spa_id=first, target_pipeline_revision_id=b)
            assert result.outcome == 'committed'
        with Session(engine) as session:
            assert set(session.scalars(select(Spa.serving_pipeline_revision_id))) == {b}
            assert [session.get(Spa, v.spa_id).timezone for v in venues] == ['UTC', 'Asia/Dushanbe']
            assert session.get(PhotoPipelineState, (photo_id, a)).status == 'no_faces'
            # An unsupported direct write must not cause arbitrary model selection.
            session.get(Spa, second).serving_pipeline_revision_id = a
            session.commit()
        with Session(engine) as session:
            repo = IngestTargetRepository(session)
            with pytest.raises(CommittedServingTargetUnavailableError):
                repo.resolve_committed_serving_revision()
            with pytest.raises(CommittedServingTargetUnavailableError):
                repo.switch_serving_revision(spa_id=first, target_pipeline_revision_id=a)
            assert set(session.scalars(select(Spa.serving_pipeline_revision_id))) == {a, b}


def test_creation_serializes_with_global_switch_including_new_venue():
    with disposable_postgresql_engine('shared_revision_race') as engine:
        with Session(engine) as session:
            a, b = [PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE, validated_at=datetime.now(UTC),
                **PIPELINE_COMPATIBILITY).id for _ in range(2)]
            first = IngestTargetRepository(session).configure_spa(timezone='UTC', serving_pipeline_revision_id=a)
            session.commit()
        started = Event()
        def switch():
            with Session(engine) as session:
                started.set()
                return IngestTargetRepository(session).switch_serving_revision(
                    spa_id=first.spa_id, target_pipeline_revision_id=b)
        with ThreadPoolExecutor(max_workers=1) as pool, Session(engine) as session:
            second = IngestTargetRepository(session).configure_spa(timezone='UTC', serving_pipeline_revision_id=a)
            future = pool.submit(switch)
            try:
                assert started.wait(5)
                assert not future.done()
            finally:
                session.commit()
            assert future.result(timeout=10).outcome == 'committed'
        with Session(engine) as session:
            assert session.get(Spa, second.spa_id).serving_pipeline_revision_id == b
            assert set(session.scalars(select(Spa.serving_pipeline_revision_id))) == {b}
            with pytest.raises(CommittedServingTargetUnavailableError):
                IngestTargetRepository(session).configure_spa(timezone='UTC', serving_pipeline_revision_id=a)

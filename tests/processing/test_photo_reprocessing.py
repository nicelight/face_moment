from datetime import date, datetime, timezone
import uuid

from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.processing import InitialPendingRepository, PipelineCode, PipelineRevisionRepository
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import ExactCompatibleSearchRepository, PhotoFace
from face_moment.serving_control import IngestTargetRepository
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY
from tests.processing.test_searchable_projection import _add_state
from tests.processing.test_initial_pending import _add_photo


def test_reprocessed_ready_photo_search_preserves_admission_revision() -> None:
    with disposable_postgresql_engine('task118_search') as engine:
        with Session(engine) as session:
            revisions = [PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime.now(timezone.utc), **PIPELINE_COMPATIBILITY,
            ) for _ in range(2)]
            old, new = revisions
            target = IngestTargetRepository(session).configure_spa(
                name='reprocess-search', timezone='Asia/Dushanbe',
                serving_pipeline_revision_id=old.id,
            )
            old_state = _add_state(session, marker=uuid.uuid4().hex,
                spa_id=target.spa_id, pipeline_revision_id=old.id,
                status='no_faces', has_face=False)
            new_state = InitialPendingRepository(session).create_initial_pending(
                photo_id=old_state.photo_id, pipeline_revision_id=new.id)
            new_state.status = 'ready'
            new_state.preview_object_key = 'new/preview.jpg'
            new_state.thumbnail_object_key = 'new/thumbnail.jpg'
            session.add(PhotoFace(photo_id=old_state.photo_id,
                pipeline_revision_id=new.id, face_index=0, bbox_x=1, bbox_y=1,
                bbox_w=4, bbox_h=4, landmarks_json=[[1., 1.]]*5,
                detection_confidence=.9, embedding=[1.] + [0.]*127))
            photo_id, old_id, new_id, spa_id = old_state.photo_id, old.id, new.id, target.spa_id
            session.commit()
        with Session(engine) as session:
            matches = ExactCompatibleSearchRepository(session).search(
                spa_id=spa_id, visit_date=date(2026, 8, 13), pipeline_revision_id=new_id,
                query_embedding=[1.] + [0.]*127, reference_threshold=.6)
            assert [match.photo_id for match in matches] == [photo_id]
            assert session.get(Photo, photo_id).admission_pipeline_revision_id == old_id
            assert session.get(PhotoPipelineState, (photo_id, old_id)).status == 'no_faces'


def test_ensure_revision_pending_is_transactional_and_preserves_every_existing_status() -> None:
    with disposable_postgresql_engine('task118_pending') as engine:
        with Session(engine) as session:
            photo_id, old_id, _ = _add_photo(session, marker=uuid.uuid4().hex)
            new = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime.now(timezone.utc), **PIPELINE_COMPATIBILITY)
            new_id = new.id
            session.commit()
        with Session(engine) as session:
            InitialPendingRepository(session).ensure_revision_pending(photo_id=photo_id, pipeline_revision_id=new_id)
            session.rollback()
        with Session(engine) as session:
            assert session.get(PhotoPipelineState, (photo_id, new_id)) is None
            state = InitialPendingRepository(session).ensure_revision_pending(photo_id=photo_id, pipeline_revision_id=new_id)
            assert state.status == 'pending'
            session.commit()
        for status in ('pending', 'processing', 'ready', 'no_faces', 'failed'):
            with Session(engine) as session:
                state = session.get(PhotoPipelineState, (photo_id, new_id))
                state.status = status
                state.attempt_count = 2
                state.last_error = 'retained diagnostic'
                state.preview_object_key = 'retained/preview'
                session.commit()
            with Session(engine) as session:
                before = session.get(PhotoPipelineState, (photo_id, new_id))
                values = tuple(getattr(before, col.name) for col in PhotoPipelineState.__table__.columns)
                state = InitialPendingRepository(session).ensure_revision_pending(photo_id=photo_id, pipeline_revision_id=new_id)
                session.commit()
                assert tuple(getattr(state, col.name) for col in PhotoPipelineState.__table__.columns) == values
                assert session.get(Photo, photo_id).admission_pipeline_revision_id == old_id


def test_local_procedure_reuses_target_after_journal_loss_and_preserves_terminals(tmp_path, monkeypatch) -> None:
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    from sqlalchemy import func, select
    from face_moment.infrastructure.settings import Settings
    from face_moment.processing.revisions import PipelineRevision
    from face_moment.serving_control.ingest_target import Spa
    from face_moment.processing.worker_claims import WorkerClaimRepository
    from face_moment.processing.worker_recovery import WorkerStartupRecoveryRepository

    spec = importlib.util.spec_from_file_location('local_preprocessing', Path('scripts/apply-local-photo-preprocessing.py'))
    procedure = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(procedure)
    # Native asset admission has separate real-model gates. Here inject only that
    # adapter boundary; publication, switch, pending and commits use real owners.
    monkeypatch.setattr(procedure, 'admit_selected_model', lambda **kwargs: SimpleNamespace(ready=True))
    with disposable_postgresql_engine('task118_rerun') as engine:
        with Session(engine) as session:
            photo_id, old_id, spa_id = _add_photo(session, marker=uuid.uuid4().hex)
            state = InitialPendingRepository(session).create_initial_pending(photo_id=photo_id, pipeline_revision_id=old_id)
            state.status = 'no_faces'
            session.commit()
        before = {'photos': {str(photo_id): {'inventory': {'spa_id': str(spa_id)}}},
                  'spas': {str(spa_id): {'serving_pipeline_revision_id': str(old_id)}}}
        procedure.apply(engine, Settings.from_env(), before, tmp_path)
        import json
        target_id = uuid.UUID(json.loads((tmp_path/'target.json').read_text())['target_revision_id'])
        with Session(engine) as session:
            worker = WorkerClaimRepository(session, bound_pipeline_revision_id=target_id)
            assert worker.claim_oldest_pending().photo_id == photo_id
            session.commit()
        with Session(engine) as session:
            worker = WorkerClaimRepository(session, bound_pipeline_revision_id=target_id)
            assert worker.record_failure(photo_id=photo_id, pipeline_revision_id=target_id).status == 'pending'
            session.commit()
        with Session(engine) as session:
            worker = WorkerClaimRepository(session, bound_pipeline_revision_id=target_id)
            assert worker.claim_oldest_pending().attempt_count == 2
            session.commit()
        # A committed claim interrupted before publication is recovered at startup.
        with Session(engine) as session:
            assert WorkerStartupRecoveryRepository(session).recover() == 1
            session.commit()
        with Session(engine) as session:
            worker = WorkerClaimRepository(session, bound_pipeline_revision_id=target_id)
            assert worker.claim_oldest_pending().attempt_count == 3
            terminal = worker.record_failure(photo_id=photo_id, pipeline_revision_id=target_id)
            assert terminal.status == 'failed'
            retained_error = terminal.last_error
            session.commit()
        # Simulate a process losing its journal after durable publication. Exact
        # compatible revision lookup recovers the same target, not another row.
        (tmp_path/'target.json').unlink()
        procedure.apply(engine, Settings.from_env(), before, tmp_path)
        procedure.apply(engine, Settings.from_env(), before, tmp_path)
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(PipelineRevision)) == 2
            assert session.scalar(select(func.count()).select_from(PhotoPipelineState)) == 2
            assert session.get(Spa, spa_id).serving_pipeline_revision_id == target_id
            state = session.get(PhotoPipelineState, (photo_id, target_id))
            assert (state.status, state.attempt_count, state.last_error) == ('failed', 3, retained_error)
            assert session.get(Photo, photo_id).admission_pipeline_revision_id == old_id
            assert session.get(PhotoPipelineState, (photo_id, old_id)).status == 'no_faces'

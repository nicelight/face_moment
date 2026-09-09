"""Apply the measured Photo revision to an explicitly snapshotted local inventory.

Run in the authorized workstation Compose network with current source and an
/evidence mount. snapshot --expected-photos N is read-only; apply reuses the
journaled target, invokes existing owner APIs, and leaves work to the ordinary
worker. check is read-only. Never use against a remote/production database.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.initial_pending import InitialPendingRepository, PhotoPipelineState
from face_moment.processing.model_admission import admit_selected_model
from face_moment.processing.persistence import ExactCompatibleSearchRepository, PhotoFace
from face_moment.processing.revisions import PipelineRevision, PipelineRevisionRepository
from face_moment.processing.searchable_projection import SearchableProjectionRepository
from face_moment.serving_control import IngestTargetRepository
from face_moment.serving_control.ingest_target import Spa

VERSION = 'opencv-photo-640-v2'


def encode(value):
    if isinstance(value, bytes):
        return value.hex()
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def row(value):
    return {col.name: getattr(value, col.name) for col in value.__table__.columns}


def plain(value):
    return json.loads(json.dumps(value, default=encode, sort_keys=True))


def digest(value):
    return hashlib.sha256(json.dumps(value, default=encode, sort_keys=True).encode()).hexdigest()


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, default=encode, indent=2, sort_keys=True)+'\n')
    temporary.replace(path)


def snapshot(engine, settings, ids=None):
    store = PrivateObjectStore(settings)
    with Session(engine) as session:
        photos = session.scalars(select(Photo).order_by(Photo.id)).all()
        if ids is not None:
            photos = [p for p in photos if str(p.id) in ids]
            if len(photos) != len(ids):
                raise RuntimeError('Selected Photo population changed')
        result = {'photos': {}, 'revisions': {}, 'spas': {}}
        for photo in photos:
            original = store.read(key=photo.original_object_key)
            original_hash = hashlib.sha256(original).hexdigest()
            if original_hash != photo.checksum_sha256.hex():
                raise RuntimeError('Original checksum mismatch: '+str(photo.id))
            states = session.scalars(select(PhotoPipelineState).where(PhotoPipelineState.photo_id == photo.id)).all()
            outcomes = {}
            for state in states:
                faces = session.scalars(select(PhotoFace).where(
                    PhotoFace.photo_id == photo.id,
                    PhotoFace.pipeline_revision_id == state.pipeline_revision_id,
                ).order_by(PhotoFace.face_index)).all()
                derivatives = {}
                for key in (state.preview_object_key, state.thumbnail_object_key):
                    if key:
                        derivatives[key] = hashlib.sha256(store.read(key=key)).hexdigest()
                outcomes[str(state.pipeline_revision_id)] = {
                    'state': plain(row(state)), 'face_count': len(faces),
                    'faces_sha256': digest([row(f) for f in faces]), 'derivatives_sha256': derivatives,
                }
            result['photos'][str(photo.id)] = {'inventory': plain(row(photo)),
                'original_sha256': original_hash, 'outcomes': outcomes}
        for revision in session.scalars(select(PipelineRevision).order_by(PipelineRevision.id)):
            result['revisions'][str(revision.id)] = plain(row(revision))
        for spa in session.scalars(select(Spa).order_by(Spa.id)):
            result['spas'][str(spa.id)] = plain(row(spa))
        result['configured_preprocessing'] = settings.sface_preprocessing_version
        return result


def assert_preserved(before, after):
    for id, previous in before['photos'].items():
        current = after['photos'][id]
        if previous['inventory'] != current['inventory'] or previous['original_sha256'] != current['original_sha256']:
            raise RuntimeError('Inventory/original changed: '+id)
        for revision_id, outcome in previous['outcomes'].items():
            if current['outcomes'].get(revision_id) != outcome:
                raise RuntimeError('Historical outcome changed: '+id)
    for id, previous in before['revisions'].items():
        if after['revisions'].get(id) != previous:
            raise RuntimeError('Historical revision changed: '+id)


def apply(engine, settings, before, directory):
    journal_path = directory/'target.json'
    selected_settings = replace(settings, sface_preprocessing_version=VERSION)
    spa_ids = {p['inventory']['spa_id'] for p in before['photos'].values()}
    if len(spa_ids) != 1:
        raise RuntimeError('Expected one local SPA')
    spa_id = uuid.UUID(next(iter(spa_ids)))
    old_id = uuid.UUID(before['spas'][str(spa_id)]['serving_pipeline_revision_id'])
    with Session(engine) as session:
        revisions = PipelineRevisionRepository(session)
        old = revisions.resolve_eligible(old_id)
        candidate = replace(old, id=uuid.uuid4(), preprocessing_version=VERSION)
        adapter = admit_selected_model(revision=candidate, settings=selected_settings)
        assert adapter.ready
        compatibility = {k: v for k, v in asdict(candidate).items() if k not in ('id', 'created_at', 'validated_at')}
        if journal_path.exists():
            target_id = uuid.UUID(json.loads(journal_path.read_text())['target_revision_id'])
            target = revisions.resolve_eligible(target_id)
            if any(getattr(target, k) != v for k, v in compatibility.items()):
                raise RuntimeError('Journal target compatibility mismatch')
        else:
            matches = session.scalars(select(PipelineRevision).where(
                *(getattr(PipelineRevision, k) == v for k, v in compatibility.items()),
                PipelineRevision.validated_at.is_not(None),
            )).all()
            if len(matches) > 1:
                raise RuntimeError('Ambiguous matching target revisions')
            if matches:
                target = revisions.resolve_eligible(matches[0].id)
            else:
                target = revisions.publish_eligible(validated_at=datetime.now(timezone.utc), **compatibility)
                session.commit()
            target_id = target.id
            save(journal_path, {'target_revision_id': str(target_id), 'old_revision_id': str(old_id),
                'spa_id': str(spa_id), 'preprocessing_version': VERSION})
        admit_selected_model(revision=target, settings=selected_settings)
    with Session(engine) as session:
        switch = IngestTargetRepository(session).switch_serving_revision(
            spa_id=spa_id, target_pipeline_revision_id=target_id)
        if switch.committed_pipeline_revision_id != target_id:
            raise RuntimeError('Guarded switch rejected: '+switch.reason)
    with Session(engine) as session:
        repo = InitialPendingRepository(session)
        for photo_id in before['photos']:
            repo.ensure_revision_pending(photo_id=uuid.UUID(photo_id), pipeline_revision_id=target_id)
        session.commit()
    print(json.dumps({'target_revision_id': str(target_id), 'switch': switch.reason, 'selected_photos': len(before['photos'])}))


def check(engine, settings, before, directory):
    target_id = uuid.UUID(json.loads((directory/'target.json').read_text())['target_revision_id'])
    after = snapshot(engine, settings, before['photos'])
    assert_preserved(before, after)
    with Session(engine) as session:
        revision = PipelineRevisionRepository(session).resolve_eligible(target_id)
        admit_selected_model(revision=revision, settings=settings)
        search_results = {}
        for id in before['photos']:
            photo_id = uuid.UUID(id)
            state = session.get(PhotoPipelineState, (photo_id, target_id))
            if state is None or state.status not in ('ready', 'no_faces', 'failed'):
                raise RuntimeError('Photo not terminal: '+id)
            projection = SearchableProjectionRepository(session).resolve(photo_id=photo_id, pipeline_revision_id=target_id)
            if state.status == 'ready':
                if projection is None or not projection.searchable:
                    raise RuntimeError('Ready Photo is not searchable: '+id)
                face = session.scalar(select(PhotoFace).where(PhotoFace.photo_id == photo_id,
                    PhotoFace.pipeline_revision_id == target_id).order_by(PhotoFace.face_index))
                embedding = face.embedding
                if isinstance(embedding, str):
                    embedding = json.loads(embedding)
                photo = session.get(Photo, photo_id)
                matches = ExactCompatibleSearchRepository(session).search(spa_id=photo.spa_id,
                    visit_date=photo.visit_date, pipeline_revision_id=target_id,
                    query_embedding=embedding, reference_threshold=.6)
                if photo_id not in {m.photo_id for m in matches}:
                    raise RuntimeError('Compatible search missed ready Photo: '+id)
                search_results[id] = {'status': state.status, 'self_match': True}
            else:
                search_results[id] = {'status': state.status, 'last_error': state.last_error}
    save(directory/'after.json', after)
    save(directory/'search-proof.json', search_results)
    print(json.dumps({'preserved': True, 'target_revision_id': str(target_id), 'results': search_results}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('snapshot', 'apply', 'check'))
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--expected-photos', type=int, default=6)
    args = parser.parse_args()
    settings = Settings.from_env()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    directory = args.evidence
    directory.mkdir(exist_ok=True, parents=True)
    before_path = directory/'before.json'
    try:
        if args.action == 'snapshot':
            if before_path.exists():
                raise RuntimeError('Before snapshot already exists; preserve it')
            before = snapshot(engine, settings)
            if len(before['photos']) != args.expected_photos:
                raise RuntimeError('Unexpected local Photo population')
            save(before_path, before)
            print(json.dumps({'photos': len(before['photos']), 'preprocessing': before['configured_preprocessing'],
                'revision_count': len(before['revisions'])}))
        else:
            before = json.loads(before_path.read_text())
            assert_preserved(before, snapshot(engine, settings, before['photos']))
            if args.action == 'apply':
                apply(engine, settings, before, directory)
            else:
                check(engine, settings, before, directory)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()

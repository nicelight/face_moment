"""AC-007: actual native adapters, browser JPEG pairs and isolated PostgreSQL."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
import json
import subprocess
import uuid

import cv2
import numpy as np
import pytest
from sqlalchemy.orm import Session

from face_moment.processing.buffalo_adapter import BuffaloModelAssets, BuffaloPhotoAdapter
from face_moment.processing.sface_adapter import SFaceModelAssets, SFacePhotoAdapter
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.processing.persistence import PublicExactSearchRepository, ExactCompatibleSearchRepository
from face_moment.processing.public_selfie_search import prepare_public_selfie, search_public_selfie
from face_moment.serving_control.ingest_target import IngestTargetRepository, Spa
from face_moment.serving_control.public_search_context import read_public_search_context
from face_moment.serving_control.realtime_context import RealtimeContextRepository, RealtimeReadinessClosedError
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.processing.test_realtime_search import _add_photo

ARTIFACTS = Path('.tasks/TASK-122-T2-FT-013-W3')


def _native(session, pipeline):
    if pipeline == 'sface':
        assets = SFaceModelAssets(
            detector_path=Path('models/opencv_sface/yunet.onnx'), detector_id='yunet', detector_version='2023mar',
            recognizer_path=Path('models/opencv_sface/sface.onnx'), recognizer_id='sface', recognizer_version='2021dec',
            preprocessing_version='opencv-bgr-v1', alignment_version='aligncrop-v1', normalization_version='l2-v1')
        code, dimension, adapter = PipelineCode.OPENCV_SFACE, 128, SFacePhotoAdapter
    else:
        assets = BuffaloModelAssets(
            detector_path=Path('models/insightface_buffalo_m/scrfd.onnx'), detector_id='scrfd', detector_version='10g-bnkps',
            recognizer_path=Path('models/insightface_buffalo_m/w600k_r50.onnx'), recognizer_id='w600k_r50', recognizer_version='buffalo-m',
            preprocessing_version='insightface-bgr-v1', alignment_version='insightface-norm-crop-v1',
            normalization_version='insightface-normed-embedding-v1', embedding_dimension=512)
        code, dimension, adapter = PipelineCode.INSIGHTFACE_BUFFALO_M, 512, BuffaloPhotoAdapter
    revision = PipelineRevisionRepository(session).publish_eligible(
        pipeline_code=code, validated_at=datetime.now(UTC), weights_sha256=assets.weights_sha256(), embedding_dimension=dimension,
        **{key: getattr(assets, key) for key in ('detector_id','detector_version','recognizer_id','recognizer_version',
                                                'preprocessing_version','alignment_version','normalization_version')})
    engine = adapter.from_configured_assets(revision=revision, assets=assets)
    engine.warmup()
    return revision, engine


@pytest.fixture(scope='module', autouse=True)
def browser_jpeg_pairs():
    subprocess.run(['node', 'tests/client/encode_public_selfie_pairs.mjs', str(ARTIFACTS)], check=True)


@pytest.mark.parametrize('pipeline', ['sface', 'buffalo'])
def test_native_browser_pairs_exact_selected_scope(pipeline):
    assert all((ARTIFACTS / f'selfie-browser-{size}.jpg').is_file() for size in ('large','small')), (
        'Actual browser encoding did not produce paired JPEG artifacts')
    observations = []
    with disposable_postgresql_engine('task122_native') as db, Session(db) as session:
        revision, engine = _native(session, pipeline)
        venues = []
        settings = RealtimeContextRepository(session)
        for i in range(4):
            target = IngestTargetRepository(session).configure_spa(
                name=f'public-{i}', timezone='UTC', serving_pipeline_revision_id=revision.id)
            venues.append(target.spa_id)
            settings.provision_reference_settings(spa_id=target.spa_id, pipeline_code=revision.pipeline_code,
                reference_threshold=.4, min_query_face_quality=(.1,.2,.3,.4)[i], quality_settings={'version':1})
            # Deliberately irrelevant invalid Promo date range.
            spa = session.get(Spa, target.spa_id); spa.search_today = False
            spa.active_visit_date = None; spa.active_visit_date_to = None
        context = read_public_search_context(session, venue_ids=venues[:3], admitted_pipeline_revision_id=revision.id)
        assert context.min_query_face_quality == .3
        for invalid in ([], venues, [venues[0], venues[0]], [uuid.uuid4()]):
            with pytest.raises((ValueError, LookupError)):
                read_public_search_context(session, venue_ids=invalid, admitted_pipeline_revision_id=revision.id)
        with pytest.raises(RealtimeReadinessClosedError):
            read_public_search_context(session, venue_ids=venues[:1], admitted_pipeline_revision_id=uuid.uuid4())
        # Immutable even when owner settings are later mutated in this transaction.
        settings.get_reference_settings(spa_id=venues[0],pipeline_code=revision.pipeline_code).min_query_face_quality=.99
        assert context.venues[0].min_query_face_quality == .1
        original = cv2.imread('tests/client/fixtures/selfie-portrait-small.png')
        query = prepare_public_selfie(context=context, engine=engine, selfie=original)
        assert query.native_face_count == 1 and query.quality_gate_passed and query.query is not None
        embedding = tuple(float(v) for v in query.query.embedding)
        expected = set()
        for i, venue in enumerate(venues):
            for year in (2001,2026):
                photo_id, _ = _add_photo(session, marker=f'{i}-{year}', spa_id=venue, revision_id=revision.id,
                    embedding=embedding, prefix='task122/', visit_date=date(year,1,1), phash64=None)
                if i < 3: expected.add(photo_id)
        for marker, kwargs in (
            ('deleted', {'is_active':False}), ('pending', {'state_status':'pending'}),
            ('no_faces', {'state_status':'no_faces'}), ('no-preview', {'has_preview':False}),
        ):
            _add_photo(session, marker=marker, spa_id=venues[0], revision_id=revision.id,
                       embedding=embedding, prefix='task122/', **kwargs)
        other = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=revision.pipeline_code, validated_at=datetime.now(UTC),
            **{key:getattr(revision,key) for key in ('detector_id','detector_version','recognizer_id','recognizer_version',
                'weights_sha256','preprocessing_version','alignment_version','normalization_version','embedding_dimension')})
        _add_photo(session, marker='foreign-revision', spa_id=venues[0], revision_id=other.id, embedding=embedding,prefix='task122/')
        repository = PublicExactSearchRepository(session)
        for size in ('large','small'):
            originals = cv2.imread(f'tests/client/fixtures/selfie-portrait-{size}.png')
            compressed = cv2.imread(str(ARTIFACTS/f'selfie-browser-{size}.jpg'))
            assert max(compressed.shape[:2]) <= 960
            if size == 'small': assert originals.shape == compressed.shape
            pair = []
            for variant, image in (('original',originals),('compressed',compressed)):
                observation = prepare_public_selfie(context=context,engine=engine,selfie=image)
                prepared = observation.query
                if prepared is not None:
                    assert prepared.pipeline_revision_id == revision.id
                    assert prepared.embedding.size == revision.embedding_dimension and np.isfinite(prepared.embedding).all()
                    assert np.linalg.norm(prepared.embedding) == pytest.approx(1.,abs=1e-3)
                    matches = search_public_selfie(repository=repository,context=context,query=prepared)
                    assert {item.photo_id for item in matches} == expected
                    assert matches == search_public_selfie(repository=repository,context=context,query=prepared)
                    assert [(str(m.spa_id),m.visit_date,-m.cosine_similarity,str(m.photo_id)) for m in matches] == sorted(
                        (str(m.spa_id),m.visit_date,-m.cosine_similarity,str(m.photo_id)) for m in matches)
                    pair.append(prepared.embedding)
                else:
                    matches = ()
                    assert not observation.quality_gate_passed
                    pair.append(None)
                # No accuracy guarantee for original/compressed; record actual differences.
                if size == 'small':
                    assert observation.native_face_count == 1 and observation.quality_gate_passed
                observations.append({'pipeline':pipeline,'size':size,'variant':variant,
                    'dimensions':[image.shape[1],image.shape[0]],'revision':str(revision.id),
                    'face_count':observation.native_face_count,'confidence':observation.reference_quality_score,
                    'gate':observation.quality_gate_passed,'min_quality':context.min_query_face_quality,
                    'rejection_reason':observation.rejection_reason,
                    'embedding_valid':prepared is not None,
                    'embedding_dimension':None if prepared is None else int(prepared.embedding.size),
                    'matches':[{'id':str(m.photo_id),'venue':str(m.spa_id),'date':str(m.visit_date),'similarity':m.cosine_similarity} for m in matches]})
            observations[-1]['original_compressed_embedding_cosine'] = (
                float(np.dot(*pair)) if all(item is not None for item in pair) else None)
        # Actual native zero/multiple-face and maximum selected-venue confidence gate.
        empty = prepare_public_selfie(context=context,engine=engine,selfie=np.zeros((360,620,3),dtype=np.uint8))
        assert empty.native_face_count == 0 and empty.query is None and empty.rejection_reason == 'no_face'
        multi = prepare_public_selfie(context=context,engine=engine,selfie=np.concatenate((original,original),axis=1))
        assert multi.native_face_count >= 2 and multi.query is None and multi.rejection_reason == 'multiple_faces'
        strict = replace(context, venues=tuple(replace(v,min_query_face_quality=1.) for v in context.venues))
        low = prepare_public_selfie(context=strict,engine=engine,selfie=original)
        assert not low.quality_gate_passed and low.query is None and low.rejection_reason == 'low_quality'
        # Distinguishable per-venue thresholds on the exact same scope/vector.
        thresholds = tuple((v,.4 if i==0 else 1.) for i,v in enumerate(venues[:3]))
        rotated = np.array(embedding); orthogonal = np.roll(rotated,1); orthogonal -= np.dot(rotated,orthogonal)*rotated
        orthogonal /= np.linalg.norm(orthogonal); approximate = .7*rotated + np.sqrt(1-.7**2)*orthogonal
        result = repository.search(pipeline_revision_id=revision.id,query_embedding=approximate,venue_thresholds=thresholds)
        assert {m.spa_id for m in result} == {venues[0]}
        # Preserve existing Promo exact-search date/pHash eligibility on the same fixture.
        promo = ExactCompatibleSearchRepository(session)
        assert promo.search(spa_id=venues[0],visit_date=date(2001,1,1),
            pipeline_revision_id=revision.id,query_embedding=embedding,reference_threshold=.4) == ()
        promo_id, _ = _add_photo(session,marker='promo-with-phash',spa_id=venues[0],revision_id=revision.id,
            embedding=embedding,prefix='task122/',visit_date=date(2001,1,1),phash64=1)
        assert [m.photo_id for m in promo.search(spa_id=venues[0],visit_date=date(2001,1,1),
            pipeline_revision_id=revision.id,query_embedding=embedding,reference_threshold=.4)] == [promo_id]
        assert promo.search(spa_id=venues[0],visit_date=date(2026,1,1),
            pipeline_revision_id=revision.id,query_embedding=embedding,reference_threshold=.4) == ()
        observations.append({'pipeline':pipeline,'native_empty_faces':empty.native_face_count,
            'native_multiple_faces':multi.native_face_count,'strict_gate':low.quality_gate_passed,'per_venue_thresholds':'passed','promo_date_phash_regression':'passed'})
    (ARTIFACTS/f'native-{pipeline}-comparison.json').write_text(json.dumps(observations,indent=2)+'\n')

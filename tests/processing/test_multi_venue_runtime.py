"""AC-27: real PostgreSQL, MinIO, native SFace and production lifecycles."""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
import uuid

import cv2
import pytest
from skimage import data
from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.entrypoints import background_worker, realtime
from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.admission import AdmissionCandidate, AtomicPhotoAdmission
from face_moment.inventory.candidate_staging import StagedCandidate
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import JpegValidationLimits, validate_jpeg_candidate
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.sface_adapter import SFaceModelAssets
from face_moment.promo import PromoAttempt, PromoSession, PromoSessionRepository
from face_moment.promo.display_media import PromoMediaNotFoundError, resolve_teaser_media
from face_moment.promo.qr_continuation import PhoneContinuationService
from face_moment.serving_control.display_client_access import DisplayClientRepository
from face_moment.serving_control.ingest_target import CommittedServingTargetUnavailableError, IngestTargetRepository, Spa
from face_moment.serving_control.realtime_context import RealtimeContextRepository
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.promo.test_realtime_attempt_integration import _async_request, _manifest, _multipart


def test_native_two_venues_restart_photo_search_and_qr(monkeypatch):
    assets = SFaceModelAssets(
        detector_path=Path('models/opencv_sface/yunet.onnx'), detector_id='yunet', detector_version='2023mar',
        recognizer_path=Path('models/opencv_sface/sface.onnx'), recognizer_id='sface', recognizer_version='2021dec',
        preprocessing_version='opencv-photo-640-v2', alignment_version='aligncrop-v1', normalization_version='l2-v1')
    assert assets.detector_path.is_file() and assets.recognizer_path.is_file()
    for key in ('detector_path', 'detector_id', 'detector_version', 'recognizer_path',
                'recognizer_id', 'recognizer_version', 'preprocessing_version', 'alignment_version', 'normalization_version'):
        monkeypatch.setenv('SFACE_' + key.upper(), str(getattr(assets, key)))
    monkeypatch.setenv('SFACE_EMBEDDING_DIMENSION', '128')
    monkeypatch.setenv('REALTIME_RESULT_DISPLAY_MS', '5000')
    monkeypatch.setenv('REALTIME_SUCCESS_COOLDOWN_MS', '1000')
    image = cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR)
    crop = cv2.imencode('.jpg', image[40:200, 160:300])[1].tobytes()
    original_payloads = [cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, q])[1].tobytes()
                         for q in (88, 90, 92, 94)]
    with disposable_postgresql_engine('multi_venue_native') as engine:
        settings = Settings.from_env()
        ensure_bucket(settings)
        store = PrivateObjectStore(settings)
        original_keys = []
        photo_ids = {}
        try:
            with Session(engine) as session:
                revision = PipelineRevisionRepository(session).publish_eligible(
                    pipeline_code=PipelineCode.OPENCV_SFACE, validated_at=datetime.now(UTC),
                    weights_sha256=assets.weights_sha256(), embedding_dimension=128,
                    **{k: getattr(assets, k) for k in ('detector_id', 'detector_version', 'recognizer_id',
                       'recognizer_version', 'preprocessing_version', 'alignment_version', 'normalization_version')})
                venues, tokens = [], []
                for i, zone in enumerate(('UTC', 'Asia/Dushanbe')):
                    venue = IngestTargetRepository(session).configure_spa(timezone=zone, serving_pipeline_revision_id=revision.id)
                    venues.append(venue)
                    spa = session.get(Spa, venue.spa_id)
                    spa.photo_yunet_threshold = (.8, .85)[i]
                    spa.capture_blazeface_threshold = (.4, .7)[i]
                    context = RealtimeContextRepository(session)
                    context.update_search_dates(spa_id=venue.spa_id, search_today=False,
                        date_from=date(2026, 9, 15+i), date_to=date(2026, 9, 16+i))
                    context.provision_reference_settings(spa_id=venue.spa_id, pipeline_code=revision.pipeline_code,
                        reference_threshold=(.2, .4)[i], min_query_face_quality=(0., .01)[i], quality_settings={'version': 1})
                    tokens.append(DisplayClientRepository(session).provision(spa_id=venue.spa_id, name=f'Screen {i}').token_value)
                session.commit()
            # Identical people AND identical JPEG bytes across venues: distance cannot separate them.
            for i, venue in enumerate(venues):
                photo_ids[venue.spa_id] = set()
                for payload in original_payloads:
                    key = f'private/multi-venue/{uuid.uuid4()}.jpg'
                    original_keys.append(key)
                    store.put(key=key, body=payload)
                    validated = validate_jpeg_candidate(payload, visit_date=date(2026, 9, 16),
                        spa_timezone=venue.timezone, upload_started_at=datetime.now(UTC),
                        limits=JpegValidationLimits(10_000_000, 4096, 20_000_000))
                    with Session(engine) as session:
                        photo = AtomicPhotoAdmission(session).publish(ingest_target=venue, uploader_id=uuid.uuid4(),
                            candidate=AdmissionCandidate(StagedCandidate(key=key), validated))
                        assert photo.photo_yunet_threshold == (.8, .85)[i]
                        photo_ids[venue.spa_id].add(photo.id)

            async def exercise():
                for restart in range(2):
                    worker_app, realtime_app = background_worker.create_app(), realtime.create_app()
                    async with worker_app.router.lifespan_context(worker_app), realtime_app.router.lifespan_context(realtime_app):
                        assert worker_app.state.role_state['ready']
                        assert realtime_app.state.role_state['ready']
                        for _ in range(200):
                            with Session(engine) as session:
                                statuses = list(session.scalars(select(PhotoPipelineState.status)))
                            if statuses == ['ready'] * 8:
                                break
                            await asyncio.sleep(.1)
                        assert statuses == ['ready'] * 8, statuses
                        for i, (venue, token) in enumerate(zip(venues, tokens)):
                            body, content_type = _multipart(_manifest(uuid.uuid4(), count=1), crops=[crop])
                            status, _, payload = await _async_request(realtime_app, body, content_type, token)
                            assert status == 200 and payload['outcome'] == 'result', payload
                            result = payload['result']
                            assert result['n'] == 4
                            assert {uuid.UUID(p['photo_id']) for p in result['teasers']} <= photo_ids[venue.spa_id]
                            with Session(engine) as session:
                                promo = session.get(PromoSession, uuid.UUID(result['session_id']))
                                assert promo.spa_id == venue.spa_id
                                attempt = session.get(PromoAttempt, promo.attempt_id)
                                assert attempt.spa_id == venue.spa_id
                                assert attempt.threshold == (.2, .4)[i]
                                assert attempt.visit_date == date(2026, 9, 15+i)
                                assert set(promo.session_result_photo_ids) == photo_ids[venue.spa_id]
                                for teaser in result['teasers']:
                                    teaser_photo_id = uuid.UUID(teaser['photo_id'])
                                    assert teaser['media_url'] == (
                                        f"/api/promo/sessions/{promo.id}/media/{teaser_photo_id}"
                                    )
                                    assert resolve_teaser_media(session, spa_id=venue.spa_id,
                                        session_id=promo.id, photo_id=teaser_photo_id,
                                        object_store=store)
                                    with pytest.raises(PromoMediaNotFoundError):
                                        resolve_teaser_media(session, spa_id=venues[1-i].spa_id,
                                            session_id=promo.id, photo_id=teaser_photo_id,
                                            object_store=store)
                                ticket = result['qr_url'].split('ticket=')[1]
                                opened, first = PromoSessionRepository(session,
                                    qr_ticket_secret=settings.promo_qr_ticket_secret.encode()).open_browser_access(ticket)
                                assert first and opened.spa_id == venue.spa_id
                                assert set(opened.teaser_photo_ids) <= photo_ids[venue.spa_id]
                                session.commit()
                                phone = PhoneContinuationService(session,
                                    qr_ticket_secret=settings.promo_qr_ticket_secret,
                                    purchase_url='https://example.test/purchase', object_store=store).read_session(ticket)
                                assert phone.spa_name == venue.name
                                assert phone.visit_date == date(2026, 9, 15+i).isoformat()
                                assert uuid.UUID(phone.teaser.photo_id) in photo_ids[venue.spa_id]
            asyncio.run(exercise())
            with Session(engine) as session:
                for i, venue in enumerate(venues):
                    spa = session.get(Spa, venue.spa_id)
                    assert (spa.timezone, spa.photo_yunet_threshold, spa.capture_blazeface_threshold) == (
                        venue.timezone, (.8, .85)[i], (.4, .7)[i])
                for photo in session.scalars(select(Photo)):
                    assert store.read(key=photo.original_object_key) in original_payloads
            with Session(engine) as session:
                other_revision = PipelineRevisionRepository(session).publish_eligible(
                    pipeline_code=PipelineCode.OPENCV_SFACE, validated_at=datetime.now(UTC),
                    weights_sha256=assets.weights_sha256(), embedding_dimension=128,
                    **{k: getattr(assets, k) for k in ('detector_id', 'detector_version', 'recognizer_id',
                       'recognizer_version', 'preprocessing_version', 'alignment_version', 'normalization_version')})
                session.get(Spa, venues[1].spa_id).serving_pipeline_revision_id = other_revision.id
                session.commit()
            async def rejected_startups():
                for create_app in (background_worker.create_app, realtime.create_app):
                    app = create_app()
                    with pytest.raises(CommittedServingTargetUnavailableError):
                        async with app.router.lifespan_context(app):
                            pytest.fail('conflicting revisions opened readiness')
                    assert not app.state.role_state['ready']
            asyncio.run(rejected_startups())
        finally:
            for key in original_keys:
                store.delete(key=key)
            for ids in photo_ids.values():
                for photo_id in ids:
                    for key in store.list_keys(prefix=f'private/derivatives/{photo_id}/'):
                        store.delete(key=key)

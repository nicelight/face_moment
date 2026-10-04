"""Fixed gallery HTTP authorization using disposable owner state and JPEG bytes."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
import uuid

from botocore.exceptions import ClientError
from PIL import Image
import pytest
from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.promo import PromoAttemptRepository, PromoSession, ResultAssembly
from face_moment.promo.result_assembly import GalleryPhoto
from face_moment.serving_control.display_client_access import DisplayClientRepository
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from face_moment.serving_control.ingest_target import IngestTargetRepository
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY
from tests.processing.test_realtime_search import _add_photo
from tests.promo.test_result_session import _attempt_values


def jpeg(width=640):
    output = BytesIO()
    Image.new('RGB', (width, width // 2), (35, 90, 160)).save(output, 'JPEG')
    return output.getvalue()


class ObjectStore:
    def __init__(self):
        self.objects = {}
        self.reads = []

    def read(self, *, key):
        self.reads.append(key)
        if key not in self.objects:
            raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
        return self.objects[key]


async def request(app, path, token):
    messages = []
    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}
    async def send(message):
        messages.append(message)
    headers = [(b'host', b'localhost')]
    if token is not None:
        headers.append((b'authorization', f'Bearer {token}'.encode()))
    await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
        'method': 'GET', 'scheme': 'https', 'path': path, 'raw_path': path.encode(),
        'query_string': b'', 'root_path': '', 'headers': headers,
        'client': ('127.0.0.1', 1), 'server': ('localhost', 443)}, receive, send)
    start = next(m for m in messages if m['type'] == 'http.response.start')
    return start['status'], dict((k.decode(), v.decode()) for k, v in start['headers']), b''.join(
        m.get('body', b'') for m in messages if m['type'] == 'http.response.body')


@pytest.fixture
def gallery():
    with disposable_postgresql_engine('task142_media') as engine:
        store = ObjectStore()
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE, validated_at=datetime.now(timezone.utc),
                **PIPELINE_COMPATIBILITY).id
            venues = [IngestTargetRepository(session).configure_public_spa(
                name=f'gallery {i}', timezone='Asia/Dushanbe', serving_pipeline_revision_id=revision,
                is_free=False).spa_id for i in range(2)]
            clients = [DisplayClientRepository(session).provision(spa_id=v, name='test') for v in venues]
            tokens = [c.token_value for c in clients]; client_id = clients[0].id
            photos = []
            for i in range(7):
                photo, key = _add_photo(session, marker=f'photo{i}', spa_id=venues[i == 6],
                    revision_id=revision, embedding=(1.,) + (0.,)*127, prefix='task142/',
                    visit_date=date(2001, 1, 1), state_status='no_faces' if i == 5 else 'ready',
                    has_preview=i != 5)
                photos.append(photo)
                store.objects[key] = jpeg()
                store.objects[f'task142/photo{i}-original.jpg'] = jpeg(1200)
            values = _attempt_values(uuid.uuid4()); values.update(spa_id=venues[0], pipeline_revision_id=revision)
            repository = PromoAttemptRepository(session)
            attempt = repository.create_or_get(**values)
            repository.mark_search_started(attempt)
            assembly = ResultAssembly(outcome='result', session_result_photo_ids=tuple(photos[:5]),
                teaser_photo_ids=tuple(photos[:4]), n=5,
                gallery_photos=tuple(GalleryPhoto(p, 'matched') for p in photos[:5]))
            result = repository.publish_result(attempt, assembly, qr_ticket_secret=b'task142-only-secret', display_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1))
            session.commit(); session_id = result.session_id; attempt_id = attempt.id
        app = create_app(); app.state.role_state['session_factory'] = lambda: Session(engine)
        app.state.promo_display_object_store = store
        app.state.promo_display_rate_limiter = DisplayClientRateLimiter(limit=1000, window_seconds=60)
        yield SimpleNamespace(engine=engine, store=store, app=app, photos=photos, tokens=tokens,
            client_id=client_id, session_id=session_id, attempt_id=attempt_id, revision=revision, venues=venues)


def get(fixture, photo=None, *, token_index=0, path=None, token=None):
    path = path or f'/api/promo/sessions/{fixture.session_id}/gallery/media/{photo or fixture.photos[4]}'
    return asyncio.run(request(fixture.app, path, fixture.tokens[token_index] if token is None else token))


def snapshot(fixture):
    with fixture.engine.connect() as connection:
        return {table: connection.execute(text(f'SELECT to_jsonb(t) FROM face_moment.{table} t ORDER BY to_jsonb(t)::text')).scalars().all()
            for table in ('promo_sessions', 'promo_attempts', 'photo_pipeline_states')}


def test_authorized_gallery_and_common_are_reduced_no_store_without_mutation(gallery, caplog):
    before = snapshot(gallery)
    for photo in gallery.photos[:6]:
        code, headers, body = get(gallery, photo)
        assert code == 200, f'authorized fixed gallery member expected 200, observed {code}'
        assert headers['content-type'] == 'image/jpeg' and headers['cache-control'] == 'no-store'
        with Image.open(BytesIO(body)) as image:
            assert image.size == (640, 320)
        assert body != jpeg(1200)
        assert b'task142/' not in body and b'X-Amz-' not in body
    assert snapshot(gallery) == before
    assert 'task142/photo5-original.jpg' in gallery.store.reads
    assert all(token not in caplog.text for token in gallery.tokens)


def test_denial_matrix_and_strict_teaser_route_preserve_state(gallery, caplog):
    from face_moment.inventory.photo_persistence import Photo
    from face_moment.processing.persistence import PhotoFace, PhotoPipelineState
    from face_moment.promo import PromoAttempt

    def check(expected, photo=None, **kwargs):
        before = snapshot(gallery)
        code, headers, body = get(gallery, photo, **kwargs)
        assert code == expected
        assert headers['cache-control'] == 'no-store'
        assert snapshot(gallery) == before
        if code != 200:
            assert b'task142/' not in body and b'photo_id' not in body
        return body

    path = f'/api/promo/sessions/{gallery.session_id}/gallery/media/{gallery.photos[4]}'
    before = snapshot(gallery)
    code, headers, _ = asyncio.run(request(gallery.app, path, None))
    assert code == 401 and headers['cache-control'] == 'no-store'
    assert snapshot(gallery) == before
    check(401, token='invalid')
    check(404, token_index=1)
    check(404, gallery.photos[6])
    check(404, uuid.uuid4())
    check(404, path=f'/api/promo/sessions/{uuid.uuid4()}/gallery/media/{gallery.photos[4]}')
    check(404, path=f'/api/promo/sessions/{gallery.session_id}/media/{gallery.photos[4]}')
    check(200, path=f'/api/promo/sessions/{gallery.session_id}/media/{gallery.photos[0]}')
    gallery.store.objects.pop('task142/photo4.jpg')
    check(404)
    gallery.store.objects['task142/photo4.jpg'] = jpeg()
    original = gallery.store.objects.pop('task142/photo5-original.jpg')
    check(404, gallery.photos[5])
    gallery.store.objects['task142/photo5-original.jpg'] = b'corrupt JPEG'
    check(404, gallery.photos[5])
    gallery.store.objects['task142/photo5-original.jpg'] = original
    with Session(gallery.engine) as session:
        session.get(Photo, gallery.photos[5]).is_active = False
        session.commit()
    check(404, gallery.photos[5])
    with Session(gallery.engine) as session:
        session.get(Photo, gallery.photos[5]).is_active = True
        state = session.get(PhotoPipelineState, (gallery.photos[5], gallery.revision))
        state.status = 'ready'; session.commit()
    check(404, gallery.photos[5])
    with Session(gallery.engine) as session:
        row = session.get(PromoSession, gallery.session_id)
        fixed = row.gallery_photos
        row.gallery_photos = None; session.commit()
    check(404)
    check(200, path=f'/api/promo/sessions/{gallery.session_id}/media/{gallery.photos[0]}')
    with Session(gallery.engine) as session:
        session.get(PromoSession, gallery.session_id).gallery_photos = fixed
        # A stored reference from another venue cannot bypass provider scope.
        session.get(PromoSession, gallery.session_id).gallery_photos = fixed + [
            {'photo_id': str(gallery.photos[6]), 'kind': 'matched'}]
        session.commit()
    check(404, gallery.photos[6])
    with Session(gallery.engine) as session:
        session.get(PromoSession, gallery.session_id).gallery_photos = fixed
        session.get(PromoAttempt, gallery.attempt_id).pipeline_revision_id = uuid.uuid4()
        session.commit()
    check(404)
    with Session(gallery.engine) as session:
        session.get(PromoAttempt, gallery.attempt_id).pipeline_revision_id = gallery.revision
        # Task-owned purge fixture: remove dependent state before the Photo.
        session.execute(delete(PhotoFace).where(PhotoFace.photo_id == gallery.photos[4]))
        session.execute(delete(PhotoPipelineState).where(PhotoPipelineState.photo_id == gallery.photos[4]))
        session.delete(session.get(Photo, gallery.photos[4])); session.commit()
    check(404)
    with Session(gallery.engine) as session:
        updated = DisplayClientRepository(session).reset(display_client_id=gallery.client_id)
        fresh = updated.token_value; session.commit()
    check(401)
    with Session(gallery.engine) as session:
        DisplayClientRepository(session).deactivate(display_client_id=gallery.client_id); session.commit()
    check(401, token=fresh)
    assert all(token not in caplog.text for token in (*gallery.tokens, fresh))


def test_matched_preview_uses_issuing_revision_after_serving_switch(gallery):
    from face_moment.serving_control.ingest_target import Spa
    from face_moment.inventory.photo_persistence import Photo
    with Session(gallery.engine) as session:
        other = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M, validated_at=datetime.now(timezone.utc),
            **PIPELINE_COMPATIBILITY).id
        session.get(Spa, gallery.venues[0]).serving_pipeline_revision_id = other
        session.get(Photo, gallery.photos[4]).admission_pipeline_revision_id = other
        session.commit()
    before = snapshot(gallery)
    code, _, body = get(gallery)
    assert code == 200 and body == gallery.store.objects['task142/photo4.jpg']
    assert gallery.store.reads == ['task142/photo4.jpg']
    assert snapshot(gallery) == before

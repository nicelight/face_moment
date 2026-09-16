"""Disposable PostgreSQL/MinIO proof of private staff media browsing."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
from io import BytesIO
import json
from typing import Any, Iterator
from urllib.parse import urlencode
import uuid

from fastapi import FastAPI
from PIL import Image
import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy import select, text

from face_moment.diagnostics.evidence import DiagnosticEvidence
from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import Settings
from face_moment.inventory import staff_media_http
from face_moment.inventory.orphan_original_cleanup import (
    OriginalCleanupRunningError,
    OriginalCleanupResult,
    OriginalCleanupUploadPausedError,
    admission_storage_guard,
    cleanup_orphan_originals,
)
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.platform.auth.sessions import LoginRateLimiter, create_browser_session
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.derivatives import derivative_object_key
from face_moment.promo import advertising_http
from face_moment.promo.advertising import AdvertisingMedia
from face_moment.serving_control.ingest_target import IngestTargetRepository, Spa
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@dataclass
class MediaFixture:
    app: FastAPI
    engine: Engine
    spa_id: uuid.UUID
    other_spa_id: uuid.UUID
    ids: dict[str, uuid.UUID]
    cookies: dict[str, dict[str, str]]
    store: PrivateObjectStore
    original: bytes
    thumbnail: bytes
    keys: list[str]


@dataclass
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


def request(app: FastAPI, path: str, *, cookies: dict[str, str] | None = None,
            params: dict[str, str] | None = None, method: str = 'GET',
            payload: dict[str, object] | None = None, csrf: str | None = None,
            raw_body: bytes | None = None, content_type: str | None = None) -> Reply:
    body = raw_body if raw_body is not None else json.dumps(payload).encode() if payload is not None else b''
    headers = [(b'host', b'testserver')]
    if cookies:
        headers.append((b'cookie', '; '.join(f'{k}={v}' for k,v in cookies.items()).encode()))
    if payload is not None or content_type is not None:
        headers.append((b'content-type', (content_type or 'application/json').encode()))
    if csrf is not None:
        headers.append((b'x-csrf-token', csrf.encode()))
    messages: list[dict[str, Any]] = []
    delivered = False
    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {'type': 'http.disconnect'}
        delivered = True
        return {'type': 'http.request', 'body': body, 'more_body': False}
    async def send(message: dict[str, Any]) -> None:
        messages.append(message)
    asyncio.run(app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
        'method': method, 'scheme': 'https', 'path': path, 'raw_path': path.encode(),
        'query_string': urlencode(params or {}).encode(), 'headers': headers,
        'client': ('127.0.0.1', 12345), 'server': ('testserver',443)}, receive, send))
    start = next(m for m in messages if m['type'] == 'http.response.start')
    return Reply(start['status'], {k.decode(): v.decode() for k,v in start['headers']},
        b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body'))


@pytest.fixture
def media_state() -> Iterator[MediaFixture]:
    marker = uuid.uuid4().hex
    store = PrivateObjectStore(Settings.from_env())
    buffers = []
    for dimensions in ((640,400), (320,200)):
        buf = BytesIO(); Image.new('RGB', dimensions, '#487b95').save(buf, 'JPEG'); buffers.append(buf.getvalue())
    keys: list[str] = []
    with disposable_postgresql_engine('staff_media') as engine:
        try:
            ids: dict[str, uuid.UUID] = {}
            cookies = {}
            with Session(engine) as session:
                repo = PipelineRevisionRepository(session)
                revision = repo.publish_eligible(pipeline_code=PipelineCode.OPENCV_SFACE,
                    validated_at=datetime.now(UTC), **PIPELINE_COMPATIBILITY)
                newer = repo.publish_eligible(pipeline_code=PipelineCode.OPENCV_SFACE,
                    validated_at=datetime.now(UTC), **{**PIPELINE_COMPATIBILITY, 'weights_sha256': 'f'*64})
                venues = IngestTargetRepository(session)
                target = venues.configure_spa(name='Бассейн <script>bad()</script>', timezone='Asia/Novosibirsk', serving_pipeline_revision_id=revision.id)
                other = venues.configure_spa(name='Другой бассейн', timezone='Asia/Novosibirsk', serving_pipeline_revision_id=revision.id)
                users = {}
                for role in ('photographer','other','operator','developer'):
                    username = f'media-{role}-{marker}'
                    password = f'fixture-{marker}'
                    users[role] = provision_staff_user(session, username=username, password=password,
                        role=StaffRole.PHOTOGRAPHER if role=='other' else StaffRole(role))
                session.commit()
                for role in users:
                    browser = create_browser_session(session, username=f'media-{role}-{marker}', password=f'fixture-{marker}',
                        ip_address='127.0.0.1', ttl_seconds=3600, limiter=LoginRateLimiter(limit=20, window_seconds=60))
                    cookies[role] = {'fm_staff_session': browser.session_token, 'fm_staff_csrf': browser.csrf_token}
                start = datetime(2026,9,11,17,tzinfo=UTC)
                rows = [('ready',0,'ready'), ('foreign',1,'ready'), ('no_faces',2,'no_faces'),
                        ('pending',3,'pending'), ('failed',4,'failed'), ('absent',5,None),
                        ('other_venue',6,'ready'), ('hidden',7,'ready'), ('before',-1,'ready'), ('after',86400,'ready')]
                for name, seconds, state in rows:
                    original_key = f'private/staff-media-test/{marker}/{name}/original.jpg'
                    thumb_key = f'private/staff-media-test/{marker}/{name}/thumbnail.jpg'
                    for key, data in ((original_key,buffers[0]),(thumb_key,buffers[1])):
                        store.put(key=key, body=data); keys.append(key)
                    photo = Photo(spa_id=other.spa_id if name=='other_venue' else target.spa_id,
                        visit_date=date(2026,8,1), captured_at=datetime(2026,8,1,10,tzinfo=UTC),
                        captured_at_source=CapturedAtSource.EXIF, accepted_at=start+timedelta(seconds=seconds),
                        admission_pipeline_revision_id=revision.id,
                        uploader_id=users['other' if name=='foreign' else 'photographer'].staff_user_id,
                        checksum_sha256=hashlib.sha256((marker+name).encode()).digest(),
                        original_object_key=original_key, original_byte_size=len(buffers[0]), width=640,height=400,is_active=name!='hidden')
                    session.add(photo); session.flush(); ids[name]=photo.id
                    if state:
                        session.add(PhotoPipelineState(photo_id=photo.id,pipeline_revision_id=revision.id,status=state,
                            thumbnail_object_key=thumb_key if state=='ready' else None))
                    if name in ('ready','no_faces'):
                        session.add(PhotoPipelineState(photo_id=photo.id,pipeline_revision_id=newer.id,
                            status='no_faces' if name=='ready' else 'ready', thumbnail_object_key=thumb_key))
                session.commit()
            app = create_app(); app.state.role_state['session_factory'] = lambda: Session(engine)
            yield MediaFixture(app,engine,target.spa_id,other.spa_id,ids,cookies,store,*buffers,keys)
        finally:
            for key in keys:
                store.delete(key=key)


def selection(f: MediaFixture, **changes: str) -> dict[str,str]:
    return {'spa_id':str(f.spa_id),'date_from':'2026-09-12','date_to':'2026-09-12',**changes}


def test_staff_media_journey_and_authorization_boundary(media_state: MediaFixture) -> None:
    f=media_state
    for role in ('photographer','operator','developer'):
        page=request(f.app,'/staff/venue-media',params={'spa_id':str(f.spa_id)},cookies=f.cookies[role])
        assert page.status==200
        assert b'data-staff-media' in page.body
        assert b'<script>bad()' not in page.body
        listing=request(f.app,'/api/inventory/venue-media',params=selection(f),cookies=f.cookies[role])
        assert listing.status==200
        assert listing.headers['cache-control']=='no-store'
        expected=['absent','failed','pending']+(['foreign'] if role!='photographer' else [])+['ready']
        assert [p['photo_id'] for p in listing.json()['photos']]==[str(f.ids[n]) for n in expected]
        assert b'private/' not in listing.body
    for path in ('/staff/venue-media','/api/inventory/venue-media',f'/api/inventory/venue-media/{f.ids["ready"]}/original'):
        assert request(f.app,path,params=selection(f)).status==401


def test_private_media_requires_session_before_delivery(media_state: MediaFixture) -> None:
    f=media_state
    for suffix in ('thumbnail','original'):
        response=request(f.app,f'/api/inventory/venue-media/{f.ids["ready"]}/{suffix}')
        assert response.status==401
        assert response.headers['cache-control']=='no-store'


def test_private_bytes_ownership_missing_objects_and_revoke(media_state: MediaFixture) -> None:
    f=media_state
    for role in ('photographer','operator','developer'):
        for suffix, expected in (('thumbnail',f.thumbnail),('original',f.original)):
            response=request(f.app,f'/api/inventory/venue-media/{f.ids["ready"]}/{suffix}',cookies=f.cookies[role])
            assert response.status==200 and response.body==expected
            assert response.headers['content-type']=='image/jpeg'
            assert response.headers['cache-control']=='no-store'
            with Image.open(BytesIO(response.body)) as image:
                assert image.size==((320,200) if suffix=='thumbnail' else (640,400))
    for suffix in ('thumbnail','original'):
        denied=request(f.app,f'/api/inventory/venue-media/{f.ids["foreign"]}/{suffix}',cookies=f.cookies['photographer'])
        assert denied.status==403 and denied.headers['cache-control']=='no-store'
    assert request(f.app,f'/api/inventory/venue-media/{f.ids["absent"]}/thumbnail',cookies=f.cookies['developer']).status==404
    assert request(f.app,f'/api/inventory/venue-media/{uuid.uuid4()}/original',cookies=f.cookies['developer']).status==404
    key=next(k for k in f.keys if k.endswith('/ready/thumbnail.jpg'))
    f.store.delete(key=key)
    assert request(f.app,f'/api/inventory/venue-media/{f.ids["ready"]}/thumbnail',cookies=f.cookies['developer']).status==404
    cookies=f.cookies['developer']
    assert request(f.app,'/api/staff/session',cookies=cookies,method='DELETE',csrf=cookies['fm_staff_csrf']).status==204
    for path in ('/api/inventory/venue-media',f'/api/inventory/venue-media/{f.ids["ready"]}/original',f'/api/inventory/venue-media/{f.ids["ready"]}/thumbnail'):
        assert request(f.app,path,params=selection(f),cookies=cookies).status==401


def test_date_validation_venue_and_store_failures(media_state: MediaFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    f=media_state; cookies=f.cookies['operator']
    for values in ({'date_from':'2026-09-13'}, {'date_to':'nonsense'}, {'date_to':'9999-12-31'}, {'spa_id':'bad'}):
        reply=request(f.app,'/api/inventory/venue-media',params=selection(f,**values),cookies=cookies)
        assert reply.status==422 and reply.headers['cache-control']=='no-store'
    assert request(f.app,'/api/inventory/venue-media',params=selection(f,spa_id=str(uuid.uuid4())),cookies=cookies).status==404
    def fail_read(self: PrivateObjectStore, *, key: str) -> bytes:
        raise ValueError('test storage outage private/secret')
    monkeypatch.setattr(PrivateObjectStore,'read',fail_read)
    reply=request(f.app,f'/api/inventory/venue-media/{f.ids["ready"]}/original',cookies=cookies)
    assert reply.status==500 and reply.headers['cache-control']=='no-store'
    assert b'private/' not in reply.body
    with Session(f.engine) as session:
        spa=session.get(Spa,f.spa_id); assert spa; spa.active=False; session.commit()
    for path in ('/staff/venue-media','/api/inventory/venue-media',f'/api/inventory/venue-media/{f.ids["ready"]}/original'):
        assert request(f.app,path,params=selection(f),cookies=cookies).status==403


def test_soft_delete_preserves_media_and_requires_csrf(media_state: MediaFixture) -> None:
    f=media_state; cookies=f.cookies['developer']; photo_id=f.ids['ready']
    path=f'/api/inventory/photos/{photo_id}/visibility'
    with Session(f.engine) as session:
        photo=session.get(Photo,photo_id); assert photo
        before=(photo.accepted_at,photo.captured_at,photo.original_object_key)
    for csrf in (None,'wrong'):
        assert request(f.app,path,cookies=cookies,method='PUT',payload={'schema_version':1,'active':False},csrf=csrf).status==403
        with Session(f.engine) as session:
            photo=session.get(Photo,photo_id); assert photo and photo.is_active
    result=request(f.app,path,cookies=cookies,method='PUT',payload={'schema_version':1,'active':False},csrf=cookies['fm_staff_csrf'])
    assert result.status==200
    with Session(f.engine) as session:
        photo=session.get(Photo,photo_id); assert photo and not photo.is_active
        assert (photo.accepted_at,photo.captured_at,photo.original_object_key)==before
    assert request(f.app,f'/api/inventory/venue-media/{photo_id}/original',cookies=cookies).body==f.original
    listed=request(f.app,'/api/inventory/venue-media',params=selection(f),cookies=cookies).json()['photos']
    assert str(photo_id) not in [row['photo_id'] for row in listed]


def test_orphan_cleanup_keeps_referenced_originals_and_pauses_uploads(
    media_state: MediaFixture,
) -> None:
    f = media_state
    with Session(f.engine) as session:
        referenced = session.get(Photo, f.ids['ready'])
        assert referenced is not None
        existing_key = referenced.original_object_key
    orphan_key = f'candidates/test-orphan-{uuid.uuid4().hex}'

    class Store:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def list_key_pages(self, *, prefix: str) -> Iterator[list[str]]:
            yield [existing_key, orphan_key] if prefix == 'candidates/' else []

        def delete(self, *, key: str) -> None:
            self.deleted.append(key)

    store = Store()
    with Session(f.engine) as session:
        result = cleanup_orphan_originals(session, store)  # type: ignore[arg-type]
    assert result == OriginalCleanupResult(scanned=2, deleted=1)
    assert store.deleted == [orphan_key]

    with f.engine.connect() as connection, connection.begin():
        connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 62_401_876_321})
        with Session(f.engine) as session:
            with pytest.raises(OriginalCleanupRunningError):
                cleanup_orphan_originals(session, store)  # type: ignore[arg-type]
    assert store.deleted == [orphan_key]

    # An exclusive cleanup lock makes the next admission fail before MinIO put.
    with f.engine.connect() as connection, connection.begin():
        connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 62_401_876_320})
        with Session(f.engine) as session:
            with pytest.raises(OriginalCleanupUploadPausedError):
                with admission_storage_guard(session):
                    pytest.fail('admission passed through cleanup lock')


def test_orphan_cleanup_scans_known_namespaces_without_deleting_owned_files(
    media_state: MediaFixture,
) -> None:
    f = media_state
    ad = AdvertisingMedia(id=uuid.uuid4(), spa_id=f.spa_id, filename='ad.jpg',
        content_type='image/jpeg', byte_size=1)
    ad_key = ad.object_key
    capture_id = uuid.uuid4()
    capture_key = f'diagnostics/captures/{capture_id}/0.jpg'
    promoted_key = f'diagnostics/captures/{capture_id}/1.jpg'
    legacy_key = f'diagnostics/captures/{capture_id}/2.jpg'
    with Session(f.engine) as session:
        state = session.scalar(select(PhotoPipelineState).where(
            PhotoPipelineState.photo_id == f.ids['ready']))
        assert state is not None
        derivative_key = derivative_object_key(photo_id=state.photo_id,
            pipeline_revision_id=state.pipeline_revision_id, artifact_kind='preview')
        session.add(ad)
        session.add(DiagnosticEvidence(attempt_id=capture_id, completeness='incomplete',
            gap_reason='test', ordinary_manifest={'artifacts': [
                {'object_key': capture_key}, {'key': legacy_key}]},
            promoted_subset={'media_refs': [promoted_key]}, promoted_at=datetime.now(UTC)))
        session.commit()

    orphan_ad = f'advertising/{f.spa_id}/{uuid.uuid4()}'
    orphan_derivative = derivative_object_key(photo_id=uuid.uuid4(),
        pipeline_revision_id=uuid.uuid4(), artifact_kind='thumbnail')
    orphan_capture = f'diagnostics/captures/{uuid.uuid4()}/0.jpg'
    pages = {
        'candidates/': [],
        'advertising/': [ad_key, orphan_ad, 'advertising/unknown'],
        'private/derivatives/': [derivative_key, orphan_derivative,
            'private/derivatives/unknown'],
        'diagnostics/captures/': [capture_key, promoted_key, legacy_key,
            orphan_capture, 'diagnostics/captures/unknown'],
    }

    class Store:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def list_key_pages(self, *, prefix: str) -> Iterator[list[str]]:
            yield pages[prefix]

        def delete(self, *, key: str) -> None:
            self.deleted.append(key)

    store = Store()
    with Session(f.engine) as session:
        result = cleanup_orphan_originals(session, store)  # type: ignore[arg-type]
    assert result == OriginalCleanupResult(scanned=11, deleted=3)
    assert store.deleted == [orphan_ad, orphan_derivative, orphan_capture]


def test_advertising_upload_pauses_before_object_write_during_cleanup(
    media_state: MediaFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    f = media_state
    monkeypatch.setattr(advertising_http, 's3_client', lambda _settings: pytest.fail(
        'MinIO upload happened while cleanup held the storage lock'))
    boundary = 'cleanup-guard-test'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            'filename="ad.jpg"\r\nContent-Type: image/jpeg\r\n\r\nx\r\n'
            f'--{boundary}--\r\n').encode()
    cookies = f.cookies['operator']
    with f.engine.connect() as connection, connection.begin():
        connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 62_401_876_320})
        reply = request(f.app, f'/api/advertising/{f.spa_id}/media', method='POST',
            cookies=cookies, csrf=cookies['fm_staff_csrf'], raw_body=body,
            content_type=f'multipart/form-data; boundary={boundary}')
    assert reply.status == 503


def test_orphan_cleanup_route_requires_admin_and_csrf(
    media_state: MediaFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    f = media_state
    calls: list[bool] = []

    def fake_cleanup(_session: Session, _store: PrivateObjectStore) -> OriginalCleanupResult:
        calls.append(True)
        return OriginalCleanupResult(scanned=12, deleted=3)

    monkeypatch.setattr(staff_media_http, 'cleanup_orphan_originals', fake_cleanup)
    path = '/api/inventory/orphan-originals/cleanup'
    for role in ('photographer', 'operator', 'developer'):
        page = request(f.app, '/staff/venue-media', params={'spa_id': str(f.spa_id)}, cookies=f.cookies[role])
        assert ('Запустить очистку битых файлов'.encode() in page.body) == (role != 'photographer')
        if role != 'photographer':
            assert 'Это может занять до 30 минут'.encode() in page.body
            assert '>ДА!</button>'.encode() in page.body and '>Отмена</button>'.encode() in page.body
    assert request(f.app, path, method='POST').status == 401
    for role in ('photographer', 'operator'):
        cookies = f.cookies[role]
        assert request(f.app, path, method='POST', cookies=cookies).status == 403
        assert request(f.app, path, method='POST', cookies=cookies, csrf='wrong').status == 403
    assert request(f.app, path, method='POST', cookies=f.cookies['photographer'],
                   csrf=f.cookies['photographer']['fm_staff_csrf']).status == 403
    assert calls == []
    for role in ('operator', 'developer'):
        cookies = f.cookies[role]
        reply = request(f.app, path, method='POST', cookies=cookies,
                        csrf=cookies['fm_staff_csrf'])
        assert reply.status == 200 and reply.headers['cache-control'] == 'no-store'
        assert reply.json() == {'schema_version': 1, 'scanned': 12, 'deleted': 3}
    assert len(calls) == 2

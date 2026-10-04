"""Public HTTP/profile/result integration on rerunnable isolated PostgreSQL."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from io import BytesIO
import json
import threading
import time
import uuid

import cv2
import numpy as np
from PIL import Image
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app as backend_app
from face_moment.entrypoints.realtime import create_app as realtime_app
from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.persistence import PublicExactSearchRepository
from face_moment.processing.reference_query import PreparedReferenceQuery, ReferenceQualityObservation
from face_moment.promo.browser_search_profile import BrowserSearchProfile, BrowserSearchProfileRepository, COOKIE_NAME
from face_moment.promo.public_photo_search import PublicSearchResult
from face_moment.promo.realtime_orchestration import _PROCESS_LOCAL_REALTIME_SLOT
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from face_moment.serving_control.ingest_target import IngestTargetRepository, Spa
from face_moment.serving_control.realtime_context import RealtimeContextRepository
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY
from tests.processing.test_realtime_search import _add_photo


def request(app, method, path, *, body=b'', headers=None, token=None, peer='127.0.0.1', scheme='https'):
    messages = []
    async def receive():
        return {'type': 'http.request', 'body': body, 'more_body': False}
    async def send(message):
        messages.append(message)
    values = {'host': 'localhost', 'origin': 'https://localhost', **(headers or {})}
    if token is not None:
        values['cookie'] = f'{COOKIE_NAME}={token}'
    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': method,
        'scheme': scheme, 'path': path, 'raw_path': path.encode(), 'query_string': b'', 'root_path': '',
        'headers': [(k.lower().encode(), v.encode()) for k, v in values.items()],
        'client': (peer, 1), 'server': ('localhost', 443)}
    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m['type'] == 'http.response.start')
    payload = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
    return start['status'], {k.decode(): v.decode() for k, v in start['headers']}, json.loads(payload)


def jpeg(width=64, height=64):
    image = BytesIO(); Image.new('RGB', (width, height), (80, 100, 120)).save(image, 'JPEG')
    return image.getvalue()


def multipart(venues, *, image=None, confirm=None, extra=None, mime='image/jpeg'):
    parts = [('selfie', jpeg() if image is None else image, mime, 'selfie.jpg'),
             ('venue_ids', json.dumps(venues).encode(), None, None)]
    if confirm is not None:
        parts.append(('confirm_reset', confirm, None, None))
    if extra:
        parts.extend(extra)
    body = bytearray()
    for name, data, content_type, filename in parts:
        body.extend(f'--task123\r\nContent-Disposition: form-data; name="{name}"'.encode())
        if filename:
            body.extend(f'; filename="{filename}"'.encode())
        body.extend(b'\r\n')
        if content_type:
            body.extend(f'Content-Type: {content_type}\r\n'.encode())
        body.extend(b'\r\n' + data + b'\r\n')
    body.extend(b'--task123--\r\n')
    return bytes(body), {'content-type': 'multipart/form-data; boundary=task123'}


class ProcessingBoundary:
    """Native boundary double; the separate HTTP/native test uses real warmed SFace."""
    def __init__(self, revision):
        self.pipeline_revision_id = revision
        self.embedding = np.eye(1, 128, dtype=np.float32)[0]
        self.calls = 0; self.faces = 1; self.quality = .9; self.delay = 0; self.fail = False

    def inspect_reference_crop(self, selfie, settings):
        self.calls += 1
        time.sleep(self.delay)
        if self.fail:
            raise RuntimeError('synthetic native technical failure')
        return ReferenceQualityObservation(native_face_count=self.faces, reference_quality_score=self.quality,
            gate_observations=(), prepared_query=PreparedReferenceQuery(self.pipeline_revision_id, self.embedding))

    def prepare_reference_query(self, selfie):
        return PreparedReferenceQuery(self.pipeline_revision_id, self.embedding)


@pytest.fixture
def public_fixture():
    with disposable_postgresql_engine('task123_http') as engine:
        model = None
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime.now(timezone.utc), **PIPELINE_COMPATIBILITY)
            model = ProcessingBoundary(revision.id)
            venues = []; personal = {}; common = {}; prefix = f'task123/{uuid.uuid4().hex}/'
            for i in range(4):
                target = IngestTargetRepository(session).configure_public_spa(name=f'synthetic venue {i}',
                    timezone='Asia/Dushanbe', serving_pipeline_revision_id=revision.id, is_free=i == 1)
                venues.append(target.spa_id)
                RealtimeContextRepository(session).provision_reference_settings(spa_id=target.spa_id,
                    pipeline_code=PipelineCode.OPENCV_SFACE, reference_threshold=.7,
                    min_query_face_quality=.6, quality_settings={'version': 1})
                spa = session.get(Spa, target.spa_id); spa.search_today = False
                spa.active_visit_date = None; spa.active_visit_date_to = None
                for year in (2001, 2026):
                    p, _ = _add_photo(session, marker=f'{i}-{year}', spa_id=target.spa_id, revision_id=revision.id,
                        embedding=tuple(model.embedding), prefix=prefix, visit_date=date(year, 1, 1), phash64=None)
                    personal[i, year] = p
                    p, _ = _add_photo(session, marker=f'common-{i}-{year}', spa_id=target.spa_id, revision_id=revision.id,
                        embedding=tuple(model.embedding), prefix=prefix, visit_date=date(year, 1, 1),
                        state_status='no_faces', has_preview=False)
                    common[i, year] = p
                _add_photo(session, marker=f'outside-date-{i}', spa_id=target.spa_id, revision_id=revision.id,
                    embedding=tuple(model.embedding), prefix=prefix, visit_date=date(1999, 1, 1),
                    state_status='no_faces', has_preview=False)
            session.commit(); revision_id = revision.id
        backend = backend_app(); realtime = realtime_app()
        backend.state.role_state['session_factory'] = lambda: Session(engine)
        state = realtime.state.role_state
        state.update(ready=True, session_factory=lambda: Session(engine), model_adapter=model,
            admitted_pipeline_revision_id=revision_id, realtime_deadline_ms=10000,
            public_search_rate_limiter=DisplayClientRateLimiter(limit=100, window_seconds=60))
        yield engine, backend, realtime, model, venues, personal, common


def submit(fixture, *, selected=None, token=None, **options):
    _, _, app, _, venues, _, _ = fixture
    body, headers = multipart([str(v) for v in venues[:3]] if selected is None else selected, **options)
    return request(app, 'POST', '/api/public/search', body=body, headers=headers, token=token)


def cookie(headers):
    return headers['set-cookie'].split(';', 1)[0].split('=', 1)[1]


def security(headers):
    assert headers['cache-control'] == 'no-store' and headers['referrer-policy'] == 'no-referrer'
    assert 'access-control-allow-origin' not in headers


def test_scope_current_result_paid_free_common_and_private_json(public_fixture):
    engine, backend, realtime, model, venues, personal, common = public_fixture
    code, headers, listing = request(backend, 'GET', '/api/public/venues')
    assert code == 200 and listing['schema_version'] == 1
    assert listing['venues'] == [{'id': str(v), 'name': f'synthetic venue {i}'} for i, v in enumerate(venues)]
    security(headers)
    for selection in ([], [str(v) for v in venues], [str(venues[0])]*2, [str(uuid.uuid4())], ['bad'], [True]):
        assert submit(public_fixture, selected=selection)[0] == 422
    assert model.calls == 0
    with Session(engine) as session:
        session.get(Spa, venues[3]).active = False; session.commit()
    assert submit(public_fixture, selected=[str(venues[3])])[0] == 422 and model.calls == 0
    code, headers, result = submit(public_fixture)
    assert code == 200 and result['outcome'] == 'result' and result['personal_count'] == 6
    token = cookie(headers); security(headers)
    for flag in ('HttpOnly', 'Secure', 'SameSite=lax', 'Max-Age=31536000', 'Path=/'):
        assert flag in headers['set-cookie']
    assert 'Domain=' not in headers['set-cookie']
    for i, venue in enumerate(result['venues']):
        assert venue['id'] == str(venues[i]) and venue['dates'] == ['2001-01-01', '2026-01-01']
        assert [p['id'] for p in venue['personal']] == [str(personal[i, year]) for year in (2001, 2026)]
        assert [p['id'] for p in venue['common']] == [str(common[i, year]) for year in (2001, 2026)]
        assert all(p['is_free'] is (i == 1) for p in venue['personal'])
        assert all(p['is_free'] is True for p in venue['common'])
        assert all(p['preview_url'].startswith(f"/api/public/results/{result['result_id']}/previews/") for p in venue['personal'] + venue['common'])
    serialized = json.dumps(result)
    for forbidden in ('original', 'object_key', 'embedding', 'similarity', 'task123/', 'presigned', token):
        assert forbidden not in serialized
    path = '/api/public/results/' + result['result_id']
    assert request(backend, 'GET', path)[0] == 401
    assert request(backend, 'GET', path, token='unknown')[0] == 401
    other = cookie(submit(public_fixture)[1])
    assert request(backend, 'GET', path, token=other)[0] == 404
    with Session(engine) as session:
        profile = BrowserSearchProfileRepository(session).find(token); before = profile.last_visit_at
        record = session.scalar(select(PublicSearchResult).where(PublicSearchResult.profile_id == profile.id))
        assert record.venue_ids == venues[:3] and len(record.venues[0]['personal']) == 2
        assert 'similarity' in record.venues[0]['personal'][0]
    code, headers, reread = request(backend, 'GET', path, token=token)
    assert code == 200 and reread == result; security(headers)
    with Session(engine) as session:
        assert BrowserSearchProfileRepository(session).find(token).last_visit_at > before
    fresh = submit(public_fixture, selected=[str(venues[0])], token=token)[2]
    assert request(backend, 'GET', path, token=token)[0] == 404
    assert request(backend, 'GET', '/api/public/results/' + fresh['result_id'], token=token)[2] == fresh
    # Deleting personal Photos removes both personal and corresponding-date common.
    with Session(engine) as session:
        session.get(Photo, personal[0, 2001]).is_active = False; session.commit()
    reread = request(backend, 'GET', '/api/public/results/' + fresh['result_id'], token=token)[2]
    assert reread['personal_count'] == 1 and reread['venues'][0]['dates'] == ['2026-01-01']
    assert len(reread['venues'][0]['common']) == 1


def test_strict_multipart_jpeg_origin_limits_before_inference(public_fixture):
    _, _, app, model, venues, _, _ = public_fixture
    for value in (b'1', b'0', b'True', b'"true"', b'null', b' true '):
        assert submit(public_fixture, confirm=value)[0] == 422
    assert submit(public_fixture, extra=[('other', b'x', None, None)])[0] == 422
    assert submit(public_fixture, extra=[('venue_ids', b'[]', None, None)])[0] == 422
    for image, mime, expected in ((b'corrupt', 'image/jpeg', 422), (jpeg(), 'image/png', 422),
        (jpeg(4097, 4), 'image/jpeg', 422), (jpeg(4, 4097), 'image/jpeg', 422),
        (b'\xff\xd8' + b'x' * (2 * 1024 * 1024), 'image/jpeg', 413)):
        assert submit(public_fixture, image=image, mime=mime)[0] == expected
    body, headers = multipart([str(venues[0])])
    for origin in ('https://foreign', 'null', ''):
        code, h, _ = request(app, 'POST', '/api/public/search', body=body, headers={**headers, 'origin': origin})
        assert code == 403; security(h)
    assert request(app, 'POST', '/api/public/search', body=body, headers=headers, scheme='http')[0] == 403
    assert request(app, 'POST', '/api/public/search', body=b'x' * 2162689, headers=headers)[0] == 413
    assert model.calls == 0
    code, h, _ = submit(public_fixture, confirm=b'false'); assert code == 200
    token = cookie(h)
    state = app.state.role_state
    state['public_search_rate_limiter'] = DisplayClientRateLimiter(limit=1, window_seconds=60)
    assert request(app, 'POST', '/api/public/search', body=body, headers=headers, token=token, peer='127.0.0.2')[0] == 200
    calls = model.calls
    assert request(app, 'POST', '/api/public/search', body=body, headers=headers, token=token, peer='127.0.0.3')[0] == 429
    assert model.calls == calls  # profile budget across different IPs
    state['public_search_rate_limiter'] = DisplayClientRateLimiter(limit=1, window_seconds=60)
    assert submit(public_fixture)[0] == 200
    calls = model.calls
    assert request(app, 'POST', '/api/public/search', body=body, headers=headers, token='changed')[0] == 429
    assert model.calls == calls  # IP budget despite changed/no cookies


def test_failures_and_current_selfie_never_publish_success(public_fixture):
    engine, backend, app, model, venues, _, _ = public_fixture
    code, headers, good = submit(public_fixture); token = cookie(headers)
    path = '/api/public/results/' + good['result_id']
    def persisted():
        with Session(engine) as session:
            p = BrowserSearchProfileRepository(session).find(token)
            return p.a_embedding, p.b_embedding, p.reset_used, len(session.scalars(select(PublicSearchResult)).all())
    before = persisted(); calls = model.calls
    assert _PROCESS_LOCAL_REALTIME_SLOT.acquire(blocking=False)
    try:
        assert submit(public_fixture, token=token)[2] == {'schema_version': 1, 'outcome': 'busy'}
        assert model.calls == calls
    finally:
        _PROCESS_LOCAL_REALTIME_SLOT.release()
    assert persisted() == before
    model.delay = .03; app.state.role_state['realtime_deadline_ms'] = 1
    assert submit(public_fixture, token=token)[2] == {'schema_version': 1, 'outcome': 'deadline'}
    assert persisted() == before
    model.delay = 0; app.state.role_state['realtime_deadline_ms'] = 10000
    model.fail = True
    assert submit(public_fixture, token=token)[0] == 500 and persisted() == before
    model.fail = False
    for faces, quality in ((0, .9), (2, .9), (1, .1)):
        model.faces = faces; model.quality = quality
        assert submit(public_fixture, token=token, confirm=b'true')[2]['outcome'] == 'retake_required'
        assert persisted() == before
    model.faces = 1; model.quality = .9
    # B is valid but has no corpus matches: search must use current vector, not A.
    model.embedding = np.eye(1, 128, k=1, dtype=np.float32)[0]
    assert submit(public_fixture, token=token)[2] == {'schema_version': 1, 'outcome': 'no_matches'}
    fixed = persisted(); assert fixed[1] == model.embedding.tolist() and fixed[3] == before[3]
    model.embedding = np.eye(1, 128, k=2, dtype=np.float32)[0]
    denial = submit(public_fixture, token=token)[2]
    assert denial['outcome'] == 'confirmation_required' and 'result_id' not in denial
    assert persisted() == fixed
    assert submit(public_fixture, token=token, confirm=b'true')[2]['outcome'] == 'no_matches'
    model.embedding = np.eye(1, 128, k=3, dtype=np.float32)[0]
    assert submit(public_fixture, token=token)[2]['outcome'] == 'no_matches'  # post-reset B
    model.embedding = np.eye(1, 128, k=4, dtype=np.float32)[0]
    assert submit(public_fixture, token=token, confirm=b'true')[2]['outcome'] == 'face_denied'
    assert request(backend, 'GET', path, token=token)[2] == good
    app.state.role_state['admitted_pipeline_revision_id'] = uuid.uuid4()
    assert submit(public_fixture, token=token)[0] == 503


def test_slow_search_deadline_rolls_back_profile_and_result(public_fixture, monkeypatch):
    engine, _, app, model, _, _, _ = public_fixture
    original = PublicExactSearchRepository.search
    def late(self, **kwargs):
        result = original(self, **kwargs); time.sleep(.03); return result
    monkeypatch.setattr(PublicExactSearchRepository, 'search', late)
    app.state.role_state['realtime_deadline_ms'] = 20
    assert submit(public_fixture)[2] == {'schema_version': 1, 'outcome': 'deadline'}
    with Session(engine) as session:
        assert session.scalar(select(PublicSearchResult)) is None
        assert session.scalar(select(BrowserSearchProfile)) is None


def test_public_native_and_promo_share_slot_without_waiting_and_keep_qr(public_fixture, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from face_moment.entrypoints import realtime as entrypoint
    from face_moment.serving_control.display_client_access import DisplayClientRepository
    from tests.promo.test_realtime_attempt_integration import _manifest, _multipart, _request, _successful_search_result
    engine, _, app, model, venues, _, _ = public_fixture
    with Session(engine) as session:
        RealtimeContextRepository(session).update_active_visit_date(spa_id=venues[0], active_visit_date=date(2026,1,1))
        client = DisplayClientRepository(session).provision(spa_id=venues[0], name='synthetic Promo competitor')
        token = client.token_value; session.commit()
    app.state.role_state.update(display_client_rate_limiter=DisplayClientRateLimiter(limit=100, window_seconds=60),
        realtime_result_display_ms=10000, realtime_success_cooldown_ms=10000)
    monkeypatch.setattr(entrypoint, 'search_realtime_references', lambda **_: _successful_search_result())
    original = model.inspect_reference_crop
    started, release = threading.Event(), threading.Event()
    def held(*args):
        started.set(); assert release.wait(5); return original(*args)
    monkeypatch.setattr(model, 'inspect_reference_crop', held)
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(submit, public_fixture)
        try:
            assert started.wait(3)
            body, content_type = _multipart(_manifest(uuid.uuid4(), count=2))
            before = time.monotonic()
            result = _request(app, body, content_type, token)
            assert result[0] == 200 and result[2]['outcome'] == 'busy'
            assert time.monotonic()-before < 1 and not release.is_set()
            assert request(app, 'GET', '/healthz')[0] == 200
        finally:
            release.set()
        assert owner.result()[2]['outcome'] == 'result'
    body, content_type = _multipart(_manifest(uuid.uuid4(), count=2))
    result = _request(app, body, content_type, token)
    assert result[0] == 200 and result[2]['outcome'] == 'result'
    assert result[2]['result']['qr_url'].startswith('/q?ticket=')
    assert len(result[2]['result']['teasers']) >= 1


def test_real_https_edge_warmed_native_cookie_origin_and_private_store(tmp_path):
    """Actual Caddy -> two production apps -> warmed SFace/exact PostgreSQL.

    Loopback TLS and synthetic object prefix are cleaned in finally; native
    owner behavior is consumed rather than re-proving its earlier claim.
    """
    import http.client
    import os
    from pathlib import Path
    import socket
    import ssl
    import subprocess
    import uvicorn
    from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
    from face_moment.infrastructure.settings import Settings
    from tests.processing.test_public_selfie_search import _native
    from face_moment.processing.public_selfie_search import prepare_public_selfie
    from face_moment.serving_control.public_search_context import read_public_search_context
    from tests.promo.test_public_edge_routes import _free_port

    settings = Settings.from_env(); ensure_bucket(settings); store = PrivateObjectStore(settings)
    prefix = f'task123-native/{uuid.uuid4().hex}/'; keys = []
    servers = []; threads = []; process = None; log = None
    observations = []
    try:
        with disposable_postgresql_engine('task123_https') as db:
            with Session(db) as session:
                rev, native = _native(session, 'sface')
                venue = IngestTargetRepository(session).configure_public_spa(name='HTTPS synthetic venue', timezone='UTC',
                    serving_pipeline_revision_id=rev.id, is_free=False)
                RealtimeContextRepository(session).provision_reference_settings(spa_id=venue.spa_id,
                    pipeline_code=rev.pipeline_code, reference_threshold=.5, min_query_face_quality=.1,
                    quality_settings={'version':1})
                selfie_image = cv2.imread('tests/client/fixtures/selfie-portrait-small.png')
                encoded = cv2.imencode('.jpg', selfie_image, [cv2.IMWRITE_JPEG_QUALITY,85])[1].tobytes()
                decoded = cv2.imdecode(np.frombuffer(encoded,dtype=np.uint8),cv2.IMREAD_COLOR)
                context = read_public_search_context(session, venue_ids=[venue.spa_id], admitted_pipeline_revision_id=rev.id)
                query = prepare_public_selfie(context=context,engine=native,selfie=decoded).query
                assert query is not None
                photo, _ = _add_photo(session, marker='native-own', spa_id=venue.spa_id, revision_id=rev.id,
                    embedding=tuple(query.embedding), prefix=prefix, phash64=None)
                original_key = session.get(Photo, photo).original_object_key
                keys.append(original_key); original = jpeg(1200,800); store.put(key=original_key,body=original)
                session.commit(); revision_id=rev.id
            backend, realtime = backend_app(), realtime_app()
            backend.state.role_state['session_factory']=lambda: Session(db)
            realtime.state.role_state.update(ready=True,session_factory=lambda:Session(db),model_adapter=native,
                admitted_pipeline_revision_id=revision_id,realtime_deadline_ms=10000,
                public_search_rate_limiter=DisplayClientRateLimiter(limit=100,window_seconds=60))
            backend_port,realtime_port,edge_port=[_free_port() for _ in range(3)]
            for app,port in ((backend,backend_port),(realtime,realtime_port)):
                server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,lifespan='off',access_log=False,
                    log_level='error',proxy_headers=True,forwarded_allow_ips='127.0.0.1'))
                thread=threading.Thread(target=server.run,daemon=True);servers.append(server);threads.append(thread);thread.start()
            binary=tmp_path/'caddy'
            extractor=subprocess.check_output(['docker','create','caddy:2.10.0-alpine'],text=True).strip()
            try:
                subprocess.run(['docker','cp',f'{extractor}:/usr/bin/caddy',str(binary)],check=True,capture_output=True)
            finally:
                subprocess.run(['docker','rm',extractor],check=True,capture_output=True)
            binary.chmod(0o755)
            config=Path('deploy/Caddyfile').read_text().replace('{\n','{\n\tadmin off\n\tauto_https disable_redirects\n\tskip_install_trust\n\tdefault_bind 127.0.0.1\n',1)
            config=config.replace('https://localhost:8443',f'https://localhost:{edge_port}').replace(', https://{$FACE_MOMENT_PUBLIC_HOST:face-moment.ru}:8443','')
            config=config.replace('backend:8000',f'127.0.0.1:{backend_port}').replace('realtime:8002',f'127.0.0.1:{realtime_port}')
            config_path=tmp_path/'Caddyfile';config_path.write_text(config)
            env={**os.environ,'XDG_DATA_HOME':str(tmp_path/'data'),'XDG_CONFIG_HOME':str(tmp_path/'config')}
            log=(tmp_path/'caddy.log').open('w')
            subprocess.run([str(binary),'validate','--config',str(config_path),'--adapter','caddyfile'],env=env,stdout=log,stderr=log,check=True)
            process=subprocess.Popen([str(binary),'run','--config',str(config_path),'--adapter','caddyfile'],env=env,stdout=log,stderr=log)
            origin=f'https://localhost:{edge_port}'
            def https(method,path,body=None,headers=None):
                connection=http.client.HTTPSConnection('localhost',edge_port,context=ssl._create_unverified_context(),timeout=10)
                try:
                    connection.request(method,path,body=body,headers={'Origin':origin,**(headers or {})})
                    response=connection.getresponse(); data=response.read()
                    return response.status,{k.lower():v for k,v in response.getheaders()},json.loads(data) if data else None
                finally:
                    connection.close()
            for _ in range(100):
                try:
                    if https('GET','/api/public/venues')[0]==200:break
                except (OSError,ValueError):pass
                time.sleep(.05)
            else:pytest.fail('isolated HTTPS edge failed to start')
            body,h=multipart([str(venue.spa_id)],image=encoded)
            code,headers,result=https('POST','/api/public/search',body,h)
            assert code==200 and result['outcome']=='result' and result['personal_count']==1
            security(headers); token=cookie(headers)
            assert result['venues'][0]['personal'][0]['id']==str(photo)
            path='/api/public/results/'+result['result_id']
            assert https('GET',path)[0]==401
            assert https('GET',path,headers={'Cookie':f'{COOKIE_NAME}={token}'})[2]==result
            assert https('POST','/api/public/search',body,{**h,'Origin':'https://foreign.invalid'})[0]==403
            assert https('POST','/api/public/search',body,{**h,'Cookie':f'{COOKIE_NAME}={token}'})[2]['outcome']=='result'
            assert store.read(key=original_key)==original and prefix not in json.dumps(result)
            with Session(db) as session:
                assert len(session.scalars(select(PublicSearchResult)).all())==2
                assert len(session.scalars(select(BrowserSearchProfile)).all())==1
            observations.append({'https_edge':'actual deployed Caddyfile on loopback TLS','search_process':'realtime','result_process':'backend',
                'native':'warmed SFace, same admitted revision','personal_count':1,'own_current_read':200,'missing_cookie':401,
                'foreign_origin':403,'cookie_replay':'same persistent profile, 2 successful results','private_original':'unchanged, key absent from public JSON'})
    finally:
        if process is not None:
            process.terminate();process.wait(timeout=5)
        if log is not None:log.close()
        for server in servers:server.should_exit=True
        for thread in threads:thread.join(timeout=5)
        for key in keys:store.delete(key=key)
        assert not store.list_keys(prefix=prefix)
    Path('.tasks/TASK-123-T3-FT-013-W6/native-https-observations.json').write_text(json.dumps(observations,indent=2)+'\n')

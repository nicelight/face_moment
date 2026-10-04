"""Protected gallery media, isolated owner state and private MinIO bytes."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import threading
import uuid

from PIL import Image
import pytest
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from tests.promo.test_public_search_api import public_fixture, submit, cookie, security, jpeg


async def media_request(app, path, token=None, scheme='https'):
    messages = []
    async def receive():
        return {'type':'http.request','body':b'', 'more_body':False}
    async def send(message):
        messages.append(message)
    headers = [(b'host', b'localhost')]
    from face_moment.promo.browser_search_profile import COOKIE_NAME
    if token is not None:
        headers.append((b'cookie', f'{COOKIE_NAME}={token}'.encode()))
    await app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'GET',
        'scheme':scheme,'path':path,'raw_path':path.encode(),'query_string':b'','root_path':'',
        'headers':headers,'client':('127.0.0.1',1),'server':('localhost',443)}, receive, send)
    start = next(m for m in messages if m['type']=='http.response.start')
    return start['status'], {k.decode():v.decode() for k,v in start['headers']}, b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')


@pytest.fixture
def gallery_fixture(public_fixture):
    engine, backend, _, _, _, personal, common = public_fixture
    settings = Settings.from_env(); ensure_bucket(settings); store = PrivateObjectStore(settings)
    keys = []; originals = {}
    executor = ThreadPoolExecutor(max_workers=1)
    backend.state.role_state.update(public_preview_executor=executor, public_preview_slot=threading.Lock(), public_preview_store=store)
    try:
        with Session(engine) as session:
            for i, year in ((0,2001),(0,2026),(1,2001)):
                for photo_id in (personal[i,year], common[i,year]):
                    key = session.get(Photo,photo_id).original_object_key
                    original = jpeg(1200,800) if year==2026 else jpeg(60,40)
                    keys.append(key); originals[photo_id] = original; store.put(key=key,body=original)
            from face_moment.processing.persistence import PhotoPipelineState
            for state in session.query(PhotoPipelineState).filter_by(photo_id=common[0,2001]):
                state.preview_phash64_v1=None
            session.commit()
        code, headers, result = submit(public_fixture)
        assert code==200
        yield public_fixture, result, cookie(headers), store, originals
    finally:
        executor.shutdown(wait=True)
        for key in keys:store.delete(key=key)
        for key in keys:assert not store.list_keys(prefix=key)


def preview_path(result, photo):
    return f"/api/public/results/{result['result_id']}/previews/{photo}"


def test_own_personal_and_historical_no_faces_reduced_private_bytes(gallery_fixture):
    fixture, result, token, store, originals = gallery_fixture
    engine, backend, _, _, _, personal, common = fixture
    from face_moment.processing.persistence import PhotoPipelineState
    historical=common[0,2001]
    with Session(engine) as session:
        before=[(p.status,p.preview_object_key,p.thumbnail_object_key,p.preview_phash64_v1,p.status_changed_at) for p in session.query(PhotoPipelineState).filter_by(photo_id=historical)]
    for photo in (personal[0,2001], personal[0,2026], common[0,2001]):
        status, headers, body = asyncio.run(media_request(backend,preview_path(result,photo),token))
        assert status==200, f'protected preview expected 200, observed {status}'
        security(headers); assert headers['content-type']=='image/jpeg'
        assert headers['x-content-type-options']=='nosniff'
        with Image.open(BytesIO(body)) as decoded:
            assert decoded.format=='JPEG' and decoded.size==(640,427)
        assert body != originals[photo]
        assert b'original_object_key' not in body and b'X-Amz-' not in body
        with Session(engine) as session:
            key=session.get(Photo,photo).original_object_key
            assert key.encode() not in body and key not in str(headers)
            assert store.read(key=key)==originals[photo]
    with Session(engine) as session:
        after=[(p.status,p.preview_object_key,p.thumbnail_object_key,p.preview_phash64_v1,p.status_changed_at) for p in session.query(PhotoPipelineState).filter_by(photo_id=historical)]
    assert before==after and before[0][:4]==('no_faces',None,None,None)


def test_scope_missing_deleted_foreign_and_current_membership(gallery_fixture):
    fixture, result, token, store, originals = gallery_fixture
    engine, backend, _, _, _, personal, common = fixture
    path = preview_path(result, personal[0,2001])
    def status(path=path, auth=token, scheme='https'):
        code,h,_=asyncio.run(media_request(backend,path,auth,scheme));security(h);return code
    assert status(auth=None)==401 and status(auth='unknown')==401
    assert status(scheme='http')==403
    other = cookie(submit(fixture)[1])
    assert status(auth=other)==404
    assert status(preview_path(result,uuid.uuid4()))==404
    assert status('/api/public/results/bad/previews/bad')==404
    # Existing active Photo outside the result's selected scope.
    narrow = submit(fixture,selected=[str(fixture[4][0])],token=token)[2]
    assert status()==404  # old own result is no longer current
    assert status(preview_path(narrow,personal[1,2001]))==404
    with Session(engine) as session:
        session.get(Photo,personal[0,2001]).is_active=False;session.commit()
    assert status(preview_path(narrow,personal[0,2001]))==404
    assert status(preview_path(narrow,common[0,2001]))==404  # personal date gone
    with Session(engine) as session:
        key=session.get(Photo,personal[0,2026]).original_object_key
    store.delete(key=key)
    assert status(preview_path(narrow,personal[0,2026]))==404
    store.put(key=key,body=b'corrupt original')
    assert status(preview_path(narrow,personal[0,2026]))==404


def test_exif_orientation_and_original_metadata_not_exposed(gallery_fixture):
    fixture, result, token, store, _ = gallery_fixture
    engine,backend,_,_,_,personal,_=fixture
    source=BytesIO(); image=Image.new('RGB',(1200,800),(220,30,20)); exif=Image.Exif()
    exif[274]=6;exif[270]='private original annotation'
    image.save(source,'JPEG',exif=exif)
    with Session(engine) as session:key=session.get(Photo,personal[0,2026]).original_object_key
    store.put(key=key,body=source.getvalue())
    status,_,body=asyncio.run(media_request(backend,preview_path(result,personal[0,2026]),token))
    assert status==200
    with Image.open(BytesIO(body)) as image:assert image.size==(640,960) and not image.getexif()
    assert b'private original annotation' not in body
    assert store.read(key=key)==source.getvalue()


def test_single_executor_busy_retry_event_loop_and_cancel(gallery_fixture):
    fixture,result,token,store,_=gallery_fixture
    _,backend,_,_,_,personal,_=fixture
    entered=threading.Event(); release=threading.Event(); original_read=store.read
    class SlowStore:
        def read(self,*,key):
            entered.set(); assert release.wait(5); return original_read(key=key)
    backend.state.role_state['public_preview_store']=SlowStore()
    path=preview_path(result,personal[0,2026])
    async def scenario():
        task=asyncio.create_task(media_request(backend,path,token))
        for _ in range(100):
            if entered.is_set():break
            await asyncio.sleep(.01)
        assert entered.is_set()
        # A blocked object read must leave the event loop and health route usable.
        assert (await asyncio.wait_for(media_request(backend,'/healthz'),1))[0]==200
        code,h,_=await asyncio.wait_for(media_request(backend,path,token),1)
        assert code==429;security(h)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert (await media_request(backend,path,token))[0]==429
        release.set()
        for _ in range(100):
            if not backend.state.role_state['public_preview_slot'].locked():break
            await asyncio.sleep(.01)
        assert (await media_request(backend,path,token))[0]==200
    try:asyncio.run(scenario())
    finally:release.set()


def test_actual_caddy_https_canonical_preview(gallery_fixture,tmp_path):
    import http.client
    import json
    import os
    from pathlib import Path
    import ssl
    import subprocess
    import time
    import uvicorn
    from face_moment.promo.browser_search_profile import COOKIE_NAME
    from tests.promo.test_public_edge_routes import _free_port
    fixture,result,token,store,originals=gallery_fixture
    _,backend,_,_,_,personal,common=fixture
    backend_port,edge_port=_free_port(),_free_port()
    server=uvicorn.Server(uvicorn.Config(backend,host='127.0.0.1',port=backend_port,
        lifespan='off',access_log=False,log_level='error',proxy_headers=True,forwarded_allow_ips='127.0.0.1'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    process=None;log=None;observations=[]
    try:
        binary=tmp_path/'caddy'
        container=subprocess.check_output(['docker','create','caddy:2.10.0-alpine'],text=True).strip()
        try:subprocess.run(['docker','cp',f'{container}:/usr/bin/caddy',str(binary)],check=True,capture_output=True)
        finally:subprocess.run(['docker','rm',container],check=True,capture_output=True)
        binary.chmod(0o755)
        config=Path('deploy/Caddyfile').read_text().replace('{\n','{\n\tadmin off\n\tauto_https disable_redirects\n\tskip_install_trust\n\tdefault_bind 127.0.0.1\n',1)
        config=config.replace('https://localhost:8443',f'https://localhost:{edge_port}').replace(', https://{$FACE_MOMENT_PUBLIC_HOST:face-moment.ru}:8443','')
        config=config.replace('backend:8000',f'127.0.0.1:{backend_port}').replace('realtime:8002',f'127.0.0.1:{_free_port()}')
        config_path=tmp_path/'Caddyfile';config_path.write_text(config)
        env={**os.environ,'XDG_DATA_HOME':str(tmp_path/'data'),'XDG_CONFIG_HOME':str(tmp_path/'config')}
        log=(tmp_path/'caddy.log').open('w')
        subprocess.run([str(binary),'validate','--config',str(config_path),'--adapter','caddyfile'],env=env,stdout=log,stderr=log,check=True)
        process=subprocess.Popen([str(binary),'run','--config',str(config_path),'--adapter','caddyfile'],env=env,stdout=log,stderr=log)
        def https(path,auth=None):
            connection=http.client.HTTPSConnection('localhost',edge_port,context=ssl._create_unverified_context(),timeout=5)
            try:
                connection.request('GET',path,headers={} if auth is None else {'Cookie':f'{COOKIE_NAME}={auth}'})
                response=connection.getresponse();return response.status,{k.lower():v for k,v in response.getheaders()},response.read()
            finally:connection.close()
        for _ in range(100):
            try:
                if https('/api/public/venues')[0]==200:break
            except OSError:pass
            time.sleep(.05)
        else:pytest.fail('isolated TLS edge did not start')
        for photo in (personal[0,2026],common[0,2001]):
            path=preview_path(result,photo)
            assert https(path)[0]==401
            code,h,body=https(path,token);assert code==200;security(h)
            with Image.open(BytesIO(body)) as image:assert image.size==(640,427)
            assert body!=originals[photo]
            observations.append({'route':'GET /api/public/results/{current_id}/previews/{member_id}',
                'edge':'actual repository Caddyfile isolated loopback TLS','upstream':'backend',
                'kind':'personal' if photo==personal[0,2026] else 'historical no_faces',
                'status':code,'decoded_dimensions':[640,427],'missing_cookie':401,
                'original_bytes_exposed':False,'cache_control':h['cache-control'],'referrer_policy':h['referrer-policy']})
        assert https(preview_path(result,uuid.uuid4()),token)[0]==404
    finally:
        if process is not None:process.terminate();process.wait(timeout=5)
        if log is not None:log.close()
        server.should_exit=True;thread.join(timeout=5)
    artifact=Path('.tasks/TASK-124-T3-FT-013-W7/https-observations.json')
    artifact.parent.mkdir(exist_ok=True);artifact.write_text(json.dumps(observations,indent=2)+'\n')

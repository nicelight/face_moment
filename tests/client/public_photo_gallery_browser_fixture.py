"""Native public HTTP/owner state, disposable PG, loopback HTTPS; controlled inference."""
import json
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
import numpy as np
import uvicorn
from tests.promo.test_public_search_api import public_fixture
from face_moment.promo.realtime_orchestration import _PROCESS_LOCAL_REALTIME_SLOT

generator = public_fixture.__wrapped__()
try:
    engine, backend, realtime, model, venues, personal, common = next(generator)
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    from face_moment.infrastructure.settings import Settings
    from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
    from face_moment.inventory.photo_persistence import Photo
    from face_moment.processing.persistence import PhotoFace
    from PIL import Image
    from io import BytesIO
    settings = Settings.from_env(); ensure_bucket(settings); store = PrivateObjectStore(settings)
    keys = []; executor = ThreadPoolExecutor(max_workers=1)
    backend.state.role_state.update(public_preview_executor=executor, public_preview_slot=threading.Lock(), public_preview_store=store)
    with Session(engine) as session:
        # Venue 2 has Photos but no current-selfie matches; no arbitrary common grants.
        for row in session.query(PhotoFace).filter(PhotoFace.photo_id.in_([personal[2,y] for y in (2001,2026)])):
            row.embedding = np.eye(1,128,k=1,dtype=np.float32)[0].tolist()
        for photo_id in list(personal.values()) + list(common.values()):
            key=session.get(Photo,photo_id).original_object_key
            image=Image.open('tests/client/fixtures/selfie-portrait-small.png').convert('RGB').resize((1200,1400))
            encoded=BytesIO();image.save(encoded,'JPEG');store.put(key=key,body=encoded.getvalue());keys.append(key)
        session.commit()
    busy = False
    async def app(scope, receive, send):
        global busy
        if scope['type'] == 'http' and scope['path'] == '/__fixture':
            body = b''
            while True:
                msg = await receive(); body += msg.get('body', b'')
                if not msg.get('more_body'): break
            config = json.loads(body)
            model.embedding = np.eye(1, 128, k=config.get('vector', 0), dtype=np.float32)[0]
            model.delay = config.get('delay', 0); model.fail = config.get('fail', False)
            model.faces = config.get('faces', 1)
            realtime.state.role_state['realtime_deadline_ms'] = config.get('deadline_ms', 10000)
            if busy: _PROCESS_LOCAL_REALTIME_SLOT.release(); busy = False
            if config.get('busy'): busy = _PROCESS_LOCAL_REALTIME_SLOT.acquire(blocking=False)
            await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'application/json')]})
            await send({'type': 'http.response.body', 'body': b'{}'})
        else:
            target = realtime if scope.get('path') == '/api/public/search' else backend
            await target(scope, receive, send)
    with tempfile.TemporaryDirectory(prefix='task126_tls_') as directory:
        key = str(Path(directory)/'key.pem'); cert = str(Path(directory)/'cert.pem')
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',key,'-out',cert,'-days','1','-subj','/CN=localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0)); listener.listen(128)
            server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off',ssl_keyfile=key,ssl_certfile=cert))
            worker=threading.Thread(target=server.run,kwargs={'sockets':[listener]});worker.start()
            print(json.dumps({'url':f'https://127.0.0.1:{listener.getsockname()[1]}'}),flush=True)
            try: sys.stdin.readline()
            finally:
                if busy: _PROCESS_LOCAL_REALTIME_SLOT.release()
                server.should_exit=True;worker.join(timeout=15)
finally:
    if 'executor' in globals(): executor.shutdown(wait=True)
    if 'keys' in globals():
        for key in keys: store.delete(key=key)
        for key in keys: assert not store.list_keys(prefix=key)
    generator.close()
print('DISPOSABLE_DB_CLEANED',flush=True)

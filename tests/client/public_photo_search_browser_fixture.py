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
    engine, backend, realtime, model, venues, _, _ = next(generator)
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
    with tempfile.TemporaryDirectory(prefix='task125_tls_') as directory:
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
finally: generator.close()
print('DISPOSABLE_DB_CLEANED',flush=True)

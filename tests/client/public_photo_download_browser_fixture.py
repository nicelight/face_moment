"""Native public HTTP/owner state, disposable PG, loopback HTTPS; controlled inference."""
import json
import socket
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from sqlalchemy.orm import Session
import numpy as np
import uvicorn
from tests.promo.test_public_search_api import public_fixture
from face_moment.promo.realtime_orchestration import _PROCESS_LOCAL_REALTIME_SLOT

generator = public_fixture.__wrapped__()
try:
    engine, backend, realtime, model, venues, personal, common = next(generator)
    from concurrent.futures import ThreadPoolExecutor
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
    from decimal import Decimal
    from face_moment.serving_control.photo_tariff import PhotoTariff
    from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
    with Session(engine) as session:
        session.add(PhotoTariff(id=1, base_kopecks=Decimal(101), d1=Decimal(".5"), d2=Decimal(".3"), d3=Decimal(".1"), updated_at=datetime.now(timezone.utc)))
        session.commit()
    backend.state.role_state["public_quote_rate_limiter"] = DisplayClientRateLimiter(limit=1000, window_seconds=60)
    from face_moment.promo.photo_archive_executor import PhotoArchiveExecutor
    from face_moment.promo.photo_orders import PhotoOrder
    gate = threading.Event()
    archive_fail = False
    mails = []
    provider_requests = []
    provider_payments = {}
    provider_status = 'pending'
    checkout_base = ''
    class ProviderHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            key = self.headers['Idempotence-Key']
            provider_requests.append({'key': key, 'payload': payload})
            if key not in provider_payments:
                provider_payments[key] = {'id': str(uuid.uuid4()), 'amount': payload['amount'],
                    'metadata': payload['metadata']}
            payment = provider_payments[key]
            body = json.dumps({**payment, 'status': 'pending',
                'confirmation': {'type': 'redirect', 'confirmation_url': f'{checkout_base}/__provider/checkout/{key}'}}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(body)
        def do_GET(self):
            payment = next((p for p in provider_payments.values() if self.path.endswith('/' + p['id'])), None)
            if payment is None: self.send_error(404); return
            body = json.dumps({**payment, 'status': provider_status, 'paid': provider_status == 'succeeded'}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_args): pass
    provider_server = ThreadingHTTPServer(('127.0.0.1', 0), ProviderHandler)
    provider_thread = threading.Thread(target=provider_server.serve_forever, daemon=True)
    provider_thread.start()
    class ArchiveStore:
        def read(self, *, key):
            if not key.startswith('photo-archives/'):
                gate.wait(timeout=20)
                if archive_fail: raise OSError('synthetic archive IO failure')
            return store.read(key=key)
        def put(self, **kwargs): return store.put(**kwargs)
        def delete(self, **kwargs): return store.delete(**kwargs)
    class FakeMail:
        def notify(self, identity): mails.append(str(identity))
    archive_executor = PhotoArchiveExecutor(lambda: Session(engine), ArchiveStore(), FakeMail())
    backend.state.role_state.update(photo_archive_signing_secret='task136-isolated-secret',
        public_order_rate_limiter=DisplayClientRateLimiter(limit=1000, window_seconds=60))
    archive_executor.start()
    busy = False
    async def app(scope, receive, send):
        global busy, archive_fail, provider_status
        if scope['type'] == 'http' and scope['path'] == '/__fixture':
            body = b''
            while True:
                msg = await receive(); body += msg.get('body', b'')
                if not msg.get('more_body'): break
            config = json.loads(body)
            archive_fail = config.get('archive_fail', archive_fail)
            provider_status = config.get('provider_status', provider_status)
            if config.get('change_settings') or config.get('new_paid_tariff') or config.get('reset_settings') or config.get('expire_last'):
                from face_moment.serving_control.ingest_target import Spa
                with Session(engine) as session:
                    if config.get('change_settings'):
                        session.get(PhotoTariff, 1).base_kopecks = Decimal(999)
                        session.get(Spa, venues[0]).is_free = True
                    if config.get('new_paid_tariff'):
                        session.get(PhotoTariff, 1).base_kopecks = Decimal(999)
                    if config.get('reset_settings'):
                        session.get(PhotoTariff, 1).base_kopecks = Decimal(101)
                        session.get(Spa, venues[0]).is_free = False
                    if config.get('expire_last'):
                        latest = session.query(PhotoOrder).order_by(PhotoOrder.created_at.desc()).first()
                        latest.ready_at = datetime.now(timezone.utc) - timedelta(days=4)
                    session.commit()
            if config.get('release'): gate.set()
            if config.get('block'): gate.clear()
            model.embedding = np.eye(1, 128, k=config.get('vector', 0), dtype=np.float32)[0]
            model.delay = config.get('delay', 0); model.fail = config.get('fail', False)
            model.faces = config.get('faces', 1)
            realtime.state.role_state['realtime_deadline_ms'] = config.get('deadline_ms', 10000)
            if busy: _PROCESS_LOCAL_REALTIME_SLOT.release(); busy = False
            if config.get('busy'): busy = _PROCESS_LOCAL_REALTIME_SLOT.acquire(blocking=False)
            await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'application/json')]})
            with Session(engine) as session:
                orders = [{'id':str(o.id), 'status':o.archive_status, 'client_request_id':o.client_request_id,
                    'photo_ids':[i['photo_id'] for i in o.items], 'total':int(o.total_kopecks),
                    'email':o.email, 'method':o.payment_method, 'provider':o.provider_payment_id,
                    'payment_status':o.payment_status, 'items':o.items}
                    for o in session.query(PhotoOrder).order_by(PhotoOrder.created_at)]
                from face_moment.promo.browser_search_profile import BrowserSearchProfile
                profiles = [{'email': p.email, 'last_visit_at': p.last_visit_at.isoformat() if p.last_visit_at else None}
                    for p in session.query(BrowserSearchProfile)]
            await send({'type': 'http.response.body', 'body': json.dumps({'orders':orders,'profiles':profiles,
                'mail_count':len(mails),'provider_requests':provider_requests}).encode()})
        elif scope['type'] == 'http' and scope['path'].startswith('/__provider/checkout/'):
            body = b'<a href="/?payment_return=1" id="return-to-site">Return to Face Moment</a>'
            await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'text/html')]})
            await send({'type':'http.response.body','body':body})
        else:
            target = realtime if scope.get('path') == '/api/public/search' else backend
            await target(scope, receive, send)
    with tempfile.TemporaryDirectory(prefix='task136_tls_') as directory:
        key = str(Path(directory)/'key.pem'); cert = str(Path(directory)/'cert.pem')
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',key,'-out',cert,'-days','1','-subj','/CN=localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0)); listener.listen(128)
            checkout_base = f'https://127.0.0.1:{listener.getsockname()[1]}'
            from face_moment.infrastructure.yookassa_payments import YooKassaPayments
            from face_moment.promo.photo_payment import PhotoPaymentInitiator, PhotoPaymentConfirmer
            provider = YooKassaPayments('fake-shop', 'fake-secret',
                endpoint=f'http://127.0.0.1:{provider_server.server_port}/v3/payments')
            backend.state.role_state['photo_payment_initiator'] = PhotoPaymentInitiator(
                lambda: Session(engine), store, provider, return_url=f'{checkout_base}/?payment_return=1',
                receipt_description='Оказание цифровых услуг', receipt_vat_code=1,
                receipt_payment_subject='service', receipt_payment_mode='full_payment', receipt_tax_system_code=None)
            backend.state.role_state['photo_payment_confirmer'] = PhotoPaymentConfirmer(lambda: Session(engine), provider)
            server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off',ssl_keyfile=key,ssl_certfile=cert))
            worker=threading.Thread(target=server.run,kwargs={'sockets':[listener]});worker.start()
            print(json.dumps({'url':f'https://127.0.0.1:{listener.getsockname()[1]}'}),flush=True)
            try: sys.stdin.readline()
            finally:
                if busy: _PROCESS_LOCAL_REALTIME_SLOT.release()
                server.should_exit=True;worker.join(timeout=15)
finally:
    if 'provider_server' in globals(): provider_server.shutdown(); provider_server.server_close()
    if 'provider_thread' in globals(): provider_thread.join(timeout=5)
    if 'gate' in globals(): gate.set()
    if 'archive_executor' in globals(): archive_executor.stop()
    if 'store' in globals():
        with Session(engine) as session:
            identities = [o.id for o in session.query(PhotoOrder)]
        for identity in identities:
            for archive_key in store.list_keys(prefix=f'photo-archives/{identity}/'): store.delete(key=archive_key)
            assert not store.list_keys(prefix=f'photo-archives/{identity}/')
    if 'executor' in globals(): executor.shutdown(wait=True)
    if 'keys' in globals():
        for key in keys: store.delete(key=key)
        for key in keys: assert not store.list_keys(prefix=key)
    generator.close()
print('DISPOSABLE_DB_CLEANED',flush=True)

"""TASK-138: actual payment routes, fake HTTP provider, disposable DB/private objects."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import base64
import json
import threading
import uuid
from zipfile import ZipFile

import pytest
from sqlalchemy.orm import Session

from face_moment.infrastructure.yookassa_payments import YooKassaPayments
from face_moment.inventory.photo_persistence import Photo
from face_moment.promo.photo_payment import PhotoPaymentConfirmer, PhotoPaymentInitiator
from face_moment.promo.photo_orders import PhotoOrder
from tests.promo.test_photo_archive_delivery import request as archive_request
from tests.promo.test_photo_order_http import order_http
from tests.promo.test_photo_quote import quote_fixture
from tests.promo.test_public_search_api import public_fixture


@pytest.fixture
def confirmation_http(order_http):
    fixture, call, payload, foreign = order_http
    engine, app, _, _, paid, free, store, _ = fixture
    provider_payments = {}
    observations = []
    failure = {'get_status': 200}

    class ProviderHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            sent = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            key = self.headers['Idempotence-Key']
            payment = provider_payments.setdefault(key, {
                'id': f'fake-{key}', 'status': 'pending', 'paid': False,
                'amount': sent['amount'], 'metadata': sent['metadata'],
                'confirmation': {'type': 'redirect', 'confirmation_url': 'https://pay.example.test/form'},
            })
            self.reply(200, payment)

        def do_GET(self):
            payment_id = self.path.removeprefix('/v3/payments/')
            observations.append((payment_id, self.headers.get('Authorization')))
            payment = next((value for value in provider_payments.values() if value['id'] == payment_id), None)
            self.reply(failure['get_status'] if payment is not None else 404, payment or {})

        def reply(self, status, value):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), ProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    provider = YooKassaPayments('fake-shop', 'fake-secret',
        endpoint=f'http://127.0.0.1:{server.server_port}/v3/payments')
    app.state.role_state['photo_payment_initiator'] = PhotoPaymentInitiator(
        lambda: Session(engine), store, provider,
        return_url='https://face-moment.example.test/site',
        receipt_description='Оказание цифровых услуг', receipt_vat_code=1,
        receipt_payment_subject='service', receipt_payment_mode='full_payment',
        receipt_tax_system_code=None)
    app.state.role_state['photo_payment_confirmer'] = PhotoPaymentConfirmer(lambda: Session(engine), provider)
    try:
        yield fixture, call, payload, foreign, provider_payments, observations, failure
    finally:
        app.state.role_state.pop('photo_payment_initiator', None)
        app.state.role_state.pop('photo_payment_confirmer', None)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def ready_payment(confirmation_http, *, photo_ids=None):
    fixture, call, payload, _, provider_payments, _, _ = confirmation_http
    engine, app, _, _, paid, free, store, _ = fixture
    selected = paid[:2] + free[:1] if photo_ids is None else photo_ids
    created = call('POST', payload=payload(selected, email='synthetic@example.test', payment_method='bank_card'))
    assert created[0] == 200
    identity = created[2]['id']
    key = f'photo-archives/{identity}/selected.zip'
    archive_bytes = BytesIO()
    with Session(engine) as session, ZipFile(archive_bytes, 'w') as archive:
        order = session.get(PhotoOrder, uuid.UUID(identity))
        for item in order.items:
            source = session.get(Photo, uuid.UUID(item['photo_id'])).original_object_key
            archive.writestr(f'{item["photo_id"]}.jpg', store.read(key=source))
    body = archive_bytes.getvalue()
    store.put(key=key, body=body)
    ready_at = datetime.now(timezone.utc) - timedelta(days=1)
    with Session(engine) as session:
        order = session.get(PhotoOrder, uuid.UUID(identity))
        order.archive_status = 'ready'
        order.archive_object_key = key
        order.ready_at = ready_at
        session.commit()
    result = call('POST', f'/api/public/orders/{identity}/payment', payload={})
    assert result[0] == 200
    assert provider_payments[identity]['id'] == f'fake-{identity}'
    return identity, key, body, ready_at


def webhook(call, payment_id, *, event='payment.succeeded', object_fields=None, **options):
    return call('POST', '/api/public/payments/yookassa',
        payload={'type': 'notification', 'event': event,
                 'object': {'id': payment_id, **(object_fields or {})}}, **options)


def test_ac003_full_yookassa_notification_uses_only_id_for_server_truth(confirmation_http):
    fixture, call, _, _, provider_payments, observations, _ = confirmation_http
    engine, _, _, _, _, _, _, _ = fixture
    identity, _, _, _ = ready_payment(confirmation_http)
    payment = provider_payments[identity]
    payment_object = {
        'status': 'succeeded', 'paid': True,
        'amount': {'value': '999.00', 'currency': 'USD'},
        'metadata': {'order_id': str(uuid.uuid4())},
        'created_at': '2026-10-05T00:00:00.000Z',
        'payment_method': {'type': 'bank_card', 'id': payment['id'], 'saved': False},
        'refundable': False, 'test': True,
    }
    assert webhook(call, payment['id'], object_fields=payment_object,
                   auth=None, origin='https://foreign')[0] == 200
    with Session(engine) as fresh:
        assert fresh.get(PhotoOrder, uuid.UUID(identity)).payment_status == 'pending'
    assert observations and observations[-1][0] == payment['id']
    payment['status'] = 'succeeded'
    payment['paid'] = True
    # The notification can be stale or forged; only the authenticated GET result wins.
    payment_object['status'] = 'canceled'
    payment_object['paid'] = False
    assert webhook(call, payment['id'], event='payment.canceled',
                   object_fields=payment_object, auth=None, origin='https://foreign')[0] == 200
    with Session(engine) as fresh:
        order = fresh.get(PhotoOrder, uuid.UUID(identity))
        assert order.payment_status == 'succeeded' and order.paid_at is not None
        paid_at = order.paid_at
    observed_gets = len(observations)
    assert webhook(call, payment['id'], object_fields=payment_object, auth=None)[0] == 200
    assert len(observations) == observed_gets
    with Session(engine) as fresh:
        assert fresh.get(PhotoOrder, uuid.UUID(identity)).paid_at == paid_at


def test_ac003_only_authenticated_server_truth_changes_payment_once(confirmation_http):
    fixture, call, _, foreign, provider_payments, observations, failure = confirmation_http
    engine, app, _, _, _, _, _, _ = fixture
    identity, _, _, _ = ready_payment(confirmation_http)
    payment = provider_payments[identity]
    path = f'/api/public/orders/{identity}'
    assert call('GET', path)[2]['payment_status'] == 'pending'
    assert 'download_url' not in call('GET', path)[2]
    assert webhook(call, payment['id'], auth=None, origin='https://foreign')[0] == 200
    with Session(engine) as session:
        assert session.get(PhotoOrder, uuid.UUID(identity)).payment_status == 'pending'
    assert webhook(call, 'foreign-payment', auth=None)[0] == 200
    assert webhook(call, payment['id'], event='payment.canceled', auth=None)[0] == 200
    payment['status'] = 'succeeded'
    payment['paid'] = True
    payment['amount'] = {'value': '999.00', 'currency': 'RUB'}
    assert webhook(call, payment['id'], auth=None)[0] == 200
    assert call('GET', path)[2]['payment_status'] == 'pending'
    payment['amount'] = {'value': '1.52', 'currency': 'USD'}
    assert webhook(call, payment['id'], auth=None)[0] == 200
    payment['amount'] = {'value': '1.52', 'currency': 'RUB'}
    payment['metadata'] = {'order_id': str(uuid.uuid4())}
    assert webhook(call, payment['id'], auth=None)[0] == 200
    payment['metadata'] = {'order_id': identity}
    payment['paid'] = False
    assert webhook(call, payment['id'], auth=None)[0] == 200
    assert call('GET', path)[2]['payment_status'] == 'pending'
    payment['paid'] = True
    failure['get_status'] = 503
    assert webhook(call, payment['id'], auth=None)[0] >= 500
    failure['get_status'] = 200
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = list(pool.map(lambda _: webhook(call, payment['id'], auth=None)[0], range(4)))
    assert codes == [200] * 4
    assert webhook(call, payment['id'], event='payment.canceled', auth=None)[0] == 200
    with Session(engine) as fresh:
        order = fresh.get(PhotoOrder, uuid.UUID(identity))
        assert order.payment_status == 'succeeded' and order.paid_at is not None
        paid_at = order.paid_at
        assert fresh.query(PhotoOrder).count() == 1
    failure['get_status'] = 503
    assert webhook(call, payment['id'], auth=None)[0] == 200
    failure['get_status'] = 200
    assert call('GET', path)[2]['payment_status'] == 'succeeded'
    with Session(engine) as fresh:
        assert fresh.get(PhotoOrder, uuid.UUID(identity)).paid_at == paid_at
    expected_auth = 'Basic ' + base64.b64encode(b'fake-shop:fake-secret').decode()
    assert observations and all(value == expected_auth for _, value in observations)
    assert all(payment_id == payment['id'] or payment_id == 'foreign-payment'
               for payment_id, _ in observations)


def test_ac004_owner_refresh_then_bearer_delivery_preserves_ready_deadline(confirmation_http):
    fixture, call, _, foreign, provider_payments, _, _ = confirmation_http
    engine, app, _, _, _, _, store, _ = fixture
    identity, key, body, ready_at = ready_payment(confirmation_http)
    payment = provider_payments[identity]
    path = f'/api/public/orders/{identity}'
    assert call('GET', path, auth=foreign)[0] == 404
    assert call('GET', path, auth=None)[0] == 401
    assert 'download_url' not in call('GET', path)[2]
    canceled_id, _, _, _ = ready_payment(confirmation_http)
    provider_payments[canceled_id]['status'] = 'canceled'
    canceled = call('GET', f'/api/public/orders/{canceled_id}')
    assert canceled[2]['payment_status'] == 'canceled' and 'download_url' not in canceled[2]
    payment['status'] = 'succeeded'
    payment['paid'] = True
    confirmed = call('GET', path)
    assert confirmed[0] == 200 and confirmed[2]['payment_status'] == 'succeeded'
    link = confirmed[2]['download_url']
    app.state.role_state['photo_archive_clock'] = lambda: ready_at + timedelta(days=3) - timedelta(microseconds=1)
    assert archive_request(app, link, peer='127.0.0.2')[0:3:2] == (200, body)
    with ZipFile(BytesIO(body)) as archive, Session(engine) as fresh:
        order = fresh.get(PhotoOrder, uuid.UUID(identity))
        assert archive.namelist() == [f'{item["photo_id"]}.jpg' for item in order.items]
        for item in order.items:
            source = fresh.get(Photo, uuid.UUID(item['photo_id'])).original_object_key
            assert archive.read(f'{item["photo_id"]}.jpg') == store.read(key=source)
    assert archive_request(app, link.replace('token=', 'token=forged'), peer='127.0.0.2')[0] == 404
    app.state.role_state['photo_archive_clock'] = lambda: ready_at + timedelta(days=3)
    assert archive_request(app, link, peer='127.0.0.2')[0] == 410
    with Session(engine) as fresh:
        order = fresh.get(PhotoOrder, uuid.UUID(identity))
        assert order.ready_at == ready_at and order.payment_status == 'succeeded'
    app.state.role_state['photo_archive_clock'] = lambda: ready_at + timedelta(days=2)
    store.delete(key=key)
    code, _, unavailable, _ = archive_request(app, link, peer='127.0.0.2')
    assert code == 404 and 'поддержку' in json.loads(unavailable)['detail']
    assert call('GET', path)[2]['payment_status'] == 'succeeded'

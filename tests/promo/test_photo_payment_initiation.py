"""TASK-137 AC-002 payment initiation through the registered public route."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import asyncio
import json
import os
from pathlib import Path
import threading
import time
import uuid
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pytest
from sqlalchemy.orm import Session

from face_moment.infrastructure.yookassa_payments import YooKassaPayments
from face_moment.infrastructure.settings import Settings
from face_moment.entrypoints import backend
from face_moment.promo.browser_search_profile import BrowserSearchProfile
from face_moment.promo.photo_payment import PaymentProviderError, PhotoPaymentInitiator
from face_moment.promo.photo_orders import PhotoOrder
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from face_moment.serving_control.ingest_target import Spa
from face_moment.serving_control.photo_tariff import PhotoTariff
from tests.promo.test_photo_order_http import order_http
from tests.promo.test_photo_quote import quote_fixture
from tests.promo.test_public_search_api import public_fixture


@pytest.fixture
def payment_http(order_http):
    fixture, call, payload, foreign = order_http
    engine, app, _, _, paid, free, store, profile_id = fixture
    seen = []
    by_key = {}
    behavior = {'status': 200, 'sleep_seconds': 0.0, 'corrupt_metadata': False}

    class ProviderHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers['Content-Length'])
            request = json.loads(self.rfile.read(length))
            key = self.headers['Idempotence-Key']
            seen.append((key, request, self.headers['Authorization']))
            time.sleep(behavior['sleep_seconds'])
            if behavior['status'] != 200:
                self.send_response(behavior['status'])
                self.end_headers()
                self.wfile.write(b'{"type":"error"}')
                return
            if key not in by_key:
                by_key[key] = {'id': str(uuid.uuid4()), 'status': 'pending',
                    'amount': request['amount'], 'metadata': request['metadata'],
                    'confirmation': {'type': 'redirect',
                        'confirmation_url': f'https://yookassa.ru/checkout/payments/{key}'}}
            result = dict(by_key[key])
            if behavior['corrupt_metadata']:
                result['metadata'] = {'order_id': str(uuid.uuid4())}
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

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
    try:
        yield fixture, call, payload, foreign, seen, by_key, behavior
    finally:
        app.state.role_state.pop('photo_payment_initiator', None)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def make_ready(payment_http, *, method='bank_card', ids=None, email='frozen@example.test'):
    fixture, call, payload, _, _, _, _ = payment_http
    engine, _, _, _, paid, free, store, _ = fixture
    selection = ids if ids is not None else paid[:6] + free[:2]
    created = call('POST', payload=payload(selection, email=email, payment_method=method))
    assert created[0] == 200
    identity = created[2]['id']
    key = f'photo-archives/{identity}/selected.zip'
    store.put(key=key, body=b'synthetic ready archive')
    with Session(engine) as session:
        order = session.get(PhotoOrder, uuid.UUID(identity))
        order.archive_status = 'ready'
        order.archive_object_key = key
        order.ready_at = datetime.now(timezone.utc)
        session.commit()
    return identity, key


@pytest.mark.parametrize('method', ['bank_card', 'sbp'])
def test_ready_paid_archive_reaches_payment_route_with_frozen_receipt(payment_http, method):
    fixture, call, _, _, seen, by_key, _ = payment_http
    engine, _, token, _, _, _, _, profile_id = fixture
    identity, _ = make_ready(payment_http, method=method)
    with Session(engine) as session:
        session.get(BrowserSearchProfile, profile_id).email = 'changed@example.test'
        session.get(PhotoTariff, 1).base_kopecks = Decimal(999)
        frozen = session.get(PhotoOrder, uuid.UUID(identity))
        session.get(Spa, uuid.UUID(frozen.items[0]['venue_id'])).is_free = True
        session.commit()
    status, _, body = call('POST', f'/api/public/orders/{identity}/payment', payload={})
    assert status == 200, f'FT-016-AC-002 ready paid payment initiation expected 200, observed {status}'
    assert body == {'schema_version': 1,
        'confirmation_url': f'https://yookassa.ru/checkout/payments/{identity}'}
    assert len(seen) == 1
    key, sent, authorization = seen[0]
    assert key == identity and authorization == 'Basic ' + base64.b64encode(b'fake-shop:fake-secret').decode()
    assert sent['capture'] is True and sent['amount'] == {'value': '3.35', 'currency': 'RUB'}
    assert sent['payment_method_data'] == {'type': method}
    assert sent['confirmation'] == {'type': 'redirect', 'return_url': 'https://face-moment.example.test/site'}
    assert sent['metadata'] == {'order_id': identity}
    receipt = sent['receipt']
    assert receipt['customer'] == {'email': 'frozen@example.test'}
    assert len(receipt['items']) == 3
    assert [(item['amount']['value'], item['quantity']) for item in receipt['items']] == [
        ('1.01', '1'), ('0.51', '4'), ('0.30', '1')]
    assert all(item['description'] == 'Оказание цифровых услуг' and item['vat_code'] == 1 and
        item['payment_subject'] == 'service' and item['payment_mode'] == 'full_payment'
        for item in receipt['items'])
    assert sum(int(Decimal(item['amount']['value']) * 100) * int(item['quantity'])
               for item in receipt['items']) == 335
    assert 'tax_system_code' not in receipt
    with Session(engine) as fresh_session:
        persisted = fresh_session.get(PhotoOrder, uuid.UUID(identity))
        assert persisted.provider_payment_id == by_key[key]['id']
        assert persisted.payment_requested_at is not None
        assert persisted.payment_idempotence_key == identity
        assert persisted.payment_status == 'pending'
    assert call('POST', f'/api/public/orders/{identity}/payment', payload={})[2] == body
    assert len(seen) == 2 and seen[1][0] == key and seen[1][1] == sent


def test_invalid_or_unready_orders_never_reach_provider(payment_http):
    fixture, call, payload, foreign, seen, _, _ = payment_http
    engine, app, _, _, paid, free, store, _ = fixture
    identity, key = make_ready(payment_http)
    path = f'/api/public/orders/{identity}/payment'
    assert call('POST', path, payload={}, auth=foreign)[0] == 404
    assert call('POST', path, payload={}, auth=None)[0] == 401
    assert call('POST', path, payload={}, origin='https://foreign')[0] == 403
    assert call('POST', path, payload={'amount': 1})[0] == 422
    assert call('POST', path, raw=b'{')[0] == 422
    assert call('POST', f'/api/public/orders/{uuid.uuid4()}/payment', payload={})[0] == 404
    assert call('POST', f'/api/public/orders/not-a-uuid/payment', payload={})[0] == 404
    free_id = call('POST', payload=payload(free))[2]['id']
    with Session(engine) as session:
        free_order = session.get(PhotoOrder, uuid.UUID(free_id))
        free_order.archive_status = 'ready'
        free_order.ready_at = datetime.now(timezone.utc)
        free_order.archive_object_key = key
        session.commit()
    assert call('POST', f'/api/public/orders/{free_id}/payment', payload={})[0] == 409
    for state in ('requested', 'preparing', 'failed'):
        with Session(engine) as session:
            session.get(PhotoOrder, uuid.UUID(identity)).archive_status = state
            session.commit()
        assert call('POST', path, payload={})[0] == 409
    with Session(engine) as session:
        order = session.get(PhotoOrder, uuid.UUID(identity))
        order.archive_status = 'ready'
        order.ready_at = datetime.now(timezone.utc) - timedelta(days=3)
        session.commit()
    assert call('POST', path, payload={})[0] == 409
    with Session(engine) as session:
        session.get(PhotoOrder, uuid.UUID(identity)).ready_at = datetime.now(timezone.utc)
        session.commit()
    store.delete(key=key)
    assert call('POST', path, payload={})[0] == 409
    app.state.role_state['public_order_rate_limiter'] = DisplayClientRateLimiter(limit=1, window_seconds=60)
    assert call('POST', f'/api/public/orders/{uuid.uuid4()}/payment', payload={})[0] == 404
    assert call('POST', f'/api/public/orders/{uuid.uuid4()}/payment', payload={})[0] == 429
    assert not seen


def test_provider_failure_replay_and_expired_idempotency_window(payment_http):
    fixture, call, _, _, seen, by_key, behavior = payment_http
    engine, _, _, _, _, _, _, _ = fixture
    identity, _ = make_ready(payment_http)
    path = f'/api/public/orders/{identity}/payment'
    behavior['status'] = 500
    assert call('POST', path, payload={})[0] == 502
    with Session(engine) as session:
        order = session.get(PhotoOrder, uuid.UUID(identity))
        assert order.payment_requested_at is not None and order.provider_payment_id is None
    behavior['status'] = 200
    behavior['sleep_seconds'] = .25
    initiator = fixture[1].state.role_state['photo_payment_initiator']
    initiator.provider.timeout_seconds = .05
    assert call('POST', path, payload={})[0] == 502
    behavior['sleep_seconds'] = 0
    initiator.provider.timeout_seconds = 10
    assert call('POST', path, payload={})[0] == 200
    assert len(seen) == 3 and {row[0] for row in seen} == {identity}
    assert seen[0][1] == seen[1][1] == seen[2][1]
    with Session(engine) as session:
        order = session.get(PhotoOrder, uuid.UUID(identity))
        assert order.provider_payment_id == by_key[identity]['id']
        order.payment_requested_at = datetime.now(timezone.utc) - timedelta(hours=24)
        session.commit()
    assert call('POST', path, payload={})[0] == 503
    assert len(seen) == 3


def test_missing_provider_configuration_and_concurrent_replay(payment_http):
    fixture, call, _, _, seen, by_key, _ = payment_http
    engine, app, _, _, _, _, store, _ = fixture
    identity, _ = make_ready(payment_http)
    path = f'/api/public/orders/{identity}/payment'
    original = app.state.role_state['photo_payment_initiator']
    app.state.role_state['photo_payment_initiator'] = PhotoPaymentInitiator(
        lambda: Session(engine), store, YooKassaPayments(None, None),
        return_url=None, receipt_description=None, receipt_vat_code=None,
        receipt_payment_subject=None, receipt_payment_mode=None,
        receipt_tax_system_code=None)
    assert call('POST', path, payload={})[0] == 503
    with Session(engine) as session:
        assert session.get(PhotoOrder, uuid.UUID(identity)).payment_requested_at is None
    assert not seen
    app.state.role_state['photo_payment_initiator'] = original
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: call('POST', path, payload={}), range(2)))
    assert [result[0] for result in results] == [200, 200]
    assert results[0][2] == results[1][2]
    assert len(seen) == 2 and {key for key, _, _ in seen} == {identity}
    assert len(by_key) == 1


def test_four_receipt_groups_and_provider_correlation_rejection(payment_http):
    fixture, call, _, _, seen, _, behavior = payment_http
    _, _, _, _, paid, free, _, _ = fixture
    identity, _ = make_ready(payment_http, ids=paid[:21] + free)
    path = f'/api/public/orders/{identity}/payment'
    behavior['corrupt_metadata'] = True
    assert call('POST', path, payload={})[0] == 502
    behavior['corrupt_metadata'] = False
    assert call('POST', path, raw=b'')[0] == 200
    assert len(seen) == 2 and seen[0][0] == seen[1][0] == identity
    receipt_items = seen[1][1]['receipt']['items']
    assert len(receipt_items) == 4
    assert sum(int(Decimal(item['amount']['value']) * 100) * int(item['quantity'])
               for item in receipt_items) == 765


def test_backend_lifespan_binds_real_adapter_from_runtime_settings(quote_fixture, monkeypatch):
    engine, _, _, _, _, _, _, _ = quote_fixture
    monkeypatch.setenv('YOOKASSA_SHOP_ID', 'synthetic-shop')
    monkeypatch.setenv('YOOKASSA_SECRET_KEY', 'synthetic-key')
    monkeypatch.setenv('YOOKASSA_RETURN_URL', 'https://face-moment.example.test/site')
    monkeypatch.setenv('YOOKASSA_RECEIPT_DESCRIPTION', 'Оказание цифровых услуг')
    monkeypatch.setenv('YOOKASSA_RECEIPT_VAT_CODE', '1')
    monkeypatch.setenv('YOOKASSA_RECEIPT_PAYMENT_SUBJECT', 'service')
    monkeypatch.setenv('YOOKASSA_RECEIPT_PAYMENT_MODE', 'full_payment')
    async def probe():
        app = backend.create_app()
        async with app.router.lifespan_context(app):
            initiator = app.state.role_state['photo_payment_initiator']
            assert isinstance(initiator.provider, YooKassaPayments)
            assert initiator.provider.configured()
            assert initiator.return_url == 'https://face-moment.example.test/site'
        assert 'photo_payment_initiator' not in app.state.role_state
    asyncio.run(probe())


@pytest.mark.skipif(os.environ.get('YOOKASSA_TEST_JOIN') != '1', reason='explicit TEST shop join only')
def test_external_test_shop_card_redirect_and_frozen_receipt(order_http):
    """Authorized TEST call; persist only redacted observations, never credentials/URL."""
    fixture, call, payload, _ = order_http
    engine, app, _, _, paid, free, store, _ = fixture
    settings = Settings.from_env()
    assert settings.yookassa_shop_id and settings.yookassa_secret_key
    assert settings.yookassa_return_url
    basic = base64.b64encode(f'{settings.yookassa_shop_id}:{settings.yookassa_secret_key}'.encode()).decode()
    me_request = Request('https://api.yookassa.ru/v3/me',
        headers={'Authorization': f'Basic {basic}'})
    with urlopen(me_request, timeout=10) as response:
        shop = json.loads(response.read(65537))
    assert shop.get('test') is True, 'External join is limited to a TEST shop'

    class RecordingYooKassa(YooKassaPayments):
        sent = None
        issue = None

        def create_payment(self, *, idempotence_key, payload):
            self.sent = payload
            try:
                return super().create_payment(idempotence_key=idempotence_key, payload=payload)
            except PaymentProviderError as error:
                cause = error.__cause__
                if isinstance(cause, HTTPError):
                    try:
                        detail = json.loads(cause.read(2048))
                    except (ValueError, OSError):
                        detail = {}
                    self.issue = {'http_status': cause.code,
                        'provider_code': detail.get('code'),
                        'parameter': detail.get('parameter')}
                raise

    provider = RecordingYooKassa(settings.yookassa_shop_id, settings.yookassa_secret_key)
    app.state.role_state['photo_payment_initiator'] = PhotoPaymentInitiator(
        lambda: Session(engine), store, provider,
        return_url=settings.yookassa_return_url,
        receipt_description=settings.yookassa_receipt_description,
        receipt_vat_code=settings.yookassa_receipt_vat_code,
        receipt_payment_subject=settings.yookassa_receipt_payment_subject,
        receipt_payment_mode=settings.yookassa_receipt_payment_mode,
        receipt_tax_system_code=settings.yookassa_receipt_tax_system_code)
    created = call('POST', payload=payload(paid[:2] + free[:1],
        email='receipt@face-moment.test', payment_method='bank_card'))
    assert created[0] == 200
    identity = created[2]['id']
    key = f'photo-archives/{identity}/selected.zip'
    store.put(key=key, body=b'synthetic TEST archive; not personal media')
    with Session(engine) as session:
        order = session.get(PhotoOrder, uuid.UUID(identity))
        order.archive_status = 'ready'
        order.archive_object_key = key
        order.ready_at = datetime.now(timezone.utc)
        session.commit()
    code, _, body = call('POST', f'/api/public/orders/{identity}/payment', payload={})
    observation = {'http_status': code, 'provider_error': provider.issue,
        'method': 'bank_card', 'frozen_amount_rub': '1.52',
        'frozen_receipt_groups': 2,
        'test_shop_me': True,
        'me_fiscalization_present': isinstance(shop.get('fiscalization'), dict),
        'me_legacy_fiscalization_enabled': shop.get('fiscalization_enabled'),
        'receipt_registration_verified': False}
    if code == 200:
        with Session(engine) as session:
            provider_id = session.get(PhotoOrder, uuid.UUID(identity)).provider_payment_id
        assert provider_id
        get = Request(f'https://api.yookassa.ru/v3/payments/{provider_id}',
            headers={'Authorization': f'Basic {basic}'})
        with urlopen(get, timeout=10) as response:
            remote = json.loads(response.read(65537))
        receipt = provider.sent['receipt']
        receipt_items = receipt['items']
        frozen_receipt_matches = (
            receipt['customer']['email'] == 'receipt@face-moment.test' and
            [(item['amount']['value'], item['quantity']) for item in receipt_items]
                == [('1.01', '1'), ('0.51', '1')] and
            all(item['description'] == 'Оказание цифровых услуг' and
                item['vat_code'] == 1 and item['payment_subject'] == 'service' and
                item['payment_mode'] == 'full_payment' for item in receipt_items))
        observation.update(test_shop=remote.get('test') is True,
            provider_payment_id=provider_id,
            remote_status=remote.get('status'),
            remote_amount_matches=remote.get('amount') == {'value': '1.52', 'currency': 'RUB'},
            remote_order_matches=remote.get('metadata', {}).get('order_id') == identity,
            redirect_host=urlsplit(body['confirmation_url']).hostname,
            redirect_host_accepted=urlsplit(body['confirmation_url']).hostname in
                {'yookassa.ru', 'yoomoney.ru'},
            frozen_receipt_payload_sent=frozen_receipt_matches,
            receipt_registration=remote.get('receipt_registration', 'absent'))
        observation['receipt_registration_verified'] = remote.get('receipt_registration') == 'succeeded'
    artifact = Path('.tasks/TASK-137-T3-FT-016-W12/test-shop-card-observation.json')
    artifact.write_text(json.dumps(observation, ensure_ascii=False, indent=2) + '\n')
    artifact.chmod(0o600)
    assert code == 200, f'YooKassa TEST create failed: {provider.issue}'
    assert observation['test_shop'] and observation['remote_amount_matches']
    assert observation['remote_order_matches'] and observation['redirect_host_accepted']
    assert observation['frozen_receipt_payload_sent']

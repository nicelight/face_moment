"""AC-003 bearer route against disposable PostgreSQL and private MinIO."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import uuid
from urllib.parse import quote

import asyncio
import json
from urllib.parse import urlsplit
import pytest
from sqlalchemy.orm import Session

from face_moment.entrypoints import backend
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.promo.photo_orders import PhotoOrder
from tests.promo.test_photo_quote import quote_fixture
from tests.promo.test_public_search_api import public_fixture
from tests.promo.test_photo_orders import create

SECRET = 'isolated-archive-hmac-secret'
READY = datetime(2026, 10, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)
ZIP_BYTES = b'PK\x03\x04' + b'private archive fixture' * 8000


def signature(identity, ready=READY, secret=SECRET):
    message = f'{identity}\n{ready.astimezone(timezone.utc).isoformat(timespec="microseconds")}'
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


@pytest.fixture
def delivery_fixture(quote_fixture, monkeypatch):
    engine, _, _, _, paid, free, store, _ = quote_fixture
    monkeypatch.setenv('PHOTO_ARCHIVE_SIGNING_SECRET', SECRET)
    keys = []
    def add(*, payment='not_required', status='ready'):
        is_paid = payment != 'not_required'
        identity = create(quote_fixture, request_id=uuid.uuid4().hex,
            ids=paid[:1] if is_paid else free[:1],
            **({'email':'synthetic@example.test','payment_method':'sbp'} if is_paid else {}))
        key = f'task134/{uuid.uuid4().hex}/archive.zip'; keys.append(key)
        store.put(key=key, body=ZIP_BYTES)
        with Session(engine) as session:
            order = session.get(PhotoOrder, identity)
            order.archive_status = status; order.ready_at = READY
            order.archive_object_key = key; order.payment_status = payment
            session.commit()
        return identity, key
    app = backend.create_app()
    app.state.role_state.update(session_factory=lambda: Session(engine),
        public_preview_store=store, photo_archive_signing_secret=SECRET,
        photo_archive_clock=lambda: READY + timedelta(days=3) - timedelta(microseconds=1))
    try:
        yield app, add, engine, store, quote_fixture
    finally:
        for key in keys:
            store.delete(key=key)
            assert not store.exists(key=key)


def url(identity, token=None):
    return f'/api/public/archives/{identity}?token={signature(identity) if token is None else token}'


def request(app, path, *, peer='127.0.0.1', scheme='https'):
    parts = urlsplit(path); messages = []
    async def receive():
        return {'type':'http.request','body':b'', 'more_body':False}
    async def send(message): messages.append(message)
    scope = {'type':'http','asgi':{'version':'3.0','spec_version':'2.4'},
        'http_version':'1.1','method':'GET','scheme':scheme,'path':parts.path,
        'raw_path':parts.path.encode(),'query_string':parts.query.encode(),
        'root_path':'','headers':[(b'host',b'localhost')],
        'client':(peer,1),'server':('localhost',443)}
    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m['type']=='http.response.start')
    chunks = [m.get('body',b'') for m in messages if m['type']=='http.response.body' and m.get('body')]
    return start['status'], {k.decode():v.decode() for k,v in start['headers']}, b''.join(chunks), chunks


def security_headers(headers):
    assert headers['cache-control'] == 'no-store'
    assert headers['referrer-policy'] == 'no-referrer'
    assert 'set-cookie' not in headers


def test_no_cookie_private_zip_route_and_exact_expiry(delivery_fixture):
    app, add, _, _, _ = delivery_fixture
    identity, _ = add()
    status, headers, body, chunks = request(app, url(identity))
    assert status == 200, f'FT-015-AC-003 bearer route expected ZIP 200, observed {status}: {body}'
    assert body == ZIP_BYTES and len(chunks) > 1
    assert headers['content-type'] == 'application/zip'
    assert headers['content-disposition'] == f'attachment; filename="photos-{identity}.zip"'
    security_headers(headers)
    # Second independent anonymous client, no cookie/device identity.
    assert request(app, url(identity), peer='127.0.0.2')[2] == ZIP_BYTES
    for delta in (timedelta(0), timedelta(microseconds=1)):
        app.state.role_state['photo_archive_clock'] = lambda: READY + timedelta(days=3) + delta
        status, headers, body, _ = request(app, url(identity))
        assert status == 410 and ZIP_BYTES not in body
        security_headers(headers)


@pytest.mark.parametrize('payment,expected', [('not_required',200),('pending',404),('canceled',404),('succeeded',200)])
def test_stored_entitlement_and_signer(delivery_fixture, payment, expected):
    from face_moment.promo.photo_archive_delivery import archive_download_url
    app, add, engine, _, _ = delivery_fixture
    identity, _ = add(payment=payment)
    with Session(engine) as session:
        order = session.get(PhotoOrder, identity)
        link = archive_download_url(order, secret=SECRET, now=READY)
        assert link == (url(identity) if expected == 200 else None)
        assert archive_download_url(order, secret=SECRET, now=READY+timedelta(days=3)) is None
    code, headers, body, _ = request(app, url(identity))
    assert code == expected
    assert (body == ZIP_BYTES) == (expected == 200)
    security_headers(headers)


def test_forgery_binding_nonready_missing_deleted_and_privacy(delivery_fixture, caplog):
    from botocore import UNSIGNED
    from botocore.config import Config
    import boto3
    app, add, engine, store, fixture = delivery_fixture
    identity, key = add(); other, _ = add()
    for path in (url(identity, 'forged'), url(identity, signature(other)),
                 url(identity, signature(identity, READY+timedelta(microseconds=1))),
                 url(identity, signature(identity, secret='other-secret')),
                 url(identity, quote('подделка')), f'/api/public/archives/{identity}',
                 url(uuid.uuid4()), url('invalid')):
        code, headers, body, _ = request(app, path)
        assert code == 404 and ZIP_BYTES not in body
        assert key.encode() not in body and SECRET.encode() not in body
        security_headers(headers)
    with Session(engine) as session:
        session.get(PhotoOrder, identity).ready_at = READY+timedelta(microseconds=1)
        session.commit()
    assert request(app, url(identity))[0] == 404
    with Session(engine) as session:
        session.get(PhotoOrder, identity).ready_at = READY; session.commit()
    for status in ('requested','preparing','failed'):
        with Session(engine) as session:
            session.get(PhotoOrder, identity).archive_status = status; session.commit()
        assert request(app, url(identity))[0] == 404
    with Session(engine) as session:
        session.get(PhotoOrder, identity).archive_status = 'ready'; session.commit()
    store.delete(key=key)
    code, headers, body, _ = request(app, url(identity))
    assert code == 404 and 'поддержку' in json.loads(body)['detail']
    assert key.encode() not in body
    security_headers(headers)
    assert request(app, url(other), scheme='http')[0] == 403
    # No original HTTP route and unauthenticated raw private-store access is denied.
    with Session(engine) as session:
        original = session.get(Photo, fixture[5][0]).original_object_key
    assert request(app, f'/api/public/originals/{fixture[5][0]}')[0] == 404
    settings = Settings.from_env()
    anonymous = boto3.client('s3', endpoint_url=settings.s3_endpoint_url,
        region_name='us-east-1', config=Config(signature_version=UNSIGNED))
    from botocore.exceptions import ClientError
    for object_key in (original, key):
        with pytest.raises(ClientError) as error:
            anonymous.get_object(Bucket=settings.s3_bucket, Key=object_key)
        assert error.value.response['ResponseMetadata']['HTTPStatusCode'] == 403
    assert signature(identity) not in caplog.text and key not in caplog.text and SECRET not in caplog.text


def test_config_secret_composition_and_query_logging_policy(monkeypatch):
    from face_moment.entrypoints import common
    import uvicorn
    monkeypatch.setenv('PHOTO_ARCHIVE_SIGNING_SECRET', SECRET)
    settings = Settings.from_env()
    assert settings.photo_archive_signing_secret == SECRET
    assert settings.photo_archive_signing_secret != settings.promo_qr_ticket_secret
    calls = []
    monkeypatch.setattr(uvicorn, 'run', lambda *args, **kwargs: calls.append(kwargs))
    common.run(backend.create_app(), 8000)
    assert calls[0]['access_log'] is False
    monkeypatch.delenv('PHOTO_ARCHIVE_SIGNING_SECRET')
    assert Settings.from_env().photo_archive_signing_secret is None


def test_actual_backend_lifecycle_binds_secret_and_private_stream(delivery_fixture):
    app, add, _, _, _ = delivery_fixture
    identity, _ = add()
    async def probe():
        async with app.router.lifespan_context(app):
            assert app.state.role_state['photo_archive_signing_secret'] == SECRET
            from face_moment.promo.photo_archive_delivery import archive_download_url
            with app.state.role_state['session_factory']() as session:
                link = archive_download_url(session.get(PhotoOrder, identity), secret=SECRET,
                                            now=READY)
            app.state.role_state['photo_archive_clock'] = lambda: READY
            # Real ASGI transport in same event loop, with no browser identity.
            messages = []
            parts = urlsplit(link)
            async def receive(): return {'type':'http.request','body':b'','more_body':False}
            async def send(message): messages.append(message)
            await app({'type':'http','asgi':{'version':'3.0','spec_version':'2.4'},
                'http_version':'1.1','method':'GET','scheme':'https','path':parts.path,
                'raw_path':parts.path.encode(),'query_string':parts.query.encode(),
                'root_path':'','headers':[(b'host',b'localhost')],
                'client':('127.0.0.2',1),'server':('localhost',443)}, receive, send)
            assert next(m['status'] for m in messages if m['type']=='http.response.start') == 200
            assert b''.join(m.get('body',b'') for m in messages) == ZIP_BYTES
        assert 'photo_archive_signing_secret' not in app.state.role_state
    asyncio.run(probe())

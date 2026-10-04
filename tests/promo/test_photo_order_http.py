"""AC-001 public order HTTP/core join on disposable PostgreSQL/private MinIO."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import http.client
import json
import threading
import time
import uuid

import pytest
from sqlalchemy.orm import Session
import uvicorn

from face_moment.entrypoints import backend
from face_moment.promo.browser_search_profile import BrowserSearchProfile, COOKIE_NAME
from face_moment.promo.photo_orders import PhotoOrder
from face_moment.promo.public_photo_search import PublicSearchResult
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from tests.promo.test_photo_quote import quote_fixture
from tests.promo.test_public_search_api import public_fixture, security, request as asgi_request
from tests.promo.test_public_edge_routes import _free_port

SECRET = 'task135-isolated-signing-secret'


@pytest.fixture
def order_http(quote_fixture, monkeypatch):
    engine, app, token, result, paid, free, store, profile = quote_fixture
    monkeypatch.setenv('PHOTO_ARCHIVE_SIGNING_SECRET', SECRET)
    app.state.role_state.update(photo_archive_signing_secret=SECRET,
        public_order_rate_limiter=DisplayClientRateLimiter(limit=1000, window_seconds=60))
    foreign = uuid.uuid4().hex
    with Session(engine) as session:
        session.add(BrowserSearchProfile(cookie_digest=hashlib.sha256(foreign.encode()).hexdigest(),
            last_visit_at=datetime.now(timezone.utc), reset_used=False))
        session.commit()
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, lifespan='off',
        access_log=False, log_level='error', proxy_headers=True, forwarded_allow_ips='127.0.0.1'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    for _ in range(100):
        if server.started: break
        time.sleep(.02)
    else: pytest.fail('isolated backend HTTP did not start')
    def call(method, path='/api/public/orders', *, payload=None, auth=token, origin='https://localhost', scheme='https', raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        headers = {'Host':'localhost', 'Origin':origin, 'Content-Type':'application/json', 'X-Forwarded-Proto':scheme}
        if auth is not None: headers['Cookie'] = f'{COOKIE_NAME}={auth}'
        try:
            connection.request(method, path, body=raw if raw is not None else json.dumps(payload), headers=headers)
            response = connection.getresponse()
            return response.status, {k.lower():v for k,v in response.getheaders()}, json.loads(response.read())
        finally: connection.close()
    def payload(ids=None, **extra):
        return {'result_id':str(result), 'photo_ids':[str(i) for i in (free if ids is None else ids)],
                'client_request_id':uuid.uuid4().hex, **extra}
    try:
        yield quote_fixture, call, payload, foreign
    finally:
        server.should_exit = True; thread.join(timeout=5)
        with Session(engine) as session:
            identities = [o.id for o in session.query(PhotoOrder)]
        for identity in identities:
            for key in store.list_keys(prefix=f'photo-archives/{identity}/'): store.delete(key=key)
            assert not store.list_keys(prefix=f'photo-archives/{identity}/')


def test_free_actual_http_core_commit_replay_conflict(order_http):
    fixture, call, payload, _ = order_http
    engine, _, _, _, _, free, _, profile = fixture
    data = payload()
    code, headers, content = call('POST', payload=data)
    assert code == 200, f'.memory-bank/features/FT-015.md#FT-015-AC-001 expected public order 200, observed {code}: {content}'
    security(headers)
    assert content == {'schema_version':1, 'id':content['id'], 'archive_status':'requested', 'total_kopecks':0}
    identity = uuid.UUID(content['id'])
    with Session(engine) as session:
        order = session.get(PhotoOrder, identity)
        assert order.profile_id == profile and order.email is None and order.payment_method is None
        assert {i['photo_id'] for i in order.items} == {str(i) for i in free}
        assert order.provider_payment_id is None and order.payment_requested_at is None
        assert order.payment_status == 'not_required'
    assert call('POST', payload=data)[2] == content
    code, headers, _ = call('POST', payload={**data, 'photo_ids':[str(free[0])]})
    assert code == 409; security(headers)
    with Session(engine) as session: assert session.query(PhotoOrder).count() == 1
    code, headers, status = call('GET', f'/api/public/orders/{identity}')
    assert code == 200 and status['archive_status'] == 'requested' and status['payment_status'] == 'not_required'
    assert 'download_url' not in status
    security(headers)


def test_strict_admission_origin_profile_and_paid_bypass(order_http):
    fixture, call, payload, foreign = order_http
    engine, _, _, _, paid, free, _, _ = fixture
    valid = payload()
    for data in [None, [], {}, {**valid,'result_id':True}, {**valid,'result_id':'bad'},
                 {**valid,'photo_ids':True}, {**valid,'photo_ids':[True]}, {**valid,'photo_ids':['bad']},
                 {**valid,'photo_ids':[str(free[0])]*2}, {**valid,'client_request_id':True},
                 {**valid,'client_request_id':' '}, {**valid,'total_kopecks':0}, {**valid,'is_free':True},
                 {**valid,'email':True}, {**valid,'payment_method':True}, {**valid,'payment_method':'cash'},
                 payload(paid[:1]), payload(paid[:1], email='bad', payment_method='sbp')]:
        code,h,content=call('POST',payload=data); assert code==422, (data,code,content); security(h)
    for raw in (b'{', b'\xff'):
        code,h,_=call('POST',raw=raw); assert code==422; security(h)
    for auth in (None,'unknown'):
        code,h,_=call('POST',payload=valid,auth=auth);assert code==401;security(h)
        code,h,_=call('GET',f'/api/public/orders/{uuid.uuid4()}',auth=auth);assert code==401;security(h)
    for options in ({'origin':'https://foreign'}, {'origin':''}, {'scheme':'http'}):
        code,h,_=call('POST',payload=valid,**options);assert code==403;security(h)
    code,h,_=call('GET',f'/api/public/orders/{uuid.uuid4()}',scheme='http');assert code==403;security(h)
    for data, auth in [(valid,foreign), ({**valid,'result_id':str(uuid.uuid4())},fixture[2]),
                       ({**valid,'photo_ids':[str(uuid.uuid4())]},fixture[2])]:
        code,h,content=call('POST',payload=data,auth=auth);assert code==404;security(h)
        assert 'object_key' not in json.dumps(content)
    with Session(engine) as session: assert session.query(PhotoOrder).count()==0


def test_owner_status_safe_error_and_entitled_signer(order_http, caplog):
    fixture, call, payload, foreign = order_http
    engine, _, _, _, paid, _, store, _ = fixture
    free_id = call('POST',payload=payload())[2]['id']
    paid_id = call('POST',payload=payload(paid[:1], email='synthetic@example.test', payment_method='bank_card'))[2]['id']
    for identity in (free_id,paid_id):
        for auth in (foreign,None,'unknown'):
            code,h,content=call('GET',f'/api/public/orders/{identity}',auth=auth)
            assert code==(404 if auth==foreign else 401);security(h)
            assert 'download_url' not in content and 'items' not in content
    for identity in ('bad',str(uuid.uuid4())):
        code,h,_=call('GET',f'/api/public/orders/{identity}');assert code==404;security(h)
    key = f'photo-archives/{free_id}/selected.zip'; store.put(key=key,body=b'private archive synthetic')
    for state in ('preparing','failed','ready'):
        with Session(engine) as session:
            order=session.get(PhotoOrder,uuid.UUID(free_id));order.archive_status=state
            order.archive_failure_reason=f'unsafe {key} {SECRET}'
            order.ready_at=datetime.now(timezone.utc);order.archive_object_key=key;session.commit()
        code,h,content=call('GET',f'/api/public/orders/{free_id}');assert code==200;security(h)
        serialized=json.dumps(content)
        assert key not in serialized and SECRET not in serialized and 'archive_object_key' not in serialized
        assert ('retry_after_seconds' in content)==(state=='preparing')
        if state=='preparing':assert content['retry_after_seconds']==30
        assert ('error' in content)==(state=='failed')
        assert ('download_url' in content)==(state=='ready')
        if state=='ready':assert content['download_url'].startswith(f'/api/public/archives/{free_id}?token=')
    with Session(engine) as session:
        order=session.get(PhotoOrder,uuid.UUID(paid_id));order.archive_status='ready';order.ready_at=datetime.now(timezone.utc)
        order.archive_object_key=key;session.commit()
    for payment in ('pending','canceled','succeeded'):
        with Session(engine) as session:
            session.get(PhotoOrder,uuid.UUID(paid_id)).payment_status=payment;session.commit()
        content=call('GET',f'/api/public/orders/{paid_id}')[2]
        assert ('download_url' in content)==(payment=='succeeded')
    assert call('POST',f'/api/public/orders/{paid_id}/payment',payload={})[0]==404
    assert key not in caplog.text and SECRET not in caplog.text
    with Session(engine) as session:
        assert all(o.provider_payment_id is None and o.payment_requested_at is None for o in session.query(PhotoOrder))


def test_ip_and_profile_limits_include_reads(order_http):
    fixture, call, payload, _ = order_http
    _,app,token,*_=fixture
    app.state.role_state['public_order_rate_limiter']=DisplayClientRateLimiter(limit=1,window_seconds=60)
    identity=call('POST',payload=payload())[2]['id']
    for method,options in [('GET',{}),('POST',{'auth':'another-profile'})]:
        code,h,_=call(method,f'/api/public/orders/{identity}' if method=='GET' else '/api/public/orders',payload=payload(),**options)
        assert code==429;security(h)
    # ASGI second IP proves the independently shared profile bucket.
    code,h,_=asgi_request(app,'GET',f'/api/public/orders/{identity}',token=token,peer='127.0.0.2')
    assert code==429;security(h)


@pytest.mark.parametrize('method',['bank_card','sbp'])
def test_canonical_paid_request_preserved_without_provider(order_http, method):
    fixture, call, payload, _ = order_http
    engine, _, _, _, paid, _, _, _ = fixture
    code,h,content=call('POST',payload=payload(paid[:1],email='receipt@example.test',payment_method=method))
    assert code==200 and content['total_kopecks']==101;security(h)
    with Session(engine) as session:
        order=session.get(PhotoOrder,uuid.UUID(content['id']))
        assert order.email=='receipt@example.test' and order.payment_method==method
        assert order.provider_payment_id is None and order.payment_requested_at is None


def test_backend_configured_executor_to_owner_ready_link(order_http):
    fixture, call, payload, _=order_http
    engine, _, token, _, _, _, store, _=fixture
    identity=call('POST',payload=payload())[2]['id']
    async def probe():
        app=backend.create_app()
        async with app.router.lifespan_context(app):
            assert 'public_order_rate_limiter' in app.state.role_state
            for _ in range(250):
                with Session(engine) as session:
                    ready=session.get(PhotoOrder,uuid.UUID(identity)).archive_status=='ready'
                if ready:break
                await asyncio.sleep(.02)
            assert ready
            content=await asyncio.to_thread(asgi_request,app,'GET',f'/api/public/orders/{identity}',token=token)
            assert content[0]==200 and content[2]['download_url'].startswith(f'/api/public/archives/{identity}?token=')
        assert 'public_order_rate_limiter' not in app.state.role_state
    asyncio.run(probe())


def test_stale_result_and_missing_signing_config_do_not_issue_link(order_http):
    fixture,call,payload,_=order_http
    engine,app,_,result,_,_,store,profile=fixture
    data=payload();identity=call('POST',payload=data)[2]['id']
    with Session(engine) as session:
        current=session.get(PublicSearchResult,result)
        session.add(PublicSearchResult(profile_id=profile, venue_ids=current.venue_ids,
            pipeline_revision_id=current.pipeline_revision_id, created_at=datetime.now(timezone.utc), venues=current.venues))
        session.commit()
    code,h,content=call('POST',payload=payload())
    assert code==404 and 'download_url' not in content;security(h)
    # Missing deployment signing configuration must not generate an unusable link.
    key=f'photo-archives/{identity}/selected.zip';store.put(key=key,body=b'private fixture')
    with Session(engine) as session:
        order=session.get(PhotoOrder,uuid.UUID(identity));order.archive_status='ready'
        order.ready_at=datetime.now(timezone.utc);order.archive_object_key=key;session.commit()
    app.state.role_state['photo_archive_signing_secret']=None
    code,h,content=call('GET',f'/api/public/orders/{identity}')
    assert code==200 and 'download_url' not in content;security(h)

"""TASK-128 quote delta on disposable PostgreSQL and unique private originals."""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import json
import uuid

import pytest
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.promo.browser_search_profile import BrowserSearchProfile
from face_moment.promo.public_photo_search import PublicSearchResult
from face_moment.serving_control.photo_tariff import PhotoTariff
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from tests.promo.test_public_search_api import public_fixture, request, security, jpeg
from tests.processing.test_realtime_search import _add_photo


@pytest.fixture
def quote_fixture(public_fixture):
    engine, app, _, model, venues, _, common = public_fixture
    store = PrivateObjectStore(Settings.from_env()); ensure_bucket(Settings.from_env())
    token = uuid.uuid4().hex; keys = []; paid = []; free = []
    prefix = f'task128/{uuid.uuid4().hex}/'
    try:
        with Session(engine) as session:
            profile = BrowserSearchProfile(cookie_digest=hashlib.sha256(token.encode()).hexdigest(),
                last_visit_at=datetime.now(timezone.utc), reset_used=False)
            session.add(profile);session.flush()
            groups = []
            for index in range(3):
                personal = []
                for number in range(11 if index != 1 else 2):
                    photo_id, _ = _add_photo(session, marker=f'quote-{index}-{number}', spa_id=venues[index],
                        revision_id=model.pipeline_revision_id, embedding=tuple(model.embedding), prefix=prefix,
                        visit_date=date(2026,1,1), phash64=None)
                    (free if index == 1 else paid).append(photo_id)
                    personal.append({'id':str(photo_id),'visit_date':'2026-01-01','is_free':index==1})
                photo_id=common[index,2026];free.append(photo_id)
                groups.append({'id':str(venues[index]),'name':f'venue{index}', 'personal':personal,
                    'common':[{'id':str(photo_id),'visit_date':'2026-01-01','is_free':True}]})
            result=PublicSearchResult(profile_id=profile.id,venue_ids=venues[:3],pipeline_revision_id=model.pipeline_revision_id,
                created_at=datetime.now(timezone.utc),venues=groups)
            session.add(result);session.flush();result_id=result.id;profile_id=profile.id
            session.add(PhotoTariff(id=1,base_kopecks=Decimal(101),d1=Decimal('.5'),d2=Decimal('.3'),d3=Decimal('.1'),updated_at=datetime.now(timezone.utc)))
            for photo_id in paid+free:
                key=session.get(Photo,photo_id).original_object_key;keys.append(key);store.put(key=key,body=jpeg())
            session.commit()
        app.state.role_state.update(public_preview_store=store,
            public_quote_rate_limiter=DisplayClientRateLimiter(limit=1000,window_seconds=60))
        yield engine,app,token,result_id,sorted(paid),free,store,profile_id
    finally:
        for key in keys:store.delete(key=key)
        for key in keys:assert not store.list_keys(prefix=key)


def quote(fixture, ids, *, token=None, payload=None, **options):
    _,app,auth,result_id,*_=fixture
    return request(app,'POST','/api/public/quote',token=auth if token is None else token,
        body=json.dumps({'result_id':str(result_id),'photo_ids':[str(i) for i in ids]} if payload is None else payload).encode(),
        headers=options.pop('headers',{'content-type':'application/json'}), **options)


@pytest.mark.parametrize('n,total',[ (0,0),(1,101),(2,152),(5,305),(6,335),(20,755),(21,765)])
def test_global_marginal_bands_half_up_stable_assignment(quote_fixture,n,total):
    _,_,_,_,paid,free,_,_=quote_fixture
    code,headers,content=quote(quote_fixture,list(reversed(paid[:n]))+free)
    assert code==200, f'FT-014-AC-002 quote absent/wrong: expected 200 observed {code}'
    security(headers)
    assert content['schema_version']==1 and content['currency']=='RUB'
    assert content['selected_count']==n+len(free) and content['paid_count']==n
    assert content['total_kopecks']==total==sum(item['unit_kopecks'] for item in content['items'])
    priced={item['photo_id']:item['unit_kopecks'] for item in content['items']}
    for i,photo_id in enumerate(paid[:n]):assert priced[str(photo_id)]==(101 if i==0 else 51 if i<5 else 30 if i<20 else 10)
    assert all(priced[str(i)]==0 for i in free)
    assert quote(quote_fixture,paid[:n]+list(reversed(free)))[2]==content
    assert 'original' not in json.dumps(content) and 'object_key' not in json.dumps(content)


def test_empty_free_only_and_unprovisioned_paid_tariff(quote_fixture):
    engine,_,_,_,paid,free,_,_=quote_fixture
    with Session(engine) as session:session.query(PhotoTariff).delete();session.commit()
    assert quote(quote_fixture,[])[2]=={'schema_version':1,'items':[],'selected_count':0,'paid_count':0,'total_kopecks':0,'currency':'RUB'}
    assert quote(quote_fixture,free)[2]['total_kopecks']==0
    assert quote(quote_fixture,paid[:1])[0]==503


@pytest.mark.parametrize('change', ['foreign_profile','foreign_photo','foreign_result','stale_result','inactive_photo','missing_original','orphan_common_date','inactive_venue'])
def test_current_owner_active_available_scope(quote_fixture,change):
    from face_moment.serving_control.ingest_target import Spa
    engine,_,token,result_id,paid,free,store,profile_id=quote_fixture
    payload={'result_id':str(result_id),'photo_ids':[str(paid[0])]};auth=token
    with Session(engine) as session:
        result=session.get(PublicSearchResult,result_id)
        if change=='foreign_profile':
            auth=uuid.uuid4().hex
            session.add(BrowserSearchProfile(cookie_digest=hashlib.sha256(auth.encode()).hexdigest(),last_visit_at=datetime.now(timezone.utc),reset_used=False))
        elif change=='foreign_photo':payload['photo_ids']=[str(uuid.uuid4())]
        elif change=='foreign_result':payload['result_id']=str(uuid.uuid4())
        elif change=='stale_result':
            session.add(PublicSearchResult(profile_id=profile_id,venue_ids=result.venue_ids,pipeline_revision_id=result.pipeline_revision_id,
                created_at=result.created_at+timedelta(seconds=1),venues=result.venues))
        elif change=='inactive_photo':session.get(Photo,paid[0]).is_active=False
        elif change=='missing_original':store.delete(key=session.get(Photo,paid[0]).original_object_key)
        elif change=='orphan_common_date':
            venue=result.venues[0]
            for item in venue['personal']:session.get(Photo,uuid.UUID(item['id'])).is_active=False
            payload['photo_ids']=[venue['common'][0]['id']]
        elif change=='inactive_venue':session.get(Spa,session.get(Photo,paid[0]).spa_id).active=False
        session.commit()
    status,headers,_=quote(quote_fixture,[],payload=payload,token=auth)
    assert status==404;security(headers)


def test_transport_strict_shapes_origin_https_and_cookie(quote_fixture):
    _,app,token,result,paid,*_=quote_fixture
    valid={'result_id':str(result),'photo_ids':[str(paid[0])]}
    for payload in [None,[],{}, {**valid,'photo_ids':'all'}, {**valid,'photo_ids':[True]},
                    {**valid,'result_id':1},{**valid,'result_id':'bad'}, {**valid,'photo_ids':['bad']},
                    {**valid,'photo_ids':[str(paid[0])]*2}, {**valid,'total_kopecks':0},
                    {**valid,'is_free':True}]:
        code,h,_=request(app,'POST','/api/public/quote',token=token,body=json.dumps(payload).encode())
        assert code==422;security(h)
    for body in (b'{',b'\xff'):
        code,h,_=request(app,'POST','/api/public/quote',token=token,body=body)
        assert code==422;security(h)
    for auth in (None,'unknown'):
        code,h,_=request(app,'POST','/api/public/quote',token=auth,body=json.dumps(valid).encode())
        assert code==401;security(h)
    for options in ({'scheme':'http'}, {'headers':{'origin':'https://foreign'}}, {'headers':{'origin':''}}):
        code,h,_=quote(quote_fixture,paid[:1],**options);assert code==403;security(h)


def test_ip_and_profile_rate_limits(quote_fixture):
    _,app,token,_,paid,*_=quote_fixture
    app.state.role_state['public_quote_rate_limiter']=DisplayClientRateLimiter(limit=1,window_seconds=60)
    assert quote(quote_fixture,paid[:1])[0]==200
    # Same profile different IP still limited, same IP different token still limited.
    for options in ({'peer':'127.0.0.2'}, {'token':'another-token'}):
        code,h,_=quote(quote_fixture,paid[:1],**options);assert code==429;security(h)


def test_current_tariff_free_snapshot_and_no_foreign_write(quote_fixture):
    from face_moment.serving_control.ingest_target import Spa
    from face_moment.processing.persistence import PhotoPipelineState
    engine,_,_,_,paid,free,store,_=quote_fixture
    def snapshot():
        with Session(engine) as session:
            return ([(p.id,p.is_active,p.original_object_key,p.visit_date) for p in session.query(Photo).order_by(Photo.id)],
                    [(p.photo_id,p.status,p.status_changed_at) for p in session.query(PhotoPipelineState).order_by(PhotoPipelineState.photo_id)],
                    [(p.id,p.is_free) for p in session.query(Spa).order_by(Spa.id)],
                    [(p.id,p.base_kopecks,p.d1,p.d2,p.d3,p.updated_at) for p in session.query(PhotoTariff)],
                    session.query(PublicSearchResult).count())
    before=snapshot(); assert quote(quote_fixture,paid+free)[0]==200;assert snapshot()==before
    with Session(engine) as session:
        session.get(Spa,session.get(Photo,paid[0]).spa_id).is_free=True
        session.get(PhotoTariff,1).base_kopecks=Decimal(203);session.commit()
    content=quote(quote_fixture,paid[:1]+free)[2]
    assert content['paid_count']==0 and content['total_kopecks']==0
    with Session(engine) as session:
        paid_venue_ids={p.spa_id for p in session.query(Photo).filter(Photo.id.in_(paid))}
        for venue_id in paid_venue_ids:session.get(Spa,venue_id).is_free=False
        session.commit()
    assert quote(quote_fixture,paid[:2])[2]['total_kopecks']==305 # 203 + half-up 101.5


def test_exact_large_base_and_decimal_coefficients_without_invented_bounds(quote_fixture):
    engine,_,_,_,paid,*_=quote_fixture
    base=10**50+1
    with Session(engine) as session:
        tariff=session.get(PhotoTariff,1);tariff.base_kopecks=Decimal(base)
        tariff.d1=Decimal('.50000000000000000000000000000000000000000000000001')
        tariff.d2=Decimal('.3');tariff.d3=Decimal('.1');session.commit()
    # Exact product = 5e49 + 1.500... : half-up must retain the tiny tail.
    assert quote(quote_fixture,paid[:2])[2]['total_kopecks']==base+5*10**49+2


def test_actual_http_and_repository_caddy_https_quote(quote_fixture,tmp_path):
    import http.client
    import os
    from pathlib import Path
    import ssl
    import subprocess
    import threading
    import time
    import uvicorn
    from face_moment.promo.browser_search_profile import COOKIE_NAME
    from tests.promo.test_public_edge_routes import _free_port
    _,app,token,result,paid,*_=quote_fixture
    backend_port,edge_port=_free_port(),_free_port()
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=backend_port,
        lifespan='off',access_log=False,log_level='error',proxy_headers=True,forwarded_allow_ips='127.0.0.1'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    process=None;log=None;observations=[]
    body=json.dumps({'result_id':str(result),'photo_ids':[str(i) for i in paid[:6]]})
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        else:pytest.fail('isolated HTTP backend did not start')
        connection=http.client.HTTPConnection('127.0.0.1',backend_port,timeout=5)
        try:
            connection.request('POST','/api/public/quote',body=body,headers={'Cookie':f'{COOKIE_NAME}={token}',
                'Origin':f'http://127.0.0.1:{backend_port}','Content-Type':'application/json'})
            response=connection.getresponse();assert response.status==403;response.read()
            observations.append({'edge':'actual loopback HTTP backend','status':403,'reason':'HTTPS required'})
        finally:connection.close()
        binary=tmp_path/'caddy';container=subprocess.check_output(['docker','create','caddy:2.10.0-alpine'],text=True).strip()
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
        def https(path,auth=token,origin=None):
            connection=http.client.HTTPSConnection('localhost',edge_port,context=ssl._create_unverified_context(),timeout=5)
            headers={'Origin':f'https://localhost:{edge_port}' if origin is None else origin,'Content-Type':'application/json'}
            if auth is not None:headers['Cookie']=f'{COOKIE_NAME}={auth}'
            try:
                connection.request('POST',path,body=body,headers=headers)
                response=connection.getresponse();return response.status,{k.lower():v for k,v in response.getheaders()},json.loads(response.read())
            finally:connection.close()
        for _ in range(100):
            try:
                status= https('/api/public/quote')[0]
                if status==200:break
            except OSError:pass
            time.sleep(.05)
        else:pytest.fail(f'isolated canonical TLS quote did not return 200: {status}')
        code,h,content=https('/api/public/quote');assert code==200;security(h)
        assert content['paid_count']==6 and content['total_kopecks']==335
        assert https('/api/public/quote',auth=None)[0]==401
        assert https('/api/public/quote',origin='https://foreign')[0]==403
        observations.append({'edge':'actual repository Caddyfile isolated loopback TLS','upstream':'backend',
            'route':'POST /api/public/quote','status':code,'paid_count':6,'total_kopecks':335,
            'missing_cookie':401,'foreign_origin':403,'private_originals_exposed':False,
            'cache_control':h['cache-control'],'referrer_policy':h['referrer-policy']})
    finally:
        if process is not None:process.terminate();process.wait(timeout=5)
        if log is not None:log.close()
        server.should_exit=True;thread.join(timeout=5)
    artifact=Path('.tasks/TASK-128-T3-FT-014-W7/https-observations.json')
    artifact.parent.mkdir(exist_ok=True);artifact.write_text(json.dumps(observations,indent=2)+'\n')

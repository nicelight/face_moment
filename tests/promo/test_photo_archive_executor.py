"""AC-004: actual backend lifespan on disposable PostgreSQL/private MinIO."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from io import BytesIO
import threading
import uuid
from zipfile import ZipFile

import pytest
from sqlalchemy.orm import Session

from face_moment.entrypoints import backend
from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.inventory.photo_persistence import Photo
from face_moment.promo.photo_orders import PhotoOrder
from tests.promo.test_photo_quote import quote_fixture
from tests.promo.test_public_search_api import public_fixture
from tests.promo.test_photo_orders import create, snapshot


async def wait_for(engine, identity, status, seconds=5):
    end = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < end:
        record = snapshot(engine, identity)
        if record['archive_status'] == status:
            return record
        await asyncio.sleep(.02)
    raise AssertionError(f'AC-004 actual startup expected {status}, observed {record["archive_status"]}')


@pytest.fixture
def archive_fixture(quote_fixture):
    engine, _, _, _, paid, free, store, _ = quote_fixture
    orders = []
    def add(*, paid_order=False, status='requested', ready_at=None):
        ids = paid[:2] + free[:1] if paid_order else free[:2]
        identity = create(quote_fixture, request_id=uuid.uuid4().hex, ids=ids,
            **({'email':'receipt@example.test','payment_method':'sbp'} if paid_order else {}))
        orders.append(identity)
        with Session(engine) as session:
            order = session.get(PhotoOrder, identity)
            order.archive_status = status
            order.ready_at = ready_at
            session.commit()
        return identity
    try:
        yield quote_fixture, add
    finally:
        for identity in orders:
            for key in store.list_keys(prefix=f'photo-archives/{identity}/'):
                store.delete(key=key)
            assert not store.list_keys(prefix=f'photo-archives/{identity}/')


def test_startup_exact_private_zip_and_ready_timestamp(archive_fixture):
    fixture, add = archive_fixture
    engine, _, _, _, _, _, store, _ = fixture
    first = add(); second = add(paid_order=True)
    async def probe():
        app = backend.create_app()
        async with app.router.lifespan_context(app):
            completed = [await wait_for(engine, identity, 'ready') for identity in (first, second)]
            for record in completed:
                assert record['ready_at'] and record['archive_object_key'] == f'photo-archives/{record["id"]}/selected.zip'
                with ZipFile(BytesIO(store.read(key=record['archive_object_key']))) as archive:
                    assert archive.namelist() == [f'{item["photo_id"]}.jpg' for item in record['items']]
                    with Session(engine) as session:
                        for item in record['items']:
                            source = session.get(Photo, uuid.UUID(item['photo_id'])).original_object_key
                            assert archive.read(f'{item["photo_id"]}.jpg') == store.read(key=source)
                assert store.list_keys(prefix=f'photo-archives/{record["id"]}/') == {record['archive_object_key']}
                assert record['provider_payment_id'] is None and record['payment_requested_at'] is None
            assert completed[0]['ready_at'] <= completed[1]['ready_at']
        assert 'photo_archive_executor' not in app.state.role_state
        saved = [snapshot(engine, identity)['ready_at'] for identity in (first, second)]
        async with app.router.lifespan_context(app):
            await asyncio.sleep(.15)
            assert [snapshot(engine, identity)['ready_at'] for identity in (first, second)] == saved
    asyncio.run(probe())


def test_oldest_preparing_blocked_io_keeps_backend_responsive(archive_fixture, monkeypatch):
    fixture, add = archive_fixture
    engine, _, _, _, _, _, store, _ = fixture
    first = add(); second = add(paid_order=True)
    entered = threading.Event(); release = threading.Event()
    read = PrivateObjectStore.read
    def blocking_read(self, *, key):
        if not key.startswith('photo-archives/'):
            entered.set()
            assert release.wait(10)
        return read(self, key=key)
    monkeypatch.setattr(PrivateObjectStore, 'read', blocking_read)
    async def probe():
        app = backend.create_app()
        try:
            async with app.router.lifespan_context(app):
                assert await asyncio.to_thread(entered.wait, 5)
                assert snapshot(engine, first)['archive_status'] == 'preparing'
                assert snapshot(engine, second)['archive_status'] == 'requested'
                assert not store.exists(key=f'photo-archives/{first}/selected.zip')
                messages = []
                async def receive(): return {'type':'http.request','body':b'','more_body':False}
                async def send(message): messages.append(message)
                await asyncio.wait_for(app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1',
                    'method':'GET','scheme':'http','path':'/healthz','raw_path':b'/healthz',
                    'query_string':b'','root_path':'','headers':[], 'client':('127.0.0.1',1),
                    'server':('localhost',80)}, receive, send), 2)
                assert next(m for m in messages if m['type']=='http.response.start')['status'] == 200
                release.set()
                await wait_for(engine, second, 'ready')
        finally:
            release.set()
    asyncio.run(probe())


def test_temporary_complete_zip_is_not_published_before_final_success(archive_fixture, monkeypatch):
    fixture, add = archive_fixture
    engine, _, _, _, _, _, store, _ = fixture
    identity = add()
    entered = threading.Event(); release = threading.Event()
    put = PrivateObjectStore.put
    def blocking_put(self, *, key, body):
        put(self, key=key, body=body)
        if key.endswith('/building.zip'):
            entered.set(); assert release.wait(10)
    monkeypatch.setattr(PrivateObjectStore, 'put', blocking_put)
    async def probe():
        app = backend.create_app()
        try:
            async with app.router.lifespan_context(app):
                assert await asyncio.to_thread(entered.wait, 5)
                record = snapshot(engine, identity)
                assert record['archive_status']=='preparing' and record['ready_at'] is None
                assert record['archive_object_key'] is None
                assert not store.exists(key=f'photo-archives/{identity}/selected.zip')
                with ZipFile(BytesIO(store.read(key=f'photo-archives/{identity}/building.zip'))) as archive:
                    assert archive.namelist()==[f'{i["photo_id"]}.jpg' for i in record['items']]
                    assert archive.testzip() is None
                release.set(); await wait_for(engine, identity, 'ready')
        finally: release.set()
    asyncio.run(probe())


def test_actual_process_interruption_restart_rebuild_and_saved_timestamp(archive_fixture):
    import os
    import subprocess
    import sys
    import time
    fixture, add = archive_fixture
    engine, _, _, _, _, _, store, _ = fixture
    identity = add()
    script = '''import asyncio, threading
from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.object_store import PrivateObjectStore
original = PrivateObjectStore.read
def blocked(self, *, key):
    if not key.startswith('photo-archives/'): threading.Event().wait()
    return original(self, key=key)
PrivateObjectStore.read = blocked
async def main():
    app = create_app()
    async with app.router.lifespan_context(app): await asyncio.Event().wait()
asyncio.run(main())
'''
    process = subprocess.Popen([sys.executable, '-c', script], env=os.environ.copy(),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        end = time.monotonic()+8
        while snapshot(engine, identity)['archive_status']!='preparing' and time.monotonic()<end:
            assert process.poll() is None
            time.sleep(.03)
        assert snapshot(engine, identity)['archive_status']=='preparing'
    finally:
        process.kill(); process.wait(timeout=5)
    assert snapshot(engine, identity)['archive_status']=='preparing'
    # An interrupted record with saved timestamp must preserve that timestamp too.
    saved = datetime.now(timezone.utc)-timedelta(hours=1)
    prior = add(status='preparing', ready_at=saved)
    store.put(key=f'photo-archives/{identity}/building.zip', body=b'interrupted unpublished bytes')
    async def probe():
        app = backend.create_app()
        async with app.router.lifespan_context(app):
            completed = await wait_for(engine, identity, 'ready')
            rebuilt = await wait_for(engine, prior, 'ready')
            assert rebuilt['ready_at']==saved
            with ZipFile(BytesIO(store.read(key=completed['archive_object_key']))) as archive:
                assert archive.namelist()==[f'{item["photo_id"]}.jpg' for item in completed['items']]
            assert not store.exists(key=f'photo-archives/{identity}/building.zip')
    asyncio.run(probe())


@pytest.mark.parametrize('failure,mail_failure', [('missing',False),('deleted',True),('build',True)])
def test_failed_persists_and_configured_mail_attempt_is_bounded(archive_fixture, monkeypatch, caplog, failure, mail_failure):
    from face_moment.infrastructure import archive_failure_mail
    from face_moment.promo.photo_archive_executor import logger
    # Alembic fileConfig disables pre-imported loggers during fixture migration.
    monkeypatch.setattr(logger, "disabled", False)
    fixture, add = archive_fixture
    engine, _, _, _, _, _, store, _ = fixture
    identity = add(paid_order=True)
    record = snapshot(engine, identity)
    with Session(engine) as session:
        photo = session.get(Photo, uuid.UUID(record['items'][0]['photo_id']))
        if failure=='missing': store.delete(key=photo.original_object_key)
        elif failure=='deleted': photo.is_active=False; session.commit()
    if failure=='build':
        put = PrivateObjectStore.put
        def failing_put(self, *, key, body):
            if key.endswith('/selected.zip'): raise RuntimeError('synthetic build error secret-marker')
            return put(self,key=key,body=body)
        monkeypatch.setattr(PrivateObjectStore,'put',failing_put)
    calls = []
    class FakeSMTP:
        def __init__(self, host, port, *, timeout): calls.append(('connect',host,port,timeout))
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def starttls(self): calls.append(('tls',))
        def login(self,username,password): calls.append(('login',username,password))
        def send_message(self,message):
            calls.append(('send',message))
            if mail_failure: raise RuntimeError('smtp failure secret-marker')
    monkeypatch.setattr(archive_failure_mail.smtplib,'SMTP',FakeSMTP)
    for name,value in {'ARCHIVE_MAIL_HOST':'fixture.invalid','ARCHIVE_MAIL_PORT':'2525',
        'ARCHIVE_MAIL_FROM':'archive@example.test','ARCHIVE_MAIL_USERNAME':'fixture-user',
        'ARCHIVE_MAIL_PASSWORD':'fixture-password','ARCHIVE_MAIL_TIMEOUT_SECONDS':'1'}.items():
        monkeypatch.setenv(name,value)
    async def probe():
        app = backend.create_app()
        async with app.router.lifespan_context(app):
            failed = await wait_for(engine,identity,'failed')
            end = asyncio.get_running_loop().time()+3
            while not any(c[0]=='send' for c in calls) and asyncio.get_running_loop().time()<end:
                await asyncio.sleep(.02)
            await asyncio.sleep(.1)
            assert failed['archive_failure_reason']=='Не удалось подготовить архив. Обратитесь в поддержку.'
            assert failed['archive_object_key'] is None and failed['ready_at'] is None
            assert failed['payment_status']=='pending' and failed['provider_payment_id'] is None
            assert failed['payment_requested_at'] is None
        assert calls[:3]==[('connect','fixture.invalid',2525,1.0),('tls',),('login','fixture-user','fixture-password')]
        sent=[c[1] for c in calls if c[0]=='send']; assert len(sent)==1
        assert sent[0]['To']=='sergiosandroid2@gmail.com' and sent[0]['From']=='archive@example.test'
        assert str(identity) in sent[0].get_content() and 'secret-marker' not in sent[0].get_content()
        assert snapshot(engine,identity)['archive_status']=='failed'
        assert not store.list_keys(prefix=f'photo-archives/{identity}/')
        errors=[r for r in caplog.records if 'photo_archive_failure_mail_failed' in r.message]
        assert len(errors)==int(mail_failure)
        assert 'secret-marker' not in caplog.text and 'fixture-password' not in caplog.text
        async with app.router.lifespan_context(app): await asyncio.sleep(.1)
        assert len([c for c in calls if c[0]=='send'])==1
    asyncio.run(probe())

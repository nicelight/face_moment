"""Frozen core AC-006 on disposable PostgreSQL and private synthetic originals."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
import threading
import uuid

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.promo.browser_search_profile import BrowserSearchProfile
from face_moment.promo.photo_orders import PhotoOrder, PhotoOrderConflictError, PhotoOrderRepository
from face_moment.promo.public_photo_search import PublicSearchResult, PublicResultNotFoundError, PublicProfileRequiredError
from face_moment.serving_control.photo_tariff import PhotoTariff
from face_moment.serving_control.ingest_target import Spa
from tests.promo.test_photo_quote import quote_fixture
from tests.promo.test_public_search_api import public_fixture


def create(fixture, *, request_id='request-1', ids=None, **kwargs):
    engine, _, token, result_id, paid, _, store, _ = fixture
    with Session(engine) as session, session.begin():
        order = PhotoOrderRepository(session).create(cookie_token=token, result_id=result_id,
            photo_ids=paid[:2] if ids is None else ids, client_request_id=request_id,
            object_store=store, **kwargs)
        identity = order.id
    return identity


def snapshot(engine, order_id):
    with Session(engine) as session:
        order = session.get(PhotoOrder, order_id)
        return {column.key: getattr(order, column.key) for column in inspect(PhotoOrder).columns}


def profile_state(engine, profile_id):
    with Session(engine) as session:
        profile = session.get(BrowserSearchProfile, profile_id)
        return profile.email, profile.last_visit_at


@pytest.mark.parametrize('method', ['bank_card', 'sbp'])
def test_complete_frozen_snapshot_new_settings_and_owner_read(quote_fixture, method):
    engine, _, token, result_id, paid, free, _, profile_id = quote_fixture
    with Session(engine) as session:
        first_venue = session.get(Photo, paid[0]).spa_id
        other = next(i for i in paid if session.get(Photo, i).spa_id != first_venue)
    ids = [paid[0], other, free[-1]]
    old_id = create(quote_fixture, ids=ids, email='frozen@example.test', payment_method=method)
    old = snapshot(engine, old_id)
    assert old['profile_id'] == profile_id and old['client_request_id'] == 'request-1'
    assert old['total_kopecks'] == 152 and old['email'] == 'frozen@example.test'
    assert old['payment_method'] == method and old['archive_status'] == 'requested'
    assert old['payment_status'] == 'pending' and old['payment_idempotence_key'] == str(old_id)
    assert len(old['request_digest']) == 64
    for key in ('archive_object_key', 'ready_at', 'archive_failure_reason',
                'provider_payment_id', 'payment_requested_at', 'paid_at'):
        assert old[key] is None
    assert [i['photo_id'] for i in old['items']] == sorted(str(i) for i in ids)
    assert all(set(i) == {'photo_id','venue_id','visit_date','is_free','unit_kopecks'} for i in old['items'])
    assert sum(i['unit_kopecks'] for i in old['items']) == old['total_kopecks']
    with Session(engine) as session:
        for item in old['items']:
            photo = session.get(Photo, uuid.UUID(item['photo_id']))
            assert item['venue_id'] == str(photo.spa_id) and item['visit_date'] == photo.visit_date.isoformat()
            assert item['is_free'] == (photo.id in free)
        session.get(Spa, session.get(Photo, paid[0]).spa_id).is_free = True
        session.get(PhotoTariff, 1).base_kopecks = Decimal(203)
        session.commit()
    new_id = create(quote_fixture, request_id='new-settings', ids=ids,
        email='new@example.test', payment_method=method)
    new = snapshot(engine, new_id)
    assert new_id != old_id and new['total_kopecks'] == 203
    assert sum(i['is_free'] for i in new['items']) == 2
    assert snapshot(engine, old_id) == old
    # Replay is frozen even after the original gallery goes stale/source disappears.
    with Session(engine) as session:
        result = session.get(PublicSearchResult, result_id)
        session.add(PublicSearchResult(profile_id=profile_id, venue_ids=result.venue_ids,
            pipeline_revision_id=result.pipeline_revision_id, created_at=result.created_at+timedelta(seconds=1), venues=result.venues))
        session.get(Photo, paid[0]).is_active = False
        session.commit()
    state = profile_state(engine, profile_id)
    assert create(quote_fixture, ids=list(reversed(ids)), email='frozen@example.test', payment_method=method) == old_id
    assert profile_state(engine, profile_id) == state and snapshot(engine, old_id) == old
    engine.dispose()  # actual new connection/session, persistent snapshot still readable
    with Session(engine) as session:
        assert PhotoOrderRepository(session).find(cookie_token=token, order_id=old_id).items == old['items']
        assert PhotoOrderRepository(session).find(cookie_token='foreign', order_id=old_id) is None


def test_free_order_no_email_replacement_and_zero_provider_state(quote_fixture):
    engine, _, _, _, _, free, _, profile_id = quote_fixture
    with Session(engine) as session:
        session.get(BrowserSearchProfile, profile_id).email = 'keep@example.test';session.commit()
    identity = create(quote_fixture, ids=free)
    record = snapshot(engine, identity)
    assert record['total_kopecks'] == 0 and record['payment_status'] == 'not_required'
    assert record['email'] is None and record['payment_method'] is None
    assert record['archive_status'] == 'requested' and record['provider_payment_id'] is None
    assert record['payment_requested_at'] is None
    assert profile_state(engine, profile_id)[0] == 'keep@example.test'
    create(quote_fixture, ids=free, request_id='free-with-email', email='ignored@example.test')
    assert profile_state(engine, profile_id)[0] == 'keep@example.test'


def test_concurrent_identical_replay_and_conflict_atomicity(quote_fixture):
    engine, _, _, _, _, _, _, profile_id = quote_fixture
    barrier = threading.Barrier(2)
    def request(email):
        barrier.wait(timeout=10)
        try:
            return create(quote_fixture, email=email, payment_method='sbp')
        except PhotoOrderConflictError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(request, ['one@example.test']*2))
    assert first == second
    with Session(engine) as session:
        assert session.query(PhotoOrder).count() == 1
    state = profile_state(engine, profile_id); saved = snapshot(engine, first)
    for kwargs in ({'email':'other@example.test','payment_method':'sbp'},
                   {'email':'one@example.test','payment_method':'bank_card'},
                   {'email':'one@example.test','payment_method':'sbp','ids':quote_fixture[4][:1]}):
        with pytest.raises(PhotoOrderConflictError): create(quote_fixture, **kwargs)
        assert profile_state(engine, profile_id) == state and snapshot(engine, first) == saved
    # Conflicting concurrent initial requests: only winning email/order commit.
    with Session(engine) as session:session.query(PhotoOrder).delete();session.commit()
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(request, ['a@example.test', 'b@example.test']))
    assert outcomes.count('conflict') == 1
    winner = next(i for i in outcomes if i != 'conflict')
    assert profile_state(engine, profile_id)[0] == snapshot(engine, winner)['email']
    with Session(engine) as session:assert session.query(PhotoOrder).count() == 1


@pytest.mark.parametrize('invalid', ['email','method','duplicate','foreign_profile','foreign_photo',
    'foreign_result','stale_result','inactive_photo','missing_original','inactive_venue'])
def test_invalid_new_order_rolls_back_profile_and_order(quote_fixture, invalid):
    engine, _, token, result_id, paid, _, store, profile_id = quote_fixture
    args = dict(cookie_token=token, result_id=result_id, photo_ids=paid[:1],
        client_request_id='invalid', object_store=store, email='valid@example.test', payment_method='bank_card')
    with Session(engine) as session:
        if invalid == 'email':args['email']='invalid'
        elif invalid == 'method':args['payment_method']='cash'
        elif invalid == 'duplicate':args['photo_ids']=[paid[0],paid[0]]
        elif invalid == 'foreign_profile':args['cookie_token']='unknown'
        elif invalid == 'foreign_photo':args['photo_ids']=[uuid.uuid4()]
        elif invalid == 'foreign_result':args['result_id']=uuid.uuid4()
        elif invalid == 'stale_result':
            result=session.get(PublicSearchResult,result_id)
            session.add(PublicSearchResult(profile_id=profile_id,venue_ids=result.venue_ids,
                pipeline_revision_id=result.pipeline_revision_id,created_at=result.created_at+timedelta(seconds=1),venues=result.venues))
        elif invalid == 'inactive_photo':session.get(Photo,paid[0]).is_active=False
        elif invalid == 'missing_original':store.delete(key=session.get(Photo,paid[0]).original_object_key)
        elif invalid == 'inactive_venue':session.get(Spa,session.get(Photo,paid[0]).spa_id).active=False
        session.commit()
    before = profile_state(engine, profile_id)
    with pytest.raises((ValueError, PublicResultNotFoundError, PublicProfileRequiredError)):
        with Session(engine) as session, session.begin():PhotoOrderRepository(session).create(**args)
    assert profile_state(engine, profile_id) == before
    with Session(engine) as session:assert session.query(PhotoOrder).count() == 0


def test_paid_profile_and_order_atomic_commit_and_real_database_rollback(quote_fixture):
    engine, _, token, result_id, paid, _, store, profile_id = quote_fixture
    before = profile_state(engine, profile_id)
    with pytest.raises(DBAPIError):
        with Session(engine) as session, session.begin():
            PhotoOrderRepository(session).create(cookie_token=token,result_id=result_id,photo_ids=paid[:1],
                client_request_id='rollback',object_store=store,email='rollback@example.test',payment_method='sbp')
            # Real PostgreSQL transaction abort after both owned records were flushed.
            session.execute(text('SELECT 1 / 0'))
    assert profile_state(engine, profile_id) == before
    with Session(engine) as session:assert session.query(PhotoOrder).count() == 0
    identity=create(quote_fixture,email='atomic@example.test',payment_method='bank_card')
    email, visit = profile_state(engine, profile_id)
    assert email == snapshot(engine,identity)['email'] == 'atomic@example.test'
    assert visit == snapshot(engine,identity)['created_at'] and visit > before[1]


def test_own_migration_roundtrip_preserves_profile_photo_and_venue(quote_fixture):
    engine = quote_fixture[0]
    scripts=ScriptDirectory.from_config(Config('alembic.ini')); own=scripts.get_revision('0032_photo_orders')
    assert own.down_revision == '0031_public_search_results'
    def others():
        with engine.connect() as connection:
            return [connection.execute(text(f'SELECT to_jsonb(t) FROM face_moment.{table} t ORDER BY id')).all()
                    for table in ('browser_search_profiles','photos','spas','photo_tariff','public_search_results')]
    before=others()
    command.downgrade(Config('alembic.ini'),own.down_revision)
    with engine.connect() as connection:assert connection.scalar(text("SELECT to_regclass('face_moment.photo_orders')")) is None
    assert others()==before
    command.upgrade(Config('alembic.ini'),own.revision)
    assert others()==before
    # Constraint is actual PostgreSQL, independent of row-lock arbitration.
    first=create(quote_fixture,email='unique@example.test',payment_method='sbp')
    saved=snapshot(engine,first);saved['id']=uuid.uuid4()
    with pytest.raises(IntegrityError):
        with Session(engine) as session,session.begin():session.add(PhotoOrder(**saved))
    with Session(engine) as session:assert session.query(PhotoOrder).count()==1

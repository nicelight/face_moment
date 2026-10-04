"""Owned global tariff acceptance on disposable PostgreSQL only."""
from face_moment.entrypoints.backend import create_app


def test_tariff_routes_registered() -> None:
    app = create_app()
    routes = {(route.path, method) for route in app.routes for method in getattr(route, 'methods', ())}
    assert ('/api/serving/photo-tariff', 'GET') in routes
    assert ('/api/serving/photo-tariff', 'PUT') in routes

from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.orm import Session

from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.serving_control.photo_tariff import (
    PhotoTariffUnavailableError, read_photo_tariff_snapshot, save_photo_tariff,
)
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.serving_control.test_active_search_date import _login, _request

PATH = '/api/serving/photo-tariff'
VALID = {'base_kopecks': 10000, 'd1': '0.8', 'd2': '0.6', 'd3': '0.4'}


@pytest.fixture(scope='module')
def tariff_fixture() -> Iterator[tuple]:
    with disposable_postgresql_engine('task127_tariff') as engine:
        app = create_app()
        app.state.role_state['session_factory'] = lambda: Session(engine)
        cookies = {}
        for role in StaffRole:
            credentials = {'username': f'tariff-{role}', 'password': 'test-tariff-password'}
            with Session(engine) as session:
                provision_staff_user(session, role=role, **credentials)
            cookies[role] = _login(app, credentials)
        yield app, engine, cookies


def _save(app, cookies, values=VALID):
    return _request(app, 'PUT', PATH, body=values, cookies=cookies,
                    headers={'X-CSRF-Token': cookies['fm_staff_csrf']})


def test_unprovisioned_tariff_fails_closed(tariff_fixture):
    app, engine, cookies = tariff_fixture
    assert _request(app, 'GET', PATH, cookies=cookies[StaffRole.OPERATOR])[0] == 503
    with Session(engine) as session:
        with pytest.raises(PhotoTariffUnavailableError):
            read_photo_tariff_snapshot(session)
        assert session.scalar(text('SELECT count(*) FROM face_moment.photo_tariff')) == 0


@pytest.mark.parametrize('role', [StaffRole.OPERATOR, StaffRole.DEVELOPER])
def test_authorized_provision_and_update_persist_after_restart(tariff_fixture, role):
    app, engine, cookies = tariff_fixture
    status, headers, result = _save(app, cookies[role])
    assert status == 200 and headers['cache-control'] == 'no-store'
    assert result == VALID
    # New connection pool and new application reproduce an ordinary restart read.
    engine.dispose()
    restarted = create_app()
    restarted.state.role_state['session_factory'] = lambda: Session(engine)
    assert _request(restarted, 'GET', PATH, cookies=cookies[role])[2] == VALID
    with Session(engine) as session:
        snapshot = read_photo_tariff_snapshot(session)
        assert snapshot.base_kopecks == 10000 and snapshot.d3 == Decimal('0.4')
        assert snapshot.updated_at.tzinfo is not None
        with pytest.raises(FrozenInstanceError):
            snapshot.base_kopecks = 1
        assert session.scalar(text('SELECT count(*) FROM face_moment.photo_tariff')) == 1


def _owner_state(engine):
    with engine.connect() as connection:
        return (connection.execute(text('SELECT * FROM face_moment.photo_tariff')).all(),
                connection.execute(text('SELECT * FROM face_moment.public_search_settings')).all())


def test_denied_requests_preserve_tariff_and_unrelated_settings(tariff_fixture):
    app, engine, cookies = tariff_fixture
    before = _owner_state(engine)
    operator = cookies[StaffRole.OPERATOR]
    photographer = cookies[StaffRole.PHOTOGRAPHER]
    cases = [
        (None, {}, 401), ({'fm_staff_session': 'invalid'}, {}, 401),
        (photographer, {'X-CSRF-Token': photographer['fm_staff_csrf']}, 403),
        (operator, {}, 403), (operator, {'X-CSRF-Token': 'wrong'}, 403),
        ({'fm_staff_session': operator['fm_staff_session']}, {'X-CSRF-Token': operator['fm_staff_csrf']}, 403),
        ({**operator, 'fm_staff_csrf': 'forged'}, {'X-CSRF-Token': 'forged'}, 403),
    ]
    for browser, headers, expected in cases:
        assert _request(app, 'PUT', PATH, body=VALID, cookies=browser, headers=headers)[0] == expected
        assert _owner_state(engine) == before
    for browser, expected in [(None, 401), ({'fm_staff_session': 'invalid'}, 401), (photographer, 403)]:
        assert _request(app, 'GET', PATH, cookies=browser)[0] == expected
        assert _owner_state(engine) == before


@pytest.mark.parametrize('changes', [
    {'base_kopecks': 0}, {'base_kopecks': -1}, {'base_kopecks': True},
    {'base_kopecks': 1.5}, {'base_kopecks': '100'},
    {'d1': 'NaN'}, {'d2': 'Infinity'}, {'d3': '-Infinity'},
    {'d1': '1.01'}, {'d3': '0'}, {'d2': '-0.1'},
    {'d1': '0.5'}, {'d2': '0.3'}, {'base_kopecks': 1, 'd3': '0.499999'},
    {'d1': True}, {'extra': 1},
])
def test_invalid_settings_are_atomic(tariff_fixture, changes):
    app, engine, cookies = tariff_fixture
    before = _owner_state(engine)
    assert _save(app, cookies[StaffRole.OPERATOR], {**VALID, **changes})[0] == 422
    assert _owner_state(engine) == before


def test_half_up_minimum_and_exact_decimal_persistence(tariff_fixture):
    app, engine, cookies = tariff_fixture
    values = {'base_kopecks': 1, 'd1': '1', 'd2': '0.50000000000000000000000001', 'd3': '0.5'}
    assert _save(app, cookies[StaffRole.DEVELOPER], values)[0] == 200
    with Session(engine) as session:
        assert read_photo_tariff_snapshot(session).d2 == Decimal(values['d2'])
    # Base has no accepted upper bound; don't silently impose bigint limits.
    values['base_kopecks'] = 10 ** 30
    assert _save(app, cookies[StaffRole.DEVELOPER], values)[0] == 200
    with Session(engine) as session:
        assert read_photo_tariff_snapshot(session).base_kopecks == 10 ** 30


def test_owner_command_rejects_invalid_before_mutation(tariff_fixture):
    _, engine, cookies = tariff_fixture
    browser = cookies[StaffRole.OPERATOR]
    before = _owner_state(engine)
    for base, coefficient in [(0, Decimal('0.8')), (True, Decimal('0.8')), (100, Decimal('NaN')), (1, Decimal('0.49'))]:
        with Session(engine) as session:
            with pytest.raises(ValueError):
                save_photo_tariff(session, base_kopecks=base, d1=Decimal('1'), d2=Decimal('1'), d3=coefficient,
                    session_token=browser['fm_staff_session'], csrf_cookie_token=browser['fm_staff_csrf'], csrf_header_token=browser['fm_staff_csrf'])
            session.commit()
        assert _owner_state(engine) == before


def test_own_migration_round_trip_preserves_other_owner_state():
    scripts = ScriptDirectory.from_config(Config('alembic.ini'))
    own = scripts.get_revision('0029_global_photo_tariff')
    assert own is not None and own.down_revision is not None
    revisions = list(scripts.walk_revisions())
    assert len(scripts.get_heads()) == 1
    assert all(not isinstance(r.down_revision, tuple) for r in revisions)
    with disposable_postgresql_engine('task127_migration') as engine:
        with engine.begin() as connection:
            connection.execute(text('UPDATE face_moment.public_search_settings SET profile_similarity_threshold = 0.42'))
        command.downgrade(Config('alembic.ini'), own.down_revision)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT to_regclass('face_moment.photo_tariff')")) is None
            assert connection.scalar(text('SELECT profile_similarity_threshold FROM face_moment.public_search_settings')) == 0.42
        command.upgrade(Config('alembic.ini'), own.revision)
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM face_moment.photo_tariff')) == 0
            assert connection.scalar(text('SELECT profile_similarity_threshold FROM face_moment.public_search_settings')) == 0.42


def test_missing_fields_rejected_without_mutation(tariff_fixture):
    app, engine, cookies = tariff_fixture
    before = _owner_state(engine)
    for field in VALID:
        assert _save(app, cookies[StaffRole.OPERATOR], {key: value for key, value in VALID.items() if key != field})[0] == 422
        assert _owner_state(engine) == before


def test_database_enforces_singleton_and_numerical_invariants(tariff_fixture):
    from sqlalchemy.exc import IntegrityError
    _, engine, _ = tariff_fixture
    before = _owner_state(engine)
    for assignment in ('id=2', 'base_kopecks=0', 'base_kopecks=1.5',
                       "base_kopecks='NaN'::numeric", "base_kopecks='Infinity'::numeric",
                       'd1=1.1', 'd2=0.1,d3=0.2', 'd3=0', "d1='NaN'::numeric",
                       'base_kopecks=1,d1=1,d2=1,d3=0.49'):
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(f'UPDATE face_moment.photo_tariff SET {assignment}'))
        assert _owner_state(engine) == before

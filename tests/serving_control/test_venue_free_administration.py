"""AC-003: exact staff API and new-session observation in disposable state."""
from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control.ingest_target import IngestTargetRepository, Spa
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY
from tests.serving_control.test_active_search_date import _login, _request

@pytest.fixture(scope='module')
def free_fixture():
    with disposable_postgresql_engine('task131_staff') as engine:
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE, validated_at=datetime.now(timezone.utc),
                **PIPELINE_COMPATIBILITY)
            spa = IngestTargetRepository(session).configure_spa(name='Existing', timezone='UTC',
                serving_pipeline_revision_id=revision.id)
            inactive = IngestTargetRepository(session).configure_spa(name='Inactive', timezone='UTC',
                serving_pipeline_revision_id=revision.id)
            session.get(Spa, inactive.spa_id).active = False
            session.commit()
        app = create_app(); app.state.role_state['session_factory'] = lambda: Session(engine)
        cookies = {}
        for role in StaffRole:
            credentials = dict(username=f'free-{role.value}', password='free-fixture-password')
            with Session(engine) as session: provision_staff_user(session, role=role, **credentials)
            cookies[role] = _login(app, credentials)
        yield app, engine, cookies, spa.spa_id, inactive.spa_id

def state(engine):
    with Session(engine) as session:
        return [tuple(getattr(spa, column.name) for column in Spa.__table__.columns)
                for spa in session.scalars(select(Spa).order_by(Spa.id))]

def mutate(app, cookies, path, body, method='PUT', headers=None):
    return _request(app, method, path, body=body, cookies=cookies,
        headers=headers if headers is not None else {'X-CSRF-Token': cookies['fm_staff_csrf']})

@pytest.mark.parametrize('role', [StaffRole.OPERATOR, StaffRole.DEVELOPER])
def test_exact_create_update_and_ssr_reload(free_fixture, role):
    app, engine, cookies, existing, _ = free_fixture
    browser = cookies[role]
    for mode in (False, True):
        code, headers, result = mutate(app, browser, '/api/serving/spas',
            {'name': f'Created-{role.value}-{mode}', 'timezone': 'Europe/Moscow', 'is_free': mode}, 'POST')
        assert code == 201, (code, result)
        assert result['is_free'] is mode and headers['cache-control'] == 'no-store'
        spa_id = uuid.UUID(result['spa_id'])
        with Session(engine) as session:
            spa = session.get(Spa, spa_id)
            assert spa.is_free is mode and spa.timezone == 'Europe/Moscow' and spa.search_today
            assert (spa.photo_yunet_threshold, spa.capture_blazeface_threshold) == (.7, .5)
        for new_mode in (True, False):
            before = state(engine)
            code, headers, result = mutate(app, browser, f'/api/serving/spas/{spa_id}/is-free', {'is_free': new_mode})
            assert (code, result) == (200, {'spa_id': str(spa_id), 'is_free': new_mode})
            assert headers['cache-control'] == 'no-store'
            with Session(engine) as session: assert session.get(Spa, spa_id).is_free is new_mode
            after = state(engine)
            index = list(Spa.__table__.columns.keys()).index('is_free')
            assert [row[:index]+row[index+1:] for row in before] == [row[:index]+row[index+1:] for row in after]
            code, headers, page = _request(app, 'GET', '/staff/spas', cookies=browser)
            assert code == 200 and headers['cache-control'] == 'no-store'
            assert f'data-spa-id="{spa_id}" data-is-free="{str(new_mode).lower()}"' in page

@pytest.mark.parametrize('method', ['POST','PUT'])
def test_all_denials_and_strict_bool_preserve_state(free_fixture, method):
    app, engine, cookies, spa_id, inactive_id = free_fixture
    path = '/api/serving/spas' if method == 'POST' else f'/api/serving/spas/{spa_id}/is-free'
    good = {'name': 'Rejected', 'timezone': 'UTC', 'is_free': True} if method == 'POST' else {'is_free': True}
    admin, photographer = cookies[StaffRole.OPERATOR], cookies[StaffRole.PHOTOGRAPHER]
    before = state(engine)
    cases = [(None, {}, 401), ({'fm_staff_session':'invalid'}, {},401),
        (photographer, {'X-CSRF-Token':photographer['fm_staff_csrf']},403),
        (admin, {},403), (admin, {'X-CSRF-Token':'wrong'},403),
        ({'fm_staff_session':admin['fm_staff_session']}, {'X-CSRF-Token':admin['fm_staff_csrf']},403),
        ({**admin,'fm_staff_csrf':'forged'}, {'X-CSRF-Token':'forged'},403)]
    for browser, headers, expected in cases:
        assert mutate(app,browser,path,good,method,headers)[0] == expected
        assert state(engine) == before
    for value in ['true','false',1,0,None,[],{}]:
        assert mutate(app,admin,path,{**good,'is_free':value},method)[0] == 422
        assert state(engine) == before
    for body in [{k:v for k,v in good.items() if k != 'is_free'}, {**good,'extra':True}]:
        assert mutate(app,admin,path,body,method)[0] == 422
        assert state(engine) == before
    if method == 'PUT':
        for target,expected in [(uuid.uuid4(),404),(inactive_id,403)]:
            assert mutate(app,admin,f'/api/serving/spas/{target}/is-free',good)[0] == expected
            assert state(engine) == before
    else:
        for bad in [{'name':' '},{'timezone':'Mars/Nowhere'}]:
            assert mutate(app,admin,path,{**good,**bad},method)[0] == 422
            assert state(engine) == before

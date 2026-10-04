"""Task-owned A/B, protected-cookie and settings proof on disposable PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import uuid

from alembic import command
from alembic.config import Config
import numpy as np
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.responses import Response

from face_moment.entrypoints.backend import create_app
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.processing.reference_query import PreparedReferenceQuery
from face_moment.promo.browser_search_profile import (
    BrowserSearchProfile, BrowserSearchProfileRepository, FACE_DENIED_MESSAGE,
    IncompatibleBrowserProfileRevisionError, set_browser_profile_cookie,
)
from face_moment.serving_control.ingest_target import IngestTargetRepository
from face_moment.serving_control.realtime_context import RealtimeContextRepository
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY
from tests.serving_control.test_active_search_date import _login, _request


@pytest.fixture
def profile_fixture():
    with disposable_postgresql_engine('task121') as engine:
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime.now(timezone.utc), **PIPELINE_COMPATIBILITY)
            spa = IngestTargetRepository(session).configure_spa(name='synthetic profile venue',
                timezone='Asia/Dushanbe', serving_pipeline_revision_id=revision.id)
            RealtimeContextRepository(session).provision_reference_settings(spa_id=spa.spa_id,
                pipeline_code=PipelineCode.OPENCV_SFACE, reference_threshold=.73,
                min_query_face_quality=.6, quality_settings={'version':1})
            session.commit()
            revision_id = revision.id
            accounts = {}
            for role in StaffRole:
                account = {'username':f'task121-{role.value}', 'password':'synthetic-strong-password-121'}
                provision_staff_user(session, **account, role=role)
                accounts[role] = account
        app = create_app()
        app.state.role_state['session_factory'] = lambda: Session(engine)
        yield engine, revision_id, spa.spa_id, app, accounts


def query(revision, vector):
    # This is the processing boundary test double, after its single-face/quality gate.
    return PreparedReferenceQuery(revision, np.asarray(vector, dtype=np.float32))


def admit(engine, token, q, confirm=False):
    with Session(engine) as session:
        result = BrowserSearchProfileRepository(session).admit(cookie_token=token, query=q, confirm_reset=confirm)
        session.commit()
        return result


def samples(engine, token):
    with Session(engine) as session:
        record = BrowserSearchProfileRepository(session).find(token)
        return record.a_embedding, record.b_embedding, record.reset_used, record.last_visit_at


def test_fixed_samples_all_transitions_cookie_and_revision(profile_fixture):
    engine, revision, _, _, _ = profile_fixture
    a,b,c,d = [query(revision,v) for v in ([1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1])]
    first=admit(engine,None,a);token=first.cookie_token
    assert first.outcome=='allowed' and first.query is a and len(token)==64
    original=samples(engine,token)
    assert original[:3]==([1,0,0,0],None,False)
    close=query(revision,[1,.01,0,0])
    assert admit(engine,token,close).query is close
    assert samples(engine,token)[:3]==original[:3]
    assert admit(engine,token,b).outcome=='allowed'
    assert admit(engine,token,b).outcome=='allowed'
    before=samples(engine,token)
    refused=admit(engine,token,c)
    assert refused.outcome=='confirmation_required' and refused.query is None
    assert 'чужое лицо' in refused.message
    assert samples(engine,token)[:3]==before[:3]
    # None models no face, multiple faces and native quality-gate failure alike.
    for _ in range(3):
        assert admit(engine,token,None,True).outcome=='retake_required'
        assert samples(engine,token)[:3]==before[:3]
    reset=admit(engine,token,c,True)
    assert reset.outcome=='allowed' and reset.query is c
    assert samples(engine,token)[:3]==([0,0,1,0],None,True)
    assert admit(engine,token,c,True).outcome=='allowed'  # replay does not spend/reset again
    assert admit(engine,token,a).outcome=='allowed'  # B allowed after reset
    denied=admit(engine,token,d,True)
    assert denied.outcome=='face_denied' and denied.message==FACE_DENIED_MESSAGE and denied.query is None
    assert admit(engine,token,a).outcome=='allowed'
    assert samples(engine,token)[3]>original[3]
    current=samples(engine,token)
    with pytest.raises(IncompatibleBrowserProfileRevisionError):
        admit(engine,token,query(uuid.uuid4(),[1,0,0,0]),True)
    assert samples(engine,token)==current
    with pytest.raises(IncompatibleBrowserProfileRevisionError):
        admit(engine,token,query(revision,[1,0]),True)
    assert samples(engine,token)==current
    lost=admit(engine,'unknown-cookie',a)
    assert lost.profile_id!=first.profile_id and samples(engine,lost.cookie_token)[:3]==([1,0,0,0],None,False)
    with Session(engine) as session:
        record=session.get(BrowserSearchProfile,first.profile_id)
        assert record.cookie_digest==hashlib.sha256(token.encode()).hexdigest()
        assert token not in record.cookie_digest
        assert record.a_pipeline_revision_id==record.b_pipeline_revision_id==revision
        assert BrowserSearchProfileRepository(session).find(None) is None
    response=Response();set_browser_profile_cookie(response,token)
    cookie=response.headers['set-cookie']
    for flag in ('HttpOnly','Secure','SameSite=lax','Max-Age=31536000','Path=/'):
        assert flag in cookie
    assert 'Domain=' not in cookie


def test_concurrent_b_and_confirm_reset_are_atomic(profile_fixture):
    engine, revision, _, _, _=profile_fixture
    a,b,c=[query(revision,v) for v in ([1,0,0],[0,1,0],[0,0,1])]
    first=admit(engine,None,a);token=first.cookie_token
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda q: admit(engine,token,q),[b,c]))
    assert sorted(r.outcome for r in results)==['allowed','confirmation_required']
    stored=samples(engine,token)
    third=c if stored[1]==b.embedding.tolist() else b
    with ThreadPoolExecutor(max_workers=2) as pool:
        resets=list(pool.map(lambda _: admit(engine,token,third,True),range(2)))
    assert all(r.outcome=='allowed' for r in resets)
    assert samples(engine,token)[:3]==(third.embedding.tolist(),None,True)


def test_developer_threshold_auth_csrf_validation_and_search_independence(profile_fixture):
    engine,revision,spa,app,accounts=profile_fixture
    path='/api/serving/public-search-settings'
    developer=_login(app,accounts[StaffRole.DEVELOPER])
    operator=_login(app,accounts[StaffRole.OPERATOR])
    photographer=_login(app,accounts[StaffRole.PHOTOGRAPHER])
    payload={'profile_similarity_threshold':.9}
    assert _request(app,'GET',path,cookies={})[0]==401
    for account in (operator,photographer):
        assert _request(app,'GET',path,cookies=account)[0]==403
        assert _request(app,'PUT',path,cookies=account,headers={'X-CSRF-Token':account['fm_staff_csrf']},body=payload)[0]==403
    for account,header,expected in (({},'',401),(developer,'wrong',403)):
        assert _request(app,'PUT',path,cookies=account,headers={'X-CSRF-Token':header},body=payload)[0]==expected
    headers={'X-CSRF-Token':developer['fm_staff_csrf']}
    for value in (-1.1,1.1,True,'0.5',None,'NaN','Infinity'):
        assert _request(app,'PUT',path,cookies=developer,headers=headers,body={'profile_similarity_threshold':value})[0]==422
    assert _request(app,'PUT',path,cookies=developer,headers=headers,body={**payload,'foreign':1})[0]==422
    a=query(revision,[1,0]);candidate=query(revision,[.8,.6])
    token=admit(engine,None,a).cookie_token
    assert admit(engine,token,candidate).outcome=='allowed'
    assert samples(engine,token)[1] is None  # similarity .8 matches default .38
    code,rheaders,body=_request(app,'PUT',path,cookies=developer,headers=headers,body=payload)
    assert code==200 and rheaders['cache-control']=='no-store'
    assert body=={'schema_version':1,**payload}
    assert _request(app,'GET',path,cookies=developer)[2]==body
    assert admit(engine,token,candidate).outcome=='allowed'
    assert samples(engine,token)[1]==candidate.embedding.astype(np.float64).tolist()  # .9 now fills B
    with Session(engine) as session:
        assert RealtimeContextRepository(session).get_reference_settings(spa_id=spa,pipeline_code=PipelineCode.OPENCV_SFACE).reference_threshold==.73
    for endpoint in (-1,1):
        assert _request(app,'PUT',path,cookies=developer,headers=headers,body={'profile_similarity_threshold':endpoint})[0]==200


def test_threshold_one_identical_samples_and_reset_replay(profile_fixture):
    engine, revision, _, app, accounts = profile_fixture
    developer = _login(app, accounts[StaffRole.DEVELOPER])
    assert _request(app, 'PUT', '/api/serving/public-search-settings', cookies=developer,
                    headers={'X-CSRF-Token': developer['fm_staff_csrf']},
                    body={'profile_similarity_threshold': 1})[0] == 200
    a, b, c, d, e = [query(revision, v) for v in
                     ([.8, .6], [1, 0], [.6, -.8], [0, 1], [-1, 0])]
    token = admit(engine, None, a).cookie_token
    for confirm in (False, False, True, True, True):
        result = admit(engine, token, a, confirm)
        assert result.outcome == 'allowed' and result.query is a
        assert samples(engine, token)[:3] == (a.embedding.astype(float).tolist(), None, False)
    assert admit(engine, token, b).outcome == 'allowed'
    fixed = samples(engine, token)[:3]
    assert fixed[1] == b.embedding.astype(float).tolist()
    assert admit(engine, token, b, True).outcome == 'allowed'
    assert samples(engine, token)[:3] == fixed
    assert admit(engine, token, c).outcome == 'confirmation_required'
    assert admit(engine, token, c, True).outcome == 'allowed'
    for confirm in (False, True, True):
        assert admit(engine, token, c, confirm).outcome == 'allowed'
        assert samples(engine, token)[:3] == (c.embedding.astype(float).tolist(), None, True)
    assert admit(engine, token, d).outcome == 'allowed'
    assert admit(engine, token, e, True).outcome == 'face_denied'


def test_threshold_minus_one_antipodal_match_preserves_samples(profile_fixture):
    engine, revision, _, app, accounts = profile_fixture
    developer = _login(app, accounts[StaffRole.DEVELOPER])
    path = '/api/serving/public-search-settings'
    headers = {'X-CSRF-Token': developer['fm_staff_csrf']}
    assert _request(app, 'PUT', path, cookies=developer, headers=headers,
                    body={'profile_similarity_threshold': -1})[0] == 200
    rng = np.random.default_rng(121)
    for _ in range(5):
        vector = rng.standard_normal(128).astype(np.float32)
        vector = vector / np.linalg.norm(vector)
    a, opposite = query(revision, vector), query(revision, -vector)
    token = admit(engine, None, a).cookie_token
    fixed = samples(engine, token)[:3]
    for confirm in (False, True, True):
        result = admit(engine, token, opposite, confirm)
        assert result.outcome == 'allowed' and result.query is opposite
        assert samples(engine, token)[:3] == fixed
    # Clamping the mathematical range must not relax an interior threshold.
    assert _request(app, 'PUT', path, cookies=developer, headers=headers,
                    body={'profile_similarity_threshold': -.999})[0] == 200
    assert admit(engine, token, opposite).outcome == 'allowed'
    assert samples(engine, token)[:3] == (fixed[0], opposite.embedding.astype(float).tolist(), False)


def test_migration_roundtrip_preserves_unrelated_state(profile_fixture):
    engine,_,spa,_,_=profile_fixture
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE public.task121_marker (value text NOT NULL)'))
        connection.execute(text("INSERT INTO public.task121_marker VALUES ('preserve')"))
    # Downgrade only this task revision on the unique disposable database.
    command.downgrade(Config('alembic.ini'),'0027_preview_phash')
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('face_moment.browser_search_profiles')")) is None
        assert connection.scalar(text("SELECT to_regclass('face_moment.public_search_settings')")) is None
        assert connection.scalar(text('SELECT value FROM public.task121_marker'))=='preserve'
        assert connection.scalar(text('SELECT count(*) FROM face_moment.spas WHERE id=:id'),{'id':spa})==1
    command.upgrade(Config('alembic.ini'),'head')
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT profile_similarity_threshold FROM face_moment.public_search_settings'))==.38
        assert connection.scalar(text('SELECT reference_threshold FROM face_moment.reference_search_settings'))==.73
        assert connection.scalar(text('SELECT value FROM public.task121_marker'))=='preserve'


from tests.infrastructure.test_proxy_forwarding import proxy_chain


def test_threshold_endpoint_reaches_backend_through_https_edge(proxy_chain):
    request, _ = proxy_chain
    code, body = request(path='/api/serving/public-search-settings')
    assert code == 200 and body['origin'] == 'https://face-moment.ru'

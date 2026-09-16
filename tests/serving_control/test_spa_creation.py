"""Real database/API checks for staff venue creation."""
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from face_moment.serving_control.ingest_target import Spa
from face_moment.serving_control.realtime_context import RealtimeContextRepository
from tests.serving_control.test_active_search_date import active_search_date_fixture, _login, _request


@pytest.mark.parametrize('role', ['operator', 'developer'])
def test_create_venue_with_shared_revision_and_independent_settings(active_search_date_fixture, role):
    f = active_search_date_fixture
    cookies = _login(f.app, getattr(f, role))
    code, headers, result = _request(f.app, 'POST', '/api/serving/spas', cookies=cookies,
        headers={'X-CSRF-Token': cookies['fm_staff_csrf']},
        body={'name': '  Новая <площадка>  ', 'timezone': 'Europe/Moscow'})
    assert code == 201 and headers['cache-control'] == 'no-store'
    new_id = uuid.UUID(result['spa_id'])
    assert result['name'] == 'Новая <площадка>'
    with Session(f.engine) as session:
        old, new = session.get(Spa, f.spa_id), session.get(Spa, new_id)
        assert new.serving_pipeline_revision_id == old.serving_pipeline_revision_id
        assert old.name.startswith('task068-active-')
        assert new.timezone == 'Europe/Moscow' and new.search_today
        assert (new.photo_yunet_threshold, new.capture_blazeface_threshold) == (.9, .5)
        settings = RealtimeContextRepository(session).read_calibration_serving_snapshot(spa_id=new_id)
        assert settings.reference_threshold == .38 and settings.min_query_face_quality == .5
    page = _request(f.app, 'GET', '/staff/spas', cookies=cookies)[2]
    assert 'Новая &lt;площадка&gt;' in page and f'data-spa-id="{new_id}"' in page
    assert 'data-spa-create' in page and 'Добавить площадку' in page


def test_create_rejects_bad_input_access_and_conflicting_model_without_writes(active_search_date_fixture):
    f = active_search_date_fixture
    admin = _login(f.app, f.operator)
    photographer = _login(f.app, f.photographer)
    good = {'name': 'Новая', 'timezone': 'UTC'}
    cases = [({}, {}, good, 401), (photographer, {'X-CSRF-Token': photographer['fm_staff_csrf']}, good, 403),
        (admin, {}, good, 403)]
    for payload in ({**good, 'name': '   '}, {**good, 'timezone': 'Mars/Nowhere'},
                    {**good, 'pipeline_revision_id': str(uuid.uuid4())}):
        cases.append((admin, {'X-CSRF-Token': admin['fm_staff_csrf']}, payload, 422))
    with Session(f.engine) as session:
        count = session.scalar(select(func.count()).select_from(Spa))
    for cookies, headers, payload, expected in cases:
        assert _request(f.app, 'POST', '/api/serving/spas', cookies=cookies, headers=headers, body=payload)[0] == expected
    with Session(f.engine) as session:
        # No active selection is not a reason to invent a model.
        session.get(Spa, f.spa_id).active = False
        session.commit()
    assert _request(f.app, 'POST', '/api/serving/spas', cookies=admin,
        headers={'X-CSRF-Token': admin['fm_staff_csrf']}, body=good)[0] == 409
    with Session(f.engine) as session:
        assert session.scalar(select(func.count()).select_from(Spa)) == count

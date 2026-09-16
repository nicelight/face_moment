"""Screen creation against disposable PostgreSQL and the real HTTP application."""
import uuid

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from face_moment.serving_control.display_client_access import DisplayClient
from face_moment.serving_control.display_client_auth import authenticate_display_client, DisplayClientRateLimiter
from face_moment.serving_control.ingest_target import Spa
from tests.serving_control.test_display_client_admin import display_client_admin_fixture
from tests.serving_control.test_active_search_date import _request


@pytest.mark.parametrize('role', ['operator', 'developer'])
def test_create_multiple_screens_with_distinct_tokens_and_selected_venue(display_client_admin_fixture, role):
    f = display_client_admin_fixture
    cookies = getattr(f, role + '_cookies')
    venue_a, venue_b = f.display_clients[0][2], f.display_clients[1][2]
    created = []
    for venue in (venue_a, venue_a, venue_b):
        code, headers, body = _request(f.app, 'POST', '/api/serving/display-clients', cookies=cookies,
            headers={'X-CSRF-Token': cookies['fm_staff_csrf']},
            body={'name': '  Экран <новый>  ', 'spa_id': str(venue)})
        assert code == 201 and headers['cache-control'] == 'no-store'
        assert body['spa_id'] == str(venue)
        created.append((uuid.UUID(body['display_client_id']), venue))
    with Session(f.engine) as session:
        tokens = []
        for client_id, venue in created:
            client = session.get(DisplayClient, client_id)
            assert client.name == 'Экран <новый>' and client.active
            principal = authenticate_display_client(session, authorization='Bearer ' + client.token_value,
                ip_address='127.0.0.1', rate_limiter=DisplayClientRateLimiter(limit=100, window_seconds=60))
            assert principal.spa_id == venue
            tokens.append(client.token_value)
        assert len(set(tokens)) == 3
        for client_id, name, venue, active, token in f.display_clients:
            client = session.get(DisplayClient, client_id)
            assert (client.name, client.spa_id, client.active, client.token_value) == (name, venue, active, token)
        venue_name = session.get(Spa, venue_a).name
    page = _request(f.app, 'GET', '/staff/display-clients', cookies=cookies)[2]
    assert 'Экран &lt;новый&gt;' in page and 'Добавить экран' in page
    assert f'<option value="{venue_a}">{venue_name}</option>' in page
    assert all(token in page for token in tokens)


def test_screen_creation_rejects_bad_access_and_invalid_or_inactive_venue(display_client_admin_fixture):
    f = display_client_admin_fixture
    admin, photo = f.operator_cookies, f.photographer_cookies
    venue = f.display_clients[0][2]
    good = {'name': 'Экран', 'spa_id': str(venue)}
    headers = {'X-CSRF-Token': admin['fm_staff_csrf']}
    cases = [({}, {}, good, 401), (photo, {'X-CSRF-Token': photo['fm_staff_csrf']}, good, 403),
        (admin, {}, good, 403), (admin, headers, {**good, 'name': '   '}, 422),
        (admin, headers, {**good, 'spa_id': 'bad'}, 422),
        (admin, headers, {**good, 'spa_id': str(uuid.uuid4())}, 404),
        (admin, headers, {**good, 'token_value': 'chosen'}, 422)]
    for cookies, request_headers, payload, expected in cases:
        assert _request(f.app, 'POST', '/api/serving/display-clients', cookies=cookies,
            headers=request_headers, body=payload)[0] == expected
    with Session(f.engine) as session:
        session.get(Spa, venue).active = False
        session.commit()
    assert _request(f.app, 'POST', '/api/serving/display-clients', cookies=admin,
        headers=headers, body=good)[0] == 409
    page = _request(f.app, 'GET', '/staff/display-clients', cookies=admin)[2]
    assert f'<option value="{venue}">' not in page
    with Session(f.engine) as session:
        assert session.scalar(select(func.count()).select_from(DisplayClient)) == len(f.display_clients)

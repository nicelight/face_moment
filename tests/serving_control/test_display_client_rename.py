from types import SimpleNamespace
import uuid

import pytest

from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import CsrfValidationError
from face_moment.serving_control import display_client_admin as admin
from face_moment.serving_control.display_client_access import DisplayClientRepository


def test_rename_changes_only_normalized_name() -> None:
    client = SimpleNamespace(name="Old", token_value="unchanged", active=True)
    session = SimpleNamespace(scalar=lambda _: client, flush=lambda: None)
    repository = DisplayClientRepository(session)
    renamed = repository.rename(uuid.uuid4(), "  Экран у выхода  ")
    assert renamed.name == "Экран у выхода"
    assert renamed.token_value == "unchanged"
    assert renamed.active is True
    with pytest.raises(ValueError):
        repository.rename(uuid.uuid4(), "   ")
    assert client.name == "Экран у выхода"


@pytest.mark.parametrize("role", [StaffRole.OPERATOR, StaffRole.DEVELOPER, StaffRole.PHOTOGRAPHER])
def test_rename_requires_admin_role_and_passes_csrf_to_auth(monkeypatch, role) -> None:
    calls = []
    client_id = uuid.uuid4()
    def authenticate(session, **kwargs):
        assert kwargs == dict(session_token="session", csrf_cookie_token="csrf", csrf_header_token="csrf")
        return SimpleNamespace(role=role)
    monkeypatch.setattr(admin, "authenticate_unsafe_staff_request", authenticate)
    monkeypatch.setattr(admin, "DisplayClientRepository", lambda session: SimpleNamespace(rename=lambda id, name: calls.append((id, name)) or SimpleNamespace(name=name)))
    def rename():
        return admin.rename_display_client(object(), session_token="session", csrf_cookie_token="csrf", csrf_header_token="csrf", display_client_id=client_id, name="Выход")
    if role is StaffRole.PHOTOGRAPHER:
        with pytest.raises(admin.DisplayClientAdminAccessDeniedError):
            rename()
        assert calls == []
    else:
        assert rename() == "Выход"
        assert calls == [(client_id, "Выход")]


def test_csrf_rejection_prevents_owner_write(monkeypatch) -> None:
    def reject(*args, **kwargs):
        raise CsrfValidationError
    monkeypatch.setattr(admin, "authenticate_unsafe_staff_request", reject)
    monkeypatch.setattr(admin, "DisplayClientRepository", lambda session: pytest.fail("write after rejected CSRF"))
    with pytest.raises(CsrfValidationError):
        admin.rename_display_client(object(), session_token="session", csrf_cookie_token="csrf", csrf_header_token="wrong", display_client_id=uuid.uuid4(), name="Выход")


def test_rename_http_commits_only_success_and_maps_access_errors(monkeypatch) -> None:
    from fastapi import FastAPI, HTTPException
    from face_moment.serving_control import http
    from face_moment.serving_control.display_client_access import DisplayClientNotFoundError
    from face_moment.platform.auth.sessions import InvalidSessionError
    commits = []
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def commit(self): commits.append(True)
    app = FastAPI()
    http.register_display_client_admin_routes(app, session_factory=Session)
    route = next(r for r in app.routes if getattr(r, 'path', '') == '/api/serving/display-clients/{display_client_id}/name')
    client_id = uuid.uuid4()
    def invoke():
        return route.endpoint(client_id, http.DisplayClientNameRequest(name='Выход'), 'session', 'csrf', 'csrf')
    monkeypatch.setattr(http, 'rename_display_client', lambda *args, **kwargs: 'Выход')
    response = invoke()
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert commits == [True]
    for error, status in [(InvalidSessionError, 401), (CsrfValidationError, 403), (admin.DisplayClientAdminAccessDeniedError, 403), (DisplayClientNotFoundError, 404), (ValueError, 422)]:
        def fail(*args, **kwargs): raise error()
        monkeypatch.setattr(http, 'rename_display_client', fail)
        with pytest.raises(HTTPException) as caught:
            invoke()
        assert caught.value.status_code == status
        assert commits == [True]

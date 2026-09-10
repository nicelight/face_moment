from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import (
    InvalidSessionError,
    get_current_principal,
    authenticate_unsafe_staff_request,
)
from face_moment.serving_control.display_client_access import DisplayClientRepository


@dataclass(frozen=True, slots=True)
class DisplayClientAdminRecord:
    """The complete current-kiosk projection permitted on the Admin page."""

    display_client_id: uuid.UUID
    name: str
    spa_id: uuid.UUID
    active: bool
    token_value: str


class DisplayClientAdminAccessDeniedError(PermissionError):
    """The authenticated staff principal is not an Admin."""


def rename_display_client(
    database_session: Session, *, session_token: str | None,
    csrf_cookie_token: str | None, csrf_header_token: str | None,
    display_client_id: uuid.UUID, name: str,
) -> str:
    principal = authenticate_unsafe_staff_request(
        database_session, session_token=session_token,
        csrf_cookie_token=csrf_cookie_token, csrf_header_token=csrf_header_token,
    )
    if principal.role not in (StaffRole.OPERATOR, StaffRole.DEVELOPER):
        raise DisplayClientAdminAccessDeniedError
    return DisplayClientRepository(database_session).rename(display_client_id, name).name


def read_display_client_admin(
    database_session: Session,
    *,
    session_token: str | None,
) -> tuple[DisplayClientAdminRecord, ...]:
    """Authorize and read all current display-client values without mutation."""

    principal = get_current_principal(
        database_session,
        session_token=session_token,
    )
    if principal.role not in (StaffRole.OPERATOR, StaffRole.DEVELOPER):
        raise DisplayClientAdminAccessDeniedError

    clients = DisplayClientRepository(database_session).list_all()
    return tuple(
        DisplayClientAdminRecord(
            display_client_id=client.id,
            name=client.name,
            spa_id=client.spa_id,
            active=client.active,
            token_value=client.token_value,
        )
        for client in clients
    )


__all__ = [
    "DisplayClientAdminAccessDeniedError",
    "DisplayClientAdminRecord",
    "InvalidSessionError",
    "read_display_client_admin",
]

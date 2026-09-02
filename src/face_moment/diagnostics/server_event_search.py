"""Developer-only diagnostics application boundary for server-event search."""

from __future__ import annotations

from sqlalchemy.orm import Session

from face_moment.diagnostics.server_events import (
    ServerEventProjection,
    ServerEventRepository,
    ServerEventSearchFilters,
)
from face_moment.platform.auth.principals import StaffPrincipal, StaffRole


class ServerEventSearchAccessDeniedError(PermissionError):
    """The current staff principal cannot inspect structured server events."""


def search_server_events(
    database_session: Session,
    *,
    principal: StaffPrincipal,
    filters: ServerEventSearchFilters,
) -> tuple[ServerEventProjection, ...]:
    """Authorize the current principal and query diagnostics-owned rows."""

    authorize_server_event_search(principal)
    return ServerEventRepository(database_session).search(filters)


def authorize_server_event_search(principal: StaffPrincipal) -> None:
    """Keep business authorization inside diagnostics rather than staff access."""

    if principal.role is not StaffRole.DEVELOPER:
        raise ServerEventSearchAccessDeniedError


__all__ = [
    "ServerEventSearchAccessDeniedError",
    "authorize_server_event_search",
    "search_server_events",
]

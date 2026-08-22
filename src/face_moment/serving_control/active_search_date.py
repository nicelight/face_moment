from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import (
    authenticate_unsafe_staff_request,
    get_current_principal,
)
from face_moment.serving_control.ingest_target import Spa
from face_moment.serving_control.realtime_context import RealtimeContextRepository


class ActiveSearchDateAccessDeniedError(PermissionError):
    """The authenticated principal cannot administer active search dates."""


class ActiveSearchDateSpaNotFoundError(LookupError):
    """The requested SPA does not exist."""


@dataclass(frozen=True, slots=True)
class ActiveSearchDateRecord:
    spa_id: uuid.UUID
    active_visit_date: date | None
    settings_revision: int
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ActiveSearchDateSpa:
    spa_id: uuid.UUID
    name: str


def read_active_search_date(
    database_session: Session,
    *,
    session_token: str | None,
    spa_id: uuid.UUID,
) -> ActiveSearchDateRecord:
    principal = get_current_principal(
        database_session,
        session_token=session_token,
    )
    _authorize(principal.role)
    return _record_for_spa(_load_accessible_spa(database_session, spa_id))


def update_active_search_date(
    database_session: Session,
    *,
    session_token: str | None,
    csrf_cookie_token: str | None,
    csrf_header_token: str | None,
    spa_id: uuid.UUID,
    active_visit_date: date,
) -> ActiveSearchDateRecord:
    principal = authenticate_unsafe_staff_request(
        database_session,
        session_token=session_token,
        csrf_cookie_token=csrf_cookie_token,
        csrf_header_token=csrf_header_token,
    )
    _authorize(principal.role)
    _load_accessible_spa(database_session, spa_id)
    spa = RealtimeContextRepository(database_session).update_active_visit_date(
        spa_id=spa_id,
        active_visit_date=active_visit_date,
    )
    return _record_for_spa(spa)


def list_active_search_date_spas(
    database_session: Session,
    *,
    session_token: str | None,
) -> tuple[ActiveSearchDateSpa, ...]:
    principal = get_current_principal(
        database_session,
        session_token=session_token,
    )
    _authorize(principal.role)
    spas = database_session.scalars(
        select(Spa).where(Spa.active.is_(True)).order_by(Spa.name, Spa.id)
    )
    return tuple(ActiveSearchDateSpa(spa_id=spa.id, name=spa.name) for spa in spas)


def _authorize(role: StaffRole) -> None:
    if role is not StaffRole.OPERATOR:
        raise ActiveSearchDateAccessDeniedError


def _load_accessible_spa(database_session: Session, spa_id: uuid.UUID) -> Spa:
    spa = database_session.scalar(select(Spa).where(Spa.id == spa_id))
    if spa is None:
        raise ActiveSearchDateSpaNotFoundError(str(spa_id))
    if not spa.active:
        raise ActiveSearchDateAccessDeniedError
    return spa


def _record_for_spa(spa: Spa) -> ActiveSearchDateRecord:
    return ActiveSearchDateRecord(
        spa_id=spa.id,
        active_visit_date=spa.active_visit_date,
        settings_revision=spa.settings_revision,
        updated_at=spa.settings_updated_at,
    )


__all__ = [
    "ActiveSearchDateAccessDeniedError",
    "ActiveSearchDateRecord",
    "ActiveSearchDateSpa",
    "ActiveSearchDateSpaNotFoundError",
    "list_active_search_date_spas",
    "read_active_search_date",
    "update_active_search_date",
]

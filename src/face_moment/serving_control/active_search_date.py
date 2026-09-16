from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import (
    authenticate_unsafe_staff_request,
    get_current_principal,
)
from face_moment.serving_control.ingest_target import IngestTarget, IngestTargetRepository, Spa
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
    timezone: str = "Asia/Novosibirsk"
    search_today: bool = True
    date_from: date | None = None
    date_to: date | None = None
    photo_yunet_threshold: float = 0.9
    capture_blazeface_threshold: float = 0.5


@dataclass(frozen=True, slots=True)
class SearchDatesRecord:
    spa_id: uuid.UUID
    search_today: bool
    date_from: date | None
    date_to: date | None
    timezone: str
    today: date
    settings_revision: int
    updated_at: datetime | None


def read_search_dates(
    database_session: Session, *, session_token: str | None, spa_id: uuid.UUID,
) -> SearchDatesRecord:
    principal = get_current_principal(database_session, session_token=session_token)
    _authorize(principal.role)
    return _search_dates_record(_load_accessible_spa(database_session, spa_id))


def update_search_dates(
    database_session: Session, *, session_token: str | None,
    csrf_cookie_token: str | None, csrf_header_token: str | None,
    spa_id: uuid.UUID, search_today: bool, date_from: date | None, date_to: date | None,
) -> SearchDatesRecord:
    principal = authenticate_unsafe_staff_request(
        database_session, session_token=session_token,
        csrf_cookie_token=csrf_cookie_token, csrf_header_token=csrf_header_token,
    )
    _authorize(principal.role)
    _load_accessible_spa(database_session, spa_id)
    spa = RealtimeContextRepository(database_session).update_search_dates(
        spa_id=spa_id, search_today=search_today, date_from=date_from, date_to=date_to,
    )
    return _search_dates_record(spa)


def _search_dates_record(spa: Spa) -> SearchDatesRecord:
    return SearchDatesRecord(
        spa_id=spa.id, search_today=spa.search_today,
        date_from=spa.active_visit_date, date_to=spa.active_visit_date_to,
        timezone=spa.timezone, today=datetime.now(timezone.utc).astimezone(ZoneInfo(spa.timezone)).date(),
        settings_revision=spa.settings_revision,
        updated_at=spa.settings_updated_at.astimezone(timezone.utc) if spa.settings_updated_at else None,
    )


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


def create_spa(
    database_session: Session, *, session_token: str | None,
    csrf_cookie_token: str | None, csrf_header_token: str | None,
    name: str, timezone: str,
) -> IngestTarget:
    principal = authenticate_unsafe_staff_request(
        database_session, session_token=session_token,
        csrf_cookie_token=csrf_cookie_token, csrf_header_token=csrf_header_token,
    )
    _authorize(principal.role)
    repository = IngestTargetRepository(database_session)
    revision = repository.resolve_committed_serving_revision()
    venue = repository.configure_spa(name=name, timezone=timezone,
        serving_pipeline_revision_id=revision.id)
    RealtimeContextRepository(database_session).provision_reference_settings(
        spa_id=venue.spa_id, pipeline_code=revision.pipeline_code,
        reference_threshold=0.38, min_query_face_quality=0.5,
        quality_settings={"version": 1},
    )
    return venue


def rename_spa(
    database_session: Session,
    *,
    session_token: str | None,
    csrf_cookie_token: str | None,
    csrf_header_token: str | None,
    spa_id: uuid.UUID,
    name: str,
) -> str:
    principal = authenticate_unsafe_staff_request(
        database_session, session_token=session_token,
        csrf_cookie_token=csrf_cookie_token, csrf_header_token=csrf_header_token,
    )
    _authorize(principal.role)
    _load_accessible_spa(database_session, spa_id)
    return IngestTargetRepository(database_session).rename_spa(spa_id, name)


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
    return tuple(ActiveSearchDateSpa(
        spa_id=spa.id, name=spa.name, timezone=spa.timezone,
        search_today=spa.search_today, date_from=spa.active_visit_date,
        date_to=spa.active_visit_date_to,
        photo_yunet_threshold=spa.photo_yunet_threshold,
        capture_blazeface_threshold=spa.capture_blazeface_threshold,
    ) for spa in spas)


def _authorize(role: StaffRole) -> None:
    if role not in {StaffRole.OPERATOR, StaffRole.DEVELOPER}:
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

"""Bounded promo-owned Attempt investigation query."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.promo.attempt import PromoAttempt
from face_moment.promo.client_timing import (
    CoreTimelineProjection,
    project_core_timeline,
)


AttemptProcessingStatus = Literal[
    "accepted",
    "searching",
    "result_issued",
    "no_success",
    "interrupted",
    "deadline",
    "internal_failure",
]

_PROCESSING_STATUSES = frozenset(
    {
        "accepted",
        "searching",
        "result_issued",
        "no_success",
        "interrupted",
        "deadline",
        "internal_failure",
    }
)
_MAX_RESULTS = 100


@dataclass(frozen=True, slots=True)
class AttemptInvestigationFilters:
    """Exact typed filters accepted by the promo investigation boundary."""

    attempt_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    created_at_from: datetime | None = None
    created_at_to: datetime | None = None
    processing_status: AttemptProcessingStatus | None = None

    def __post_init__(self) -> None:
        _require_utc(self.created_at_from, field_name="created_at_from")
        _require_utc(self.created_at_to, field_name="created_at_to")
        if (
            self.created_at_from is not None
            and self.created_at_to is not None
            and self.created_at_to <= self.created_at_from
        ):
            raise ValueError("created_at_to must be later than created_at_from")
        if (
            self.processing_status is not None
            and self.processing_status not in _PROCESSING_STATUSES
        ):
            raise ValueError("processing_status is unsupported")


@dataclass(frozen=True, slots=True)
class AttemptInvestigationProjection:
    """Immutable promo truth exposed without ORM or write authority."""

    attempt_id: uuid.UUID
    correlation_id: uuid.UUID
    spa_id: uuid.UUID
    created_at: datetime
    processing_status: str
    domain_outcome: str | None
    timeline: CoreTimelineProjection


def query_attempts(
    database_session: Session,
    *,
    filters: AttemptInvestigationFilters,
) -> tuple[AttemptInvestigationProjection, ...]:
    """Return the newest bounded immutable projections matching every filter."""

    statement = select(PromoAttempt)
    if filters.attempt_id is not None:
        statement = statement.where(PromoAttempt.id == filters.attempt_id)
    if filters.correlation_id is not None:
        statement = statement.where(
            PromoAttempt.client_attempt_id == filters.correlation_id
        )
    if filters.created_at_from is not None:
        statement = statement.where(
            PromoAttempt.created_at >= filters.created_at_from
        )
    if filters.created_at_to is not None:
        statement = statement.where(PromoAttempt.created_at < filters.created_at_to)
    if filters.processing_status is not None:
        statement = statement.where(
            PromoAttempt.processing_status == filters.processing_status
        )

    rows = database_session.scalars(
        statement.order_by(
            PromoAttempt.created_at.desc(),
            PromoAttempt.id.desc(),
        ).limit(_MAX_RESULTS)
    ).all()
    evaluated_at = datetime.now(timezone.utc)
    projections: list[AttemptInvestigationProjection] = []
    for row in rows:
        timeline = project_core_timeline(row, now=evaluated_at)
        projections.append(
            AttemptInvestigationProjection(
                attempt_id=row.id,
                correlation_id=row.client_attempt_id,
                spa_id=row.spa_id,
                created_at=timeline.created_at,
                processing_status=timeline.processing_status,
                domain_outcome=timeline.domain_outcome,
                timeline=timeline,
            )
        )
    return tuple(projections)


def _require_utc(value: datetime | None, *, field_name: str) -> None:
    if value is None:
        return
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be an aware UTC datetime")


__all__ = [
    "AttemptInvestigationFilters",
    "AttemptInvestigationProjection",
    "AttemptProcessingStatus",
    "query_attempts",
]

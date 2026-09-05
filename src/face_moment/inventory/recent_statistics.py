"""Inventory-owned direct recent Photo statistics projection."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from face_moment.inventory.photo_persistence import Photo
from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import get_current_principal
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.serving_control.ingest_target import Spa

_WINDOW_MINUTES = (1, 5, 60)
_UNPROCESSED = ("pending", "processing")
_PROCESSED = ("ready", "no_faces")


class RecentStatisticsAccessDeniedError(PermissionError):
    """The current staff principal may not read recent statistics."""


class RecentStatisticsNotFoundError(LookupError):
    """The requested СПА does not exist."""


@dataclass(frozen=True, slots=True)
class RecentStatistics:
    """Exact response assembled from one observed direct aggregate."""

    spa_id: uuid.UUID
    observed_at: datetime
    windows: tuple[dict[str, int], ...]

    def as_response(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "spa_id": str(self.spa_id),
            "observed_at": _utc_z(self.observed_at),
            "windows": list(self.windows),
        }


def authorize_recent_statistics_access(
    database_session: Session, *, session_token: str | None
) -> None:
    """Authorize the operational statistics surface without reading it."""

    principal = get_current_principal(database_session, session_token=session_token)
    if principal.role not in {StaffRole.OPERATOR, StaffRole.DEVELOPER}:
        raise RecentStatisticsAccessDeniedError


def read_recent_statistics(
    database_session: Session,
    *,
    session_token: str | None,
    spa_id: uuid.UUID,
    observed_at: datetime | None = None,
) -> RecentStatistics:
    """Read all accepted windows through one active admission-lineage aggregate."""

    authorize_recent_statistics_access(database_session, session_token=session_token)
    if database_session.get(Spa, spa_id) is None:
        raise RecentStatisticsNotFoundError

    observed = _observed_at() if observed_at is None else observed_at.astimezone(UTC)
    columns: list[ColumnElement[int]] = []
    for minutes in _WINDOW_MINUTES:
        lower = observed - timedelta(minutes=minutes)
        accepted_in_window = and_(
            Photo.accepted_at >= lower,
            Photo.accepted_at <= observed,
        )
        transitioned_in_window = and_(
            PhotoPipelineState.status_changed_at >= lower,
            PhotoPipelineState.status_changed_at <= observed,
        )
        columns.extend(
            (
                func.count().filter(accepted_in_window),
                func.count().filter(
                    accepted_in_window,
                    PhotoPipelineState.status.in_(_UNPROCESSED),
                ),
                func.count().filter(
                    transitioned_in_window,
                    PhotoPipelineState.status.in_(_PROCESSED),
                ),
                func.count().filter(
                    transitioned_in_window,
                    PhotoPipelineState.status == "failed",
                ),
            )
        )
    counts = database_session.execute(
        select(*columns)
        .select_from(Photo)
        .join(
            PhotoPipelineState,
            and_(
                PhotoPipelineState.photo_id == Photo.id,
                PhotoPipelineState.pipeline_revision_id
                == Photo.admission_pipeline_revision_id,
            ),
        )
        .where(Photo.spa_id == spa_id, Photo.is_active.is_(True))
    ).one()

    windows = tuple(
        {
            "minutes": minutes,
            "new": int(counts[index * 4]),
            "unprocessed": int(counts[index * 4 + 1]),
            "processed": int(counts[index * 4 + 2]),
            "failed": int(counts[index * 4 + 3]),
        }
        for index, minutes in enumerate(_WINDOW_MINUTES)
    )
    return RecentStatistics(spa_id=spa_id, observed_at=observed, windows=windows)


def _observed_at() -> datetime:
    return datetime.now(UTC)


def _utc_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

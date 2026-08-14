"""Inventory-owned authenticated processing-health outcome assembly."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from face_moment.infrastructure import capacity
from face_moment.infrastructure.capacity import CapacityObservation
from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import get_current_principal
from face_moment.processing.health_projection import ProcessingHealthProjectionRepository
from face_moment.processing.ingest_slo import IngestToSearchableProjectionRepository
from face_moment.serving_control.ingest_target import Spa


class ProcessingHealthAccessDeniedError(PermissionError):
    """The active staff principal may not read operational health."""


class ProcessingHealthNotFoundError(LookupError):
    """The requested inventory-visible SPA does not exist."""


class InvalidProcessingHealthIntervalError(ValueError):
    """The controlled SLO interval is incomplete, naive or not increasing."""


@dataclass(frozen=True, slots=True)
class ProcessingHealth:
    """Exact safe processing-health response assembled by inventory."""

    spa_id: uuid.UUID
    observed_at: datetime
    queue: dict[str, object]
    ingest_to_searchable: dict[str, object] | None
    postgresql: CapacityObservation
    minio: CapacityObservation

    def as_response(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "spa_id": str(self.spa_id),
            "observed_at": _utc_z(self.observed_at),
            "queue": self.queue,
            "ingest_to_searchable": self.ingest_to_searchable,
            "storage": {
                "postgresql": _capacity_response(self.postgresql),
                "minio": _capacity_response(self.minio),
            },
        }


def authorize_processing_health_access(
    database_session: Session,
    *,
    session_token: str | None,
) -> None:
    """Authorize the inventory-owned operational-health view without reading it."""

    principal = get_current_principal(database_session, session_token=session_token)
    if principal.role not in {StaffRole.OPERATOR, StaffRole.DEVELOPER}:
        raise ProcessingHealthAccessDeniedError


def read_processing_health(
    database_session: Session,
    *,
    settings: Settings,
    session_token: str | None,
    spa_id: uuid.UUID,
    accepted_from: datetime | None,
    accepted_before: datetime | None,
) -> ProcessingHealth:
    """Authorize and assemble current owner-backed observations without writes."""

    authorize_processing_health_access(
        database_session,
        session_token=session_token,
    )
    if database_session.get(Spa, spa_id) is None:
        raise ProcessingHealthNotFoundError
    accepted_from, accepted_before = _normalize_interval(
        accepted_from, accepted_before
    )

    observed_at = datetime.now(UTC)
    queue = ProcessingHealthProjectionRepository(database_session).resolve(spa_id=spa_id)
    ingest_to_searchable: dict[str, object] | None = None
    if accepted_from is not None and accepted_before is not None:
        projection = IngestToSearchableProjectionRepository(database_session).resolve(
            spa_id=spa_id,
            accepted_from=accepted_from,
            accepted_before=accepted_before,
            evaluated_at=observed_at,
        )
        ingest_to_searchable = {
            "accepted_from": _utc_z(accepted_from),
            "accepted_before": _utc_z(accepted_before),
            "population": projection.population,
            "success_under_15_minutes": projection.success_under_15_minutes,
            "breach": projection.breach,
            "open": projection.open,
            "success_ratio": projection.success_ratio,
            "meets_95_percent": projection.meets_95_percent,
        }

    return ProcessingHealth(
        spa_id=spa_id,
        observed_at=observed_at,
        queue={
            "pending": queue.pending,
            "processing": queue.processing,
            "ready": queue.ready,
            "no_faces": queue.no_faces,
            "failed": queue.failed,
            "oldest_pending_accepted_at": _utc_z(queue.oldest_pending_accepted_at),
            "current_operation": queue.current_operation,
            "operation_started_at": _utc_z(queue.operation_started_at),
            "worker_started_at": _utc_z(queue.worker_started_at),
            "last_recovery_at": _utc_z(queue.last_recovery_at),
            "last_recovered_count": queue.last_recovered_count,
        },
        ingest_to_searchable=ingest_to_searchable,
        postgresql=capacity.observe_capacity(
            settings.postgresql_capacity_view_path,
            low_threshold_bytes=settings.postgresql_capacity_low_threshold_bytes,
        ),
        minio=capacity.observe_capacity(
            settings.minio_capacity_view_path,
            low_threshold_bytes=settings.minio_capacity_low_threshold_bytes,
        ),
    )


def _normalize_interval(
    accepted_from: datetime | None, accepted_before: datetime | None
) -> tuple[datetime | None, datetime | None]:
    if (accepted_from is None) != (accepted_before is None):
        raise InvalidProcessingHealthIntervalError
    if accepted_from is None or accepted_before is None:
        return accepted_from, accepted_before
    if accepted_from.utcoffset() is None or accepted_before.utcoffset() is None:
        raise InvalidProcessingHealthIntervalError

    normalized_from = accepted_from.astimezone(UTC)
    normalized_before = accepted_before.astimezone(UTC)
    if normalized_from >= normalized_before:
        raise InvalidProcessingHealthIntervalError
    return normalized_from, normalized_before


def _capacity_response(observation: CapacityObservation) -> dict[str, object]:
    return {
        "status": observation.status,
        "available_bytes": observation.available_bytes,
        "low_threshold_bytes": observation.low_threshold_bytes,
        "observed_at": _utc_z(observation.observed_at),
        "error": observation.error,
    }


def _utc_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

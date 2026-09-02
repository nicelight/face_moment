"""Promo-owned browser response timing boundary and core timeline projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import uuid

from sqlalchemy.orm import Session

from face_moment.promo.attempt import (
    PromoAttempt,
    PromoAttemptRepository,
    derive_effective_display_status,
)


_REPORT_FIELDS = {"schema_version", "response_received_ms"}
_TERMINAL_PROCESSING_STATUSES = {
    "result_issued",
    "no_success",
    "interrupted",
    "deadline",
    "internal_failure",
}


class InvalidClientTimingReportError(ValueError):
    """The request is outside the exact version-1 timing contract."""


class ClientTimingConflictError(ValueError):
    """The scoped Attempt cannot accept this response marker."""


@dataclass(frozen=True, slots=True)
class ClientTimingReport:
    response_received_ms: int


@dataclass(frozen=True, slots=True)
class CoreTimelineProjection:
    """Promo-owned core timing fields and bounded machine issue tags."""

    reference_series_ready_at: datetime
    reference_series_ready_elapsed_ms: int
    local_detection_completed_ms: int
    request_started_ms: int
    response_received_ms: int | None
    created_at: datetime
    slot_decided_at: datetime | None
    search_started_at: datetime | None
    search_finished_at: datetime | None
    processing_status: str
    domain_outcome: str | None
    display_status: str
    display_reported_at: datetime | None
    qr_fully_visible_elapsed_ms: int | None
    issue_tags: tuple[str, ...]


def parse_client_timing_report(
    body: bytes, content_type: str | None
) -> ClientTimingReport:
    """Parse exact UTF-8 JSON without accepting duplicate or unknown fields."""

    media_type = "" if content_type is None else content_type.split(";", 1)[0]
    if media_type.strip().casefold() != "application/json":
        raise InvalidClientTimingReportError("application/json is required")
    try:
        payload = json.loads(body.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidClientTimingReportError("body must be strict UTF-8 JSON") from error
    if not isinstance(payload, dict) or set(payload) != _REPORT_FIELDS:
        raise InvalidClientTimingReportError("timing report fields are invalid")
    schema_version = payload["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
    ):
        raise InvalidClientTimingReportError("schema_version must be 1")
    response_received_ms = payload["response_received_ms"]
    if (
        not isinstance(response_received_ms, int)
        or isinstance(response_received_ms, bool)
        or response_received_ms < 0
        or response_received_ms > 2_147_483_647
    ):
        raise InvalidClientTimingReportError(
            "response_received_ms must be a non-negative integer"
        )
    return ClientTimingReport(response_received_ms=response_received_ms)


def record_client_response_timing(
    database_session: Session,
    *,
    spa_id: uuid.UUID,
    client_attempt_id: uuid.UUID,
    report: ClientTimingReport,
) -> PromoAttempt:
    """Resolve the authenticated owner row and retain its first valid marker."""

    repository = PromoAttemptRepository(database_session)
    attempt = repository.get_by_admission_key(
        spa_id=spa_id,
        client_attempt_id=client_attempt_id,
        for_update=True,
    )
    if report.response_received_ms < attempt.request_started_ms:
        raise InvalidClientTimingReportError(
            "response marker precedes request_started_ms"
        )
    try:
        return repository.record_client_response_timing(
            attempt,
            response_received_ms=report.response_received_ms,
        )
    except ValueError as error:
        raise ClientTimingConflictError(str(error)) from error


def project_core_timeline(
    attempt: PromoAttempt, *, now: datetime | None = None
) -> CoreTimelineProjection:
    """Project only promo-owned core truth without fabricating missing stages."""

    timestamp = _utc(now)
    tags: list[str] = []
    if attempt.domain_outcome in {
        "no_proposals",
        "busy",
        "deadline",
        "unacceptable_query",
        "insufficient_results",
        "interrupted",
    }:
        tags.append(attempt.domain_outcome)
    if attempt.processing_status == "internal_failure":
        tags.append("internal_failure")
    if (
        attempt.processing_status in _TERMINAL_PROCESSING_STATUSES
        and attempt.response_received_ms is None
    ):
        tags.append("response_receipt_missing")
    if attempt.display_status == "failed":
        tags.append("display_failed")
    effective_display_status = derive_effective_display_status(
        attempt, now=timestamp
    )
    if effective_display_status == "unconfirmed":
        tags.append("display_unconfirmed")
    if (
        attempt.display_status == "confirmed"
        and attempt.qr_fully_visible_elapsed_ms is not None
        and attempt.qr_fully_visible_elapsed_ms >= 10_000
    ):
        tags.append("latency_over_10s")
    return CoreTimelineProjection(
        reference_series_ready_at=_utc(attempt.reference_series_ready_at),
        reference_series_ready_elapsed_ms=0,
        local_detection_completed_ms=attempt.local_detection_completed_ms,
        request_started_ms=attempt.request_started_ms,
        response_received_ms=attempt.response_received_ms,
        created_at=_utc(attempt.created_at),
        slot_decided_at=_optional_utc(attempt.slot_decided_at),
        search_started_at=_optional_utc(attempt.search_started_at),
        search_finished_at=_optional_utc(attempt.search_finished_at),
        processing_status=attempt.processing_status,
        domain_outcome=attempt.domain_outcome,
        display_status=effective_display_status,
        display_reported_at=_optional_utc(attempt.display_reported_at),
        qr_fully_visible_elapsed_ms=attempt.qr_fully_visible_elapsed_ms,
        issue_tags=tuple(tags),
    )


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidClientTimingReportError("duplicate JSON field")
        result[key] = value
    return result


def _optional_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _utc(value)


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("core timeline timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


__all__ = [
    "ClientTimingConflictError",
    "ClientTimingReport",
    "CoreTimelineProjection",
    "InvalidClientTimingReportError",
    "parse_client_timing_report",
    "project_core_timeline",
    "record_client_response_timing",
]

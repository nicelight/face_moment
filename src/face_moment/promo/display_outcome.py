"""Promo-owned authenticated display acknowledgement state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, cast
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.diagnostics.server_events import ServerEventCode, ServerEventSink
from face_moment.promo.attempt import (
    PromoAttempt,
    PromoAttemptRepository,
    derive_effective_display_status,
)
from face_moment.promo.session import PromoSession

DisplayReportStatus = Literal["confirmed", "failed"]
EffectiveDisplayStatus = Literal["pending", "confirmed", "failed", "unconfirmed"]


class InvalidDisplayReportError(ValueError):
    """The report does not match the exact display acknowledgement contract."""


class PromoDisplaySessionNotFoundError(LookupError):
    """The session is unknown or belongs to another display principal."""


class DisplayReportConflictError(ValueError):
    """The report conflicts with an already terminal or expired display state."""


@dataclass(frozen=True, slots=True)
class DisplayReport:
    """Validated version-1 report sent by the central Promo client."""

    status: DisplayReportStatus
    qr_fully_visible_elapsed_ms: int | None = None


@dataclass(frozen=True, slots=True)
class DisplayOutcome:
    """Stored or effective display state for one immutable result session."""

    session_id: uuid.UUID
    status: EffectiveDisplayStatus
    display_expires_at: datetime
    display_reported_at: datetime | None
    qr_fully_visible_elapsed_ms: int | None


class DisplayOutcomeRepository:
    """Read and transition display state through the Promo Attempt repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def read(
        self,
        *,
        spa_id: uuid.UUID,
        session_id: uuid.UUID,
        now: datetime | None = None,
    ) -> DisplayOutcome:
        """Read stored state, deriving pending expiry as ``unconfirmed``."""

        session_row, attempt = self._load(
            spa_id=spa_id,
            session_id=session_id,
            for_update=False,
        )
        return _outcome(session_row, attempt, now=_utc(now))

    def record(
        self,
        *,
        spa_id: uuid.UUID,
        session_id: uuid.UUID,
        report: DisplayReport,
        now: datetime | None = None,
    ) -> DisplayOutcome:
        """Record the first timely terminal report and return its state."""

        _validate_report(report)
        timestamp = _utc(now)
        session_row, attempt = self._load(
            spa_id=spa_id,
            session_id=session_id,
            for_update=True,
        )
        current = _outcome(session_row, attempt, now=timestamp)
        if current.status in {"confirmed", "failed"}:
            if current.status == report.status:
                return current
            raise DisplayReportConflictError("display status is already terminal")
        if current.status == "unconfirmed":
            raise DisplayReportConflictError("display report arrived after expiry")
        if attempt.display_status != "pending":
            raise DisplayReportConflictError("display status cannot accept a report")

        try:
            PromoAttemptRepository(self._session).record_display_outcome(
                attempt,
                status=report.status,
                qr_fully_visible_elapsed_ms=report.qr_fully_visible_elapsed_ms,
                now=timestamp,
            )
        except ValueError as error:
            raise DisplayReportConflictError(str(error)) from error
        return _outcome(session_row, attempt, now=timestamp)

    def _load(
        self,
        *,
        spa_id: uuid.UUID,
        session_id: uuid.UUID,
        for_update: bool,
    ) -> tuple[PromoSession, PromoAttempt]:
        session_statement = select(PromoSession).where(
            PromoSession.id == session_id,
            PromoSession.spa_id == spa_id,
        )
        if for_update:
            session_statement = session_statement.with_for_update()
        session_row = self._session.scalar(session_statement)
        if session_row is None:
            raise PromoDisplaySessionNotFoundError(str(session_id))

        attempt_statement = select(PromoAttempt).where(
            PromoAttempt.id == session_row.attempt_id,
            PromoAttempt.spa_id == spa_id,
        )
        if for_update:
            attempt_statement = attempt_statement.with_for_update()
        attempt = self._session.scalar(attempt_statement)
        if attempt is None or attempt.display_expires_at is None:
            raise PromoDisplaySessionNotFoundError(str(session_id))
        return session_row, attempt


def parse_display_report(payload: object) -> DisplayReport:
    """Validate the exact JSON object accepted by the display endpoint."""

    if not isinstance(payload, dict):
        raise InvalidDisplayReportError("display report must be an object")
    schema_version = payload.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
    ):
        raise InvalidDisplayReportError("schema_version must be 1")
    report_status = payload.get("status")
    if report_status == "failed":
        if set(payload) != {"schema_version", "status"}:
            raise InvalidDisplayReportError("failed report fields are invalid")
        return DisplayReport(status="failed")
    if report_status != "confirmed":
        raise InvalidDisplayReportError("display status is invalid")
    if set(payload) != {
        "schema_version",
        "status",
        "qr_fully_visible_elapsed_ms",
    }:
        raise InvalidDisplayReportError("confirmed report fields are invalid")
    elapsed = payload.get("qr_fully_visible_elapsed_ms")
    if (
        not isinstance(elapsed, int)
        or isinstance(elapsed, bool)
        or elapsed < 0
        or elapsed > 2_147_483_647
    ):
        raise InvalidDisplayReportError("QR-visible elapsed value is invalid")
    return DisplayReport(
        status="confirmed",
        qr_fully_visible_elapsed_ms=elapsed,
    )


def emit_display_confirmed(
    event_sink: ServerEventSink | None,
    *,
    attempt: PromoAttempt,
    outcome: DisplayOutcome,
) -> None:
    """Record only the committed accepted display outcome best-effort."""

    try:
        if event_sink is not None and outcome.status == "confirmed":
            event_sink.emit(
                ServerEventCode.PROMO_DISPLAY_CONFIRMED,
                attempt_id=attempt.id,
                correlation_id=attempt.client_attempt_id,
            )
    except Exception:
        pass


def _validate_report(report: DisplayReport) -> None:
    if report.status not in {"confirmed", "failed"}:
        raise InvalidDisplayReportError("display status is invalid")
    if report.status == "failed" and report.qr_fully_visible_elapsed_ms is not None:
        raise InvalidDisplayReportError("failed report cannot contain elapsed value")
    if report.status == "confirmed" and (
        not isinstance(report.qr_fully_visible_elapsed_ms, int)
        or isinstance(report.qr_fully_visible_elapsed_ms, bool)
        or report.qr_fully_visible_elapsed_ms < 0
        or report.qr_fully_visible_elapsed_ms > 2_147_483_647
    ):
        raise InvalidDisplayReportError("QR-visible elapsed value is invalid")


def _outcome(
    session_row: PromoSession,
    attempt: PromoAttempt,
    *,
    now: datetime,
) -> DisplayOutcome:
    status = cast(
        EffectiveDisplayStatus,
        derive_effective_display_status(attempt, now=now),
    )
    return DisplayOutcome(
        session_id=session_row.id,
        status=status,
        display_expires_at=_utc(attempt.display_expires_at),
        display_reported_at=(
            None
            if attempt.display_reported_at is None
            else _utc(attempt.display_reported_at)
        ),
        qr_fully_visible_elapsed_ms=(
            attempt.qr_fully_visible_elapsed_ms
            if status == "confirmed"
            else None
        ),
    )


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("display outcome timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


__all__ = [
    "DisplayOutcome",
    "DisplayOutcomeRepository",
    "DisplayReport",
    "DisplayReportConflictError",
    "DisplayReportStatus",
    "EffectiveDisplayStatus",
    "InvalidDisplayReportError",
    "PromoDisplaySessionNotFoundError",
    "parse_display_report",
    "emit_display_confirmed",
]

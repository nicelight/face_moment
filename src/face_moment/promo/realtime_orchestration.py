"""Promo-owned singleton and deadline boundary for realtime processing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import threading
import time
from typing import Generic, Literal, Protocol, TypeVar

from face_moment.processing.realtime_search import RealtimeSearchResult
from face_moment.promo.attempt import PromoAttempt
from face_moment.promo.result_assembly import ResultAssembly, assemble_result
from face_moment.promo.session import ResultSessionResponse

_PROCESS_LOCAL_REALTIME_SLOT = threading.BoundedSemaphore(1)
T = TypeVar("T")
RealtimeOutcome = Literal["processing", "busy", "deadline", "internal_failure"]


class AttemptStateWriter(Protocol):
    """The promo Attempt transitions needed by this owner-local boundary."""

    def mark_busy(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt: ...

    def mark_search_started(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt: ...

    def mark_deadline(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt: ...

    def mark_internal_failure(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt: ...

    def mark_unacceptable_query(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt: ...

    def mark_insufficient_results(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt: ...

    def publish_result(
        self,
        attempt: PromoAttempt,
        assembly: ResultAssembly,
        *,
        qr_ticket_secret: bytes | str,
        display_expires_at: datetime,
        qr_issued_at: datetime | None = None,
    ) -> ResultSessionResponse: ...


@dataclass(frozen=True, slots=True)
class RealtimeProcessingOutcome(Generic[T]):
    """Typed processing handoff; assembly and publication remain outside."""

    outcome: RealtimeOutcome
    value: T | None = None


class RealtimeOrchestrator:
    """Run one admitted processing call without a waiter lifecycle."""

    def __init__(
        self,
        repository: AttemptStateWriter,
        *,
        slot: threading.Semaphore | None = None,
        clock: Callable[[], float] = time.monotonic,
        utc_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._repository = repository
        self._slot = slot if slot is not None else _PROCESS_LOCAL_REALTIME_SLOT
        self._clock = clock
        self._utc_now = utc_now

    def run(
        self,
        attempt: PromoAttempt,
        process: Callable[[], T],
        *,
        admitted_at: float | None = None,
    ) -> RealtimeProcessingOutcome[T]:
        """Try one non-blocking acquisition and one deadline-bounded call.

        A native call cannot be force-killed safely. If it returns after the
        copied deadline, its value is discarded and the Attempt becomes
        ``deadline``. The caller owns any timely result assembly/publication.
        """

        deadline_ms = attempt.deadline_ms
        if (
            isinstance(deadline_ms, bool)
            or not isinstance(deadline_ms, int)
            or deadline_ms <= 0
        ):
            raise ValueError("Attempt deadline_ms must be positive")
        admission_clock = self._clock() if admitted_at is None else admitted_at
        deadline_at = admission_clock + deadline_ms / 1000.0

        if self._clock() >= deadline_at:
            self._repository.mark_deadline(attempt, now=self._utc_now())
            return RealtimeProcessingOutcome(outcome="deadline")
        if not self._slot.acquire(blocking=False):
            self._repository.mark_busy(attempt, now=self._utc_now())
            return RealtimeProcessingOutcome(outcome="busy")

        try:
            if self._clock() >= deadline_at:
                self._repository.mark_deadline(attempt, now=self._utc_now())
                return RealtimeProcessingOutcome(outcome="deadline")
            self._repository.mark_search_started(attempt, now=self._utc_now())
            if self._clock() >= deadline_at:
                self._repository.mark_deadline(attempt, now=self._utc_now())
                return RealtimeProcessingOutcome(outcome="deadline")

            try:
                value = process()
            except Exception:
                self._repository.mark_internal_failure(
                    attempt, now=self._utc_now()
                )
                return RealtimeProcessingOutcome(outcome="internal_failure")

            if self._clock() >= deadline_at:
                self._repository.mark_deadline(attempt, now=self._utc_now())
                return RealtimeProcessingOutcome(outcome="deadline")
            return RealtimeProcessingOutcome(outcome="processing", value=value)
        finally:
            self._slot.release()


RealtimeAttemptOutcome = Literal[
    "result",
    "busy",
    "deadline",
    "no_proposals",
    "unacceptable_query",
    "insufficient_results",
    "interrupted",
    "internal_failure",
]


@dataclass(frozen=True, slots=True)
class RealtimeAttemptExecution:
    """Promo-owned terminal handoff for one admitted realtime Attempt."""

    outcome: RealtimeAttemptOutcome
    session: ResultSessionResponse | None = None
    search_result: RealtimeSearchResult | None = None
    assembly: ResultAssembly | None = None


def execute_realtime_attempt(
    *,
    repository: AttemptStateWriter,
    attempt: PromoAttempt,
    search: Callable[[], RealtimeSearchResult],
    qr_ticket_secret: bytes | str,
    result_display_ms: int,
    slot: threading.Semaphore | None = None,
    clock: Callable[[], float] = time.monotonic,
    utc_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> RealtimeAttemptExecution:
    """Compose processing search, Promo assembly and session publication.

    The caller supplies only the already-bound processing application call.
    Attempt transitions, singleton/deadline and result/session ownership remain
    in the Promo boundary.
    """

    if (
        isinstance(result_display_ms, bool)
        or not isinstance(result_display_ms, int)
        or result_display_ms <= 0
    ):
        raise ValueError("result_display_ms must be positive")

    processing = RealtimeOrchestrator(
        repository,
        slot=slot,
        clock=clock,
        utc_now=utc_now,
    ).run(attempt, search)
    if processing.outcome != "processing":
        return RealtimeAttemptExecution(outcome=processing.outcome)
    if processing.value is None:
        repository.mark_internal_failure(attempt, now=utc_now())
        return RealtimeAttemptExecution(outcome="internal_failure")

    search_result = processing.value
    if _is_unacceptable_query(search_result):
        repository.mark_unacceptable_query(attempt, now=utc_now())
        return RealtimeAttemptExecution(
            outcome="unacceptable_query", search_result=search_result
        )

    assembly = assemble_result(search_result)
    if assembly.outcome != "result":
        repository.mark_insufficient_results(attempt, now=utc_now())
        return RealtimeAttemptExecution(
            outcome="insufficient_results", search_result=search_result
        )

    issued_at = _utc(utc_now())
    try:
        session = repository.publish_result(
            attempt,
            assembly,
            qr_ticket_secret=qr_ticket_secret,
            qr_issued_at=issued_at,
            display_expires_at=issued_at
            + timedelta(milliseconds=result_display_ms),
        )
    except Exception:
        repository.mark_internal_failure(attempt, now=utc_now())
        return RealtimeAttemptExecution(
            outcome="internal_failure", search_result=search_result, assembly=assembly
        )
    return RealtimeAttemptExecution(
        outcome="result",
        session=session,
        search_result=search_result,
        assembly=assembly,
    )


def _is_unacceptable_query(search_result: RealtimeSearchResult) -> bool:
    detections = search_result.detections
    return bool(detections) and all(
        detection.rejection_reason == "unacceptable_query"
        for detection in detections
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("realtime timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)

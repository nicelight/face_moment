"""Promo-owned singleton and deadline boundary for realtime processing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import time
from typing import Generic, Literal, Protocol, TypeVar

from face_moment.promo.attempt import PromoAttempt

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

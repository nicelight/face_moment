"""Fixed producer-matrix proof for FT-009 structured server events."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import uuid

import pytest

from face_moment.diagnostics.server_events import ServerEventCode
from face_moment.promo.display_outcome import emit_display_confirmed
from face_moment.promo.qr_continuation import PhoneContinuationService
from face_moment.promo.realtime_orchestration import (
    emit_attempt_admitted,
    emit_attempt_terminal,
    emit_runtime_readiness_closed,
)
from face_moment.promo.session import PromoBrowserAccessExpiredError


class _RecordingSink:
    def __init__(self, *, accepted: bool = True) -> None:
        self.accepted = accepted
        self.events: list[tuple[ServerEventCode, uuid.UUID | None, uuid.UUID | None]] = []

    def emit(
        self,
        event_code: ServerEventCode,
        *,
        attempt_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> bool:
        self.events.append((event_code, attempt_id, correlation_id))
        return self.accepted


def test_every_catalog_code_has_one_typed_producer_seam_without_free_form_context() -> None:
    sink = _RecordingSink()
    attempt = SimpleNamespace(
        id=uuid.uuid4(),
        client_attempt_id=uuid.uuid4(),
        processing_status="accepted",
    )
    emit_runtime_readiness_closed(sink)
    emit_attempt_admitted(
        sink,
        attempt_id=attempt.id,
        correlation_id=attempt.client_attempt_id,
    )
    attempt.processing_status = "internal_failure"
    emit_attempt_terminal(
        sink,
        attempt_id=attempt.id,
        correlation_id=attempt.client_attempt_id,
        processing_status=attempt.processing_status,
    )
    attempt.processing_status = "result_issued"
    emit_attempt_terminal(
        sink,
        attempt_id=attempt.id,
        correlation_id=attempt.client_attempt_id,
        processing_status=attempt.processing_status,
    )
    emit_display_confirmed(
        sink,
        attempt=attempt,
        outcome=SimpleNamespace(status="confirmed"),
    )

    service = PhoneContinuationService.__new__(PhoneContinuationService)
    service._event_sink = sink
    service._database_session = _AttemptLookup(attempt)
    service.emit_opened(attempt_id=attempt.id, first_open=True)
    service._emit_expired()

    assert {event[0] for event in sink.events} == set(ServerEventCode)
    assert sink.events[0] == (
        ServerEventCode.RUNTIME_READINESS_CLOSED,
        None,
        None,
    )
    assert all(
        event[1:] == (attempt.id, attempt.client_attempt_id)
        for event in sink.events[1:-1]
    )
    assert sink.events[-1] == (ServerEventCode.QR_SESSION_EXPIRED, None, None)


def test_unavailable_sink_result_changes_no_owner_state_or_producer_outcome() -> None:
    sink = _RecordingSink(accepted=False)
    attempt = SimpleNamespace(
        id=uuid.uuid4(),
        client_attempt_id=uuid.uuid4(),
        processing_status="result_issued",
        domain_outcome="result",
        display_status="confirmed",
    )
    before = vars(attempt).copy()
    emit_attempt_admitted(
        sink,
        attempt_id=attempt.id,
        correlation_id=attempt.client_attempt_id,
    )
    emit_attempt_terminal(
        sink,
        attempt_id=attempt.id,
        correlation_id=attempt.client_attempt_id,
        processing_status=attempt.processing_status,
    )
    emit_display_confirmed(
        sink,
        attempt=attempt,
        outcome=SimpleNamespace(status="confirmed"),
    )
    assert vars(attempt) == before

    raising_sink = _RaisingSink()
    emit_attempt_admitted(
        raising_sink,
        attempt_id=attempt.id,
        correlation_id=attempt.client_attempt_id,
    )
    emit_attempt_terminal(
        raising_sink,
        attempt_id=attempt.id,
        correlation_id=attempt.client_attempt_id,
        processing_status=attempt.processing_status,
    )
    emit_display_confirmed(
        raising_sink,
        attempt=attempt,
        outcome=SimpleNamespace(status="confirmed"),
    )
    assert vars(attempt) == before


def test_expired_qr_logging_preserves_the_existing_expired_outcome() -> None:
    sink = _RecordingSink(accepted=False)
    service = PhoneContinuationService.__new__(PhoneContinuationService)
    service._event_sink = sink
    service._database_session = object()
    service._sessions = _ExpiredSessions()

    with pytest.raises(PromoBrowserAccessExpiredError):
        service.validate_access("B" * 43, now=datetime.now(timezone.utc))
    assert sink.events == [
        (
            ServerEventCode.QR_SESSION_EXPIRED,
            None,
            None,
        )
    ]


def test_qr_first_open_uses_one_explicit_owner_lookup_and_ignores_lookup_failure() -> None:
    sink = _RecordingSink()
    attempt = SimpleNamespace(id=uuid.uuid4(), client_attempt_id=uuid.uuid4())
    lookup = _AttemptLookup(attempt)

    opened = PhoneContinuationService.__new__(PhoneContinuationService)
    opened._event_sink = sink
    opened._database_session = lookup
    opened.emit_opened(attempt_id=attempt.id, first_open=True)
    opened.emit_opened(attempt_id=attempt.id, first_open=False)
    assert lookup.calls == 1
    assert sink.events == [
        (
            ServerEventCode.QR_SESSION_OPENED,
            attempt.id,
            attempt.client_attempt_id,
        )
    ]

    opened._database_session = _RaisingLookup()
    opened.emit_opened(attempt_id=attempt.id, first_open=True)
    assert len(sink.events) == 1


class _AttemptLookup:
    def __init__(self, attempt: object) -> None:
        self.attempt = attempt
        self.calls = 0

    def get(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        self.calls += 1
        return self.attempt


class _RaisingLookup:
    def get(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("synthetic owner lookup failure")


class _ExpiredSessions:
    def read_browser_access(self, ticket: str, *, now: datetime | None = None) -> object:
        del ticket, now
        raise PromoBrowserAccessExpiredError("synthetic expired session")


class _RaisingSink:
    def emit(self, event_code: ServerEventCode, **kwargs: object) -> bool:
        del event_code, kwargs
        raise RuntimeError("synthetic sink exception")

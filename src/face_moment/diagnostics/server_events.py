"""Diagnostics-owned fixed structured server-event collection boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from queue import Empty, Full, Queue
import threading
from types import MappingProxyType
from typing import Literal, Protocol
import uuid

from sqlalchemy import CheckConstraint, DateTime, String, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.infrastructure.database import Base


EVENT_QUEUE_CAPACITY = 256
SERVER_EVENT_SEARCH_LIMIT = 100
Severity = Literal["info", "warning", "error"]
Component = Literal["runtime", "realtime", "promo", "qr"]


class ServerEventCode(str, Enum):
    RUNTIME_READINESS_CLOSED = "runtime.readiness_closed"
    ATTEMPT_ADMITTED = "attempt.admitted"
    ATTEMPT_FAILED = "attempt.failed"
    PROMO_RESULT_ISSUED = "promo.result_issued"
    PROMO_DISPLAY_CONFIRMED = "promo.display_confirmed"
    QR_SESSION_OPENED = "qr.session_opened"
    QR_SESSION_EXPIRED = "qr.session_expired"


@dataclass(frozen=True, slots=True)
class ServerEventDefinition:
    severity: Severity
    component: Component


EVENT_CATALOG: Mapping[ServerEventCode, ServerEventDefinition] = MappingProxyType(
    {
        ServerEventCode.RUNTIME_READINESS_CLOSED: ServerEventDefinition(
            "warning", "runtime"
        ),
        ServerEventCode.ATTEMPT_ADMITTED: ServerEventDefinition("info", "realtime"),
        ServerEventCode.ATTEMPT_FAILED: ServerEventDefinition("error", "realtime"),
        ServerEventCode.PROMO_RESULT_ISSUED: ServerEventDefinition("info", "promo"),
        ServerEventCode.PROMO_DISPLAY_CONFIRMED: ServerEventDefinition("info", "promo"),
        ServerEventCode.QR_SESSION_OPENED: ServerEventDefinition("info", "qr"),
        ServerEventCode.QR_SESSION_EXPIRED: ServerEventDefinition("warning", "qr"),
    }
)


_CATALOG_SHAPE = " OR ".join(
    f"(event_code = '{code.value}' AND severity = '{definition.severity}' "
    f"AND component = '{definition.component}')"
    for code, definition in EVENT_CATALOG.items()
)


class ServerEvent(Base):
    """Exact redacted diagnostics-owned PostgreSQL row."""

    __tablename__ = "server_events"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'warning', 'error')",
            name="ck_server_events_severity",
        ),
        CheckConstraint(
            "component IN ('runtime', 'realtime', 'promo', 'qr')",
            name="ck_server_events_component",
        ),
        CheckConstraint(_CATALOG_SHAPE, name="ck_server_events_catalog_shape"),
        CheckConstraint(
            "char_length(release_id) BETWEEN 1 AND 128",
            name="ck_server_events_release_id_length",
        ),
        CheckConstraint(
            "(event_code = 'runtime.readiness_closed' AND attempt_id IS NULL AND correlation_id IS NULL) OR "
            "(event_code IN ('attempt.admitted', 'attempt.failed', 'promo.result_issued', "
            "'promo.display_confirmed', 'qr.session_opened') AND attempt_id IS NOT NULL "
            "AND correlation_id IS NOT NULL) OR "
            "(event_code = 'qr.session_expired' AND ((attempt_id IS NULL AND correlation_id IS NULL) "
            "OR (attempt_id IS NOT NULL AND correlation_id IS NOT NULL)))",
            name="ck_server_events_correlation_shape",
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(length=7), nullable=False)
    component: Mapped[str] = mapped_column(String(length=8), nullable=False)
    event_code: Mapped[str] = mapped_column(String(length=32), nullable=False)
    release_id: Mapped[str] = mapped_column(String(length=128), nullable=False)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


@dataclass(frozen=True, slots=True)
class ServerEventEnvelope:
    occurred_at: datetime
    event_code: ServerEventCode
    release_id: str
    attempt_id: uuid.UUID | None
    correlation_id: uuid.UUID | None

    @property
    def severity(self) -> Severity:
        return EVENT_CATALOG[self.event_code].severity

    @property
    def component(self) -> Component:
        return EVENT_CATALOG[self.event_code].component


@dataclass(frozen=True, slots=True)
class ServerEventProjection:
    event_id: uuid.UUID
    occurred_at: datetime
    severity: Severity
    component: Component
    event_code: ServerEventCode
    release_id: str
    attempt_id: uuid.UUID | None
    correlation_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class ServerEventSearchFilters:
    occurred_at_from: datetime
    occurred_at_to: datetime
    severity: Severity | None = None
    component: Component | None = None
    event_code: ServerEventCode | None = None
    attempt_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None


class ServerEventSink(Protocol):
    """The only application call available to accepted event producers."""

    def emit(
        self,
        event_code: ServerEventCode,
        *,
        attempt_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> bool: ...


class ServerEventRepository:
    """Only-writer repository for diagnostics-owned event rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, envelope: ServerEventEnvelope) -> ServerEventProjection:
        row = ServerEvent(
            occurred_at=envelope.occurred_at,
            severity=envelope.severity,
            component=envelope.component,
            event_code=envelope.event_code.value,
            release_id=envelope.release_id,
            attempt_id=envelope.attempt_id,
            correlation_id=envelope.correlation_id,
        )
        self._session.add(row)
        self._session.flush()
        return _project(row)

    def get(self, event_id: uuid.UUID) -> ServerEventProjection | None:
        row = self._session.get(ServerEvent, event_id)
        return None if row is None else _project(row)

    def search(
        self, filters: ServerEventSearchFilters
    ) -> tuple[ServerEventProjection, ...]:
        """Return the newest immutable rows inside the fixed external bound."""

        statement = select(ServerEvent).where(
            ServerEvent.occurred_at >= _utc(filters.occurred_at_from),
            ServerEvent.occurred_at < _utc(filters.occurred_at_to),
        )
        if filters.severity is not None:
            statement = statement.where(ServerEvent.severity == filters.severity)
        if filters.component is not None:
            statement = statement.where(ServerEvent.component == filters.component)
        if filters.event_code is not None:
            statement = statement.where(
                ServerEvent.event_code == filters.event_code.value
            )
        if filters.attempt_id is not None:
            statement = statement.where(ServerEvent.attempt_id == filters.attempt_id)
        if filters.correlation_id is not None:
            statement = statement.where(
                ServerEvent.correlation_id == filters.correlation_id
            )
        rows = self._session.scalars(
            statement.order_by(
                ServerEvent.occurred_at.desc(), ServerEvent.event_id.desc()
            ).limit(SERVER_EVENT_SEARCH_LIMIT)
        )
        return tuple(_project(row) for row in rows)


class ServerEventEmitter:
    """Capacity-bounded, non-waiting FIFO with an isolated writer session."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        release_id: str,
        utc_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._session_factory = session_factory
        self._release_id = _validate_release_id(release_id)
        self._utc_now = utc_now
        self._queue: Queue[ServerEventEnvelope] = Queue(maxsize=EVENT_QUEUE_CAPACITY)
        self._stop = threading.Event()
        self._started = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._started.is_set():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._write_loop,
            name="face-moment-server-events",
            daemon=True,
        )
        self._started.set()
        self._thread.start()

    def stop(self) -> None:
        """Stop without promising a drain; queued events may be lost."""

        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=0.2)
        self._started.clear()

    def emit(
        self,
        event_code: ServerEventCode,
        *,
        attempt_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> bool:
        if not self._started.is_set() or self._stop.is_set():
            return False
        try:
            envelope = _envelope(
                event_code,
                release_id=self._release_id,
                occurred_at=self._utc_now(),
                attempt_id=attempt_id,
                correlation_id=correlation_id,
            )
            self._queue.put_nowait(envelope)
        except (Full, TypeError, ValueError):
            return False
        return True

    def _write_loop(self) -> None:
        while not self._stop.is_set():
            try:
                envelope = self._queue.get(timeout=0.05)
            except Empty:
                continue
            try:
                with self._session_factory() as session:
                    ServerEventRepository(session).add(envelope)
                    session.commit()
            except Exception:
                # The isolated Session context rolls back/closes independently.
                pass
            finally:
                self._queue.task_done()


def _envelope(
    event_code: ServerEventCode,
    *,
    release_id: str,
    occurred_at: datetime,
    attempt_id: uuid.UUID | None,
    correlation_id: uuid.UUID | None,
) -> ServerEventEnvelope:
    if not isinstance(event_code, ServerEventCode):
        raise TypeError("event_code must be a fixed ServerEventCode")
    timestamp = _utc(occurred_at)
    _validate_correlation(event_code, attempt_id, correlation_id)
    return ServerEventEnvelope(
        occurred_at=timestamp,
        event_code=event_code,
        release_id=_validate_release_id(release_id),
        attempt_id=attempt_id,
        correlation_id=correlation_id,
    )


def _validate_correlation(
    event_code: ServerEventCode,
    attempt_id: uuid.UUID | None,
    correlation_id: uuid.UUID | None,
) -> None:
    if attempt_id is not None and not isinstance(attempt_id, uuid.UUID):
        raise TypeError("attempt_id must be a UUID")
    if correlation_id is not None and not isinstance(correlation_id, uuid.UUID):
        raise TypeError("correlation_id must be a UUID")
    if event_code is ServerEventCode.RUNTIME_READINESS_CLOSED:
        if attempt_id is not None or correlation_id is not None:
            raise ValueError("readiness events are uncorrelated")
        return
    if event_code is ServerEventCode.QR_SESSION_EXPIRED:
        if (attempt_id is None) != (correlation_id is None):
            raise ValueError("QR expiry identities must be both present or both absent")
        return
    if attempt_id is None or correlation_id is None:
        raise ValueError("this event requires both Attempt identities")


def _validate_release_id(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("release_id must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > 128:
        raise ValueError("release_id must contain 1..128 characters")
    return normalized


def _project(row: ServerEvent) -> ServerEventProjection:
    return ServerEventProjection(
        event_id=row.event_id,
        occurred_at=_utc(row.occurred_at),
        severity=row.severity,  # type: ignore[arg-type]
        component=row.component,  # type: ignore[arg-type]
        event_code=ServerEventCode(row.event_code),
        release_id=row.release_id,
        attempt_id=row.attempt_id,
        correlation_id=row.correlation_id,
    )


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("server-event timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


__all__ = [
    "EVENT_CATALOG",
    "EVENT_QUEUE_CAPACITY",
    "SERVER_EVENT_SEARCH_LIMIT",
    "ServerEvent",
    "ServerEventCode",
    "ServerEventDefinition",
    "ServerEventEmitter",
    "ServerEventEnvelope",
    "ServerEventProjection",
    "ServerEventRepository",
    "ServerEventSearchFilters",
    "ServerEventSink",
]

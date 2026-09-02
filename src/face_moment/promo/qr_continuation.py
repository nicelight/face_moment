"""Promo-owned protected QR continuation application boundary."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hmac
import threading
from typing import Protocol
import uuid

from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from face_moment.diagnostics.server_events import ServerEventCode, ServerEventSink
from face_moment.processing import read_photo_processing_projection
from face_moment.promo.attempt import PromoAttemptRepository
from face_moment.promo.display_media import derive_media_ref
from face_moment.promo.purchase_url import (
    PhoneContinuationConfigurationError,
    validate_phone_purchase_url,
)
from face_moment.promo.session import (
    PromoBrowserAccessExpiredError,
    PromoSession,
    PromoSessionRepository,
)
from face_moment.serving_control.ingest_target import IngestTargetRepository


PHONE_COOKIE_NAME = "fm_promo_access"


class PhoneMediaNotFoundError(LookupError):
    """The requested issued preview is unknown or currently unavailable."""


class PreviewObjectStore(Protocol):
    """Narrow private preview read used by the Promo continuation owner."""

    def read(self, *, key: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class PhoneTeaser:
    photo_id: str
    media_url: str

    def as_response(self) -> dict[str, str]:
        return {"photo_id": self.photo_id, "media_url": self.media_url}


@dataclass(frozen=True, slots=True)
class PhoneSessionView:
    session_id: str
    spa_name: str
    visit_date: str
    teaser: PhoneTeaser | None
    n: int
    purchase_url: str
    idle_expires_at: datetime
    idle_expires_in_ms: int

    def as_response(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "session_id": self.session_id,
            "spa_name": self.spa_name,
            "visit_date": self.visit_date,
            "teaser": None if self.teaser is None else self.teaser.as_response(),
            "n": self.n,
            "purchase_url": self.purchase_url,
            "idle_expires_at": _utc_iso(self.idle_expires_at),
            "idle_expires_in_ms": self.idle_expires_in_ms,
        }


@dataclass(frozen=True, slots=True)
class PhoneActivityView:
    idle_expires_at: datetime
    idle_expires_in_ms: int

    def as_response(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "idle_expires_at": _utc_iso(self.idle_expires_at),
            "idle_expires_in_ms": self.idle_expires_in_ms,
        }


class PhonePublicRateLimiter:
    """One in-process Promo phone budget keyed by the resolved client IP."""

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        if limit <= 0:
            raise ValueError("phone public rate limit must be positive")
        if window_seconds <= 0:
            raise ValueError("phone public rate window must be positive")
        self._limit = limit
        self._window = timedelta(seconds=window_seconds)
        self._attempts: dict[str, deque[datetime]] = {}
        self._lock = threading.Lock()

    def allow(self, *, ip_address: str, now: datetime | None = None) -> bool:
        timestamp = _utc(now)
        cutoff = timestamp - self._window
        with self._lock:
            attempts = self._attempts.setdefault(ip_address, deque())
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self._limit:
                return False
            attempts.append(timestamp)
            return True


class PhoneContinuationService:
    """Promo application boundary for ticket, read, activity and media paths."""

    def __init__(
        self,
        database_session: Session,
        *,
        qr_ticket_secret: bytes | str,
        purchase_url: str,
        object_store: PreviewObjectStore,
        event_sink: ServerEventSink | None = None,
    ) -> None:
        self._database_session = database_session
        self._sessions = PromoSessionRepository(
            database_session,
            qr_ticket_secret=qr_ticket_secret,
        )
        self._qr_ticket_secret = qr_ticket_secret
        self._purchase_url = validate_phone_purchase_url(purchase_url)
        self._object_store = object_store
        self._event_sink = event_sink

    def exchange_ticket(
        self, ticket: str, *, now: datetime | None = None
    ) -> tuple[PromoSession, bool]:
        try:
            return self._sessions.open_browser_access(ticket, now=now)
        except PromoBrowserAccessExpiredError:
            self._emit_expired()
            raise

    def emit_opened(
        self, *, attempt_id: uuid.UUID, first_open: bool
    ) -> None:
        """Resolve correlation after commit and emit the first-open event."""

        try:
            if self._event_sink is None or not first_open:
                return
            attempt = PromoAttemptRepository(self._database_session).get(attempt_id)
            self._event_sink.emit(
                ServerEventCode.QR_SESSION_OPENED,
                attempt_id=attempt_id,
                correlation_id=attempt.client_attempt_id,
            )
        except Exception:
            pass

    def read_session(
        self, ticket: str, *, now: datetime | None = None
    ) -> PhoneSessionView:
        timestamp = _utc(now)
        try:
            session_row = self._sessions.read_browser_access(ticket, now=timestamp)
        except PromoBrowserAccessExpiredError:
            self._emit_expired()
            raise
        idle_expires_at = _idle_expiry(session_row)
        if session_row.visit_date is None:
            raise ValueError("issued phone session has no authoritative visit date")
        spa_name = IngestTargetRepository(
            self._database_session
        ).resolve_ingest_target(session_row.spa_id).name
        teaser = self._first_available_teaser(session_row)
        return PhoneSessionView(
            session_id=str(session_row.id),
            spa_name=spa_name,
            visit_date=session_row.visit_date.isoformat(),
            teaser=teaser,
            n=session_row.n,
            purchase_url=self._purchase_url,
            idle_expires_at=idle_expires_at,
            idle_expires_in_ms=_remaining_ms(idle_expires_at, timestamp),
        )

    def validate_access(
        self, ticket: str, *, now: datetime | None = None
    ) -> PromoSession:
        """Validate the protected HTML shell without assembling personal data."""

        try:
            return self._sessions.read_browser_access(ticket, now=now)
        except PromoBrowserAccessExpiredError:
            self._emit_expired()
            raise

    def record_activity(
        self, ticket: str, *, now: datetime | None = None
    ) -> PhoneActivityView:
        timestamp = _utc(now)
        try:
            session_row = self._sessions.record_browser_activity(ticket, now=timestamp)
        except PromoBrowserAccessExpiredError:
            self._emit_expired()
            raise
        idle_expires_at = _idle_expiry(session_row)
        return PhoneActivityView(
            idle_expires_at=idle_expires_at,
            idle_expires_in_ms=_remaining_ms(idle_expires_at, timestamp),
        )

    def read_media(
        self,
        ticket: str,
        media_ref: str,
        *,
        now: datetime | None = None,
    ) -> bytes:
        try:
            session_row = self._sessions.read_browser_access(ticket, now=now)
        except PromoBrowserAccessExpiredError:
            self._emit_expired()
            raise
        if not media_ref.isascii():
            raise PhoneMediaNotFoundError(media_ref)
        for photo_id in session_row.teaser_photo_ids:
            expected = derive_media_ref(
                session_row.id,
                photo_id,
                qr_ticket_secret=self._qr_ticket_secret,
            )
            if not hmac.compare_digest(expected, media_ref):
                continue
            body = self._read_preview(session_row, photo_id)
            if body is None:
                break
            return body
        raise PhoneMediaNotFoundError(media_ref)

    def _first_available_teaser(self, session_row: PromoSession) -> PhoneTeaser | None:
        for photo_id in session_row.teaser_photo_ids:
            body = self._read_preview(session_row, photo_id)
            if body is None:
                continue
            media_ref = derive_media_ref(
                session_row.id,
                photo_id,
                qr_ticket_secret=self._qr_ticket_secret,
            )
            return PhoneTeaser(
                photo_id=str(photo_id),
                media_url=f"/api/phone/media/{media_ref}",
            )
        return None

    def _read_preview(
        self, session_row: PromoSession, photo_id: uuid.UUID
    ) -> bytes | None:
        projection = read_photo_processing_projection(
            self._database_session,
            photo_id=photo_id,
            spa_id=session_row.spa_id,
        )
        if projection is None or not projection.preview_object_key:
            return None
        try:
            body = self._object_store.read(key=projection.preview_object_key)
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code")
            if error_code in {"NoSuchKey", "404", "NotFound"}:
                return None
            raise
        return body or None

    def _emit_expired(self) -> None:
        try:
            if self._event_sink is None:
                return
            self._event_sink.emit(ServerEventCode.QR_SESSION_EXPIRED)
        except Exception:
            pass


def _idle_expiry(session_row: PromoSession) -> datetime:
    value = session_row.browser_idle_expires_at
    if value is None:
        raise ValueError("phone access has no derived idle expiry")
    return _utc(value)


def _remaining_ms(deadline: datetime, timestamp: datetime) -> int:
    return max(0, int((_utc(deadline) - _utc(timestamp)).total_seconds() * 1000))


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("phone continuation timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _utc_iso(value: datetime) -> str:
    return _utc(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = [
    "PHONE_COOKIE_NAME",
    "PhoneActivityView",
    "PhoneContinuationConfigurationError",
    "PhoneContinuationService",
    "PhoneMediaNotFoundError",
    "PhonePublicRateLimiter",
    "PhoneSessionView",
    "PhoneTeaser",
    "validate_phone_purchase_url",
]

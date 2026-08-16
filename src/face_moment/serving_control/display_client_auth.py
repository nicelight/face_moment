"""Read-only display-client authentication for realtime application boundaries."""

from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.serving_control.display_client_access import (
    DisplayClient,
    hash_display_client_token,
)


class InvalidDisplayClientCredentials(Exception):
    """The request has no valid active display-client credential."""


class DisplayClientRateLimitError(Exception):
    """The display-client token or request IP exceeded its configured limit."""


@dataclass(frozen=True, slots=True)
class DisplayClientPrincipal:
    """The only identity published by display-client authentication."""

    display_client_id: uuid.UUID
    spa_id: uuid.UUID


class DisplayClientRateLimiter:
    """Single-backend deterministic limiter keyed by token digest and IP."""

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        if limit <= 0:
            raise ValueError("display-client rate limit must be positive")
        if window_seconds <= 0:
            raise ValueError("display-client rate window must be positive")
        self._limit = limit
        self._window = timedelta(seconds=window_seconds)
        self._token_attempts: dict[bytes, deque[datetime]] = {}
        self._ip_attempts: dict[str, deque[datetime]] = {}
        self._lock = threading.Lock()

    def allow(
        self,
        *,
        token_digest: bytes | None,
        ip_address: str,
        now: datetime,
    ) -> bool:
        """Reserve one request budget without retaining a plaintext token."""
        current_time = _utc(now)
        cutoff = current_time - self._window
        with self._lock:
            ip_attempts = self._ip_attempts.setdefault(ip_address, deque())
            _discard_before(ip_attempts, cutoff)
            token_attempts = (
                None
                if token_digest is None
                else self._token_attempts.setdefault(token_digest, deque())
            )
            if token_attempts is not None:
                _discard_before(token_attempts, cutoff)
            if len(ip_attempts) >= self._limit or (
                token_attempts is not None and len(token_attempts) >= self._limit
            ):
                return False
            ip_attempts.append(current_time)
            if token_attempts is not None:
                token_attempts.append(current_time)
            return True


def authenticate_display_client(
    database_session: Session,
    *,
    authorization: str | None,
    ip_address: str,
    rate_limiter: DisplayClientRateLimiter,
    now: datetime | None = None,
) -> DisplayClientPrincipal:
    """Authenticate one Bearer candidate against the active owner row.

    The function performs only a `display_clients` read. It deliberately
    returns a principal with no token, digest, name or mutable model state.
    Consumers map the two exceptions to the standard `401` and `429` HTTP
    statuses at their own transport boundary.
    """
    token = _parse_bearer_token(authorization)
    token_digest = None if token is None else hash_display_client_token(token)
    if not rate_limiter.allow(
        token_digest=token_digest,
        ip_address=ip_address,
        now=_utc(now),
    ):
        raise DisplayClientRateLimitError
    if token_digest is None:
        raise InvalidDisplayClientCredentials

    client = database_session.scalar(
        select(DisplayClient).where(
            DisplayClient.token_hash_sha256 == token_digest,
            DisplayClient.active.is_(True),
        )
    )
    if client is None:
        raise InvalidDisplayClientCredentials
    return DisplayClientPrincipal(
        display_client_id=client.id,
        spa_id=client.spa_id,
    )


def _parse_bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, separator, candidate = authorization.partition(" ")
    if (
        not separator
        or scheme.casefold() != "bearer"
        or not candidate
        or candidate != candidate.strip()
        or any(character.isspace() for character in candidate)
    ):
        return None
    try:
        candidate.encode("ascii")
    except UnicodeEncodeError:
        return None
    return candidate


def _discard_before(attempts: deque[datetime], cutoff: datetime) -> None:
    while attempts and attempts[0] <= cutoff:
        attempts.popleft()


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("display-client authentication timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


__all__ = [
    "DisplayClientPrincipal",
    "DisplayClientRateLimitError",
    "DisplayClientRateLimiter",
    "InvalidDisplayClientCredentials",
    "authenticate_display_client",
]

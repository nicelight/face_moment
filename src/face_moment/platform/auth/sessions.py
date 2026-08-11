from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, ForeignKey, LargeBinary, Uuid, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.infrastructure.database import Base
from face_moment.platform.auth.principals import (
    InvalidUsernameError,
    StaffPrincipal,
    StaffUser,
    deactivate_staff_user,
    normalize_username,
    reset_staff_password,
    verify_password,
)

_TOKEN_BYTES = 32


class StaffSession(Base):
    __tablename__ = "staff_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    staff_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("face_moment.staff_users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    token_hash_sha256: Mapped[bytes] = mapped_column(
        LargeBinary(_TOKEN_BYTES), nullable=False, unique=True
    )
    csrf_token_hash_sha256: Mapped[bytes] = mapped_column(
        LargeBinary(_TOKEN_BYTES), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


@dataclass(frozen=True, slots=True)
class BrowserSession:
    session_token: str
    csrf_token: str
    expires_at: datetime


class InvalidCredentialsError(Exception):
    pass


class LoginRateLimitError(Exception):
    pass


class InvalidSessionError(Exception):
    pass


class CsrfValidationError(Exception):
    pass


class LoginRateLimiter:
    """Single-backend deterministic login limiter keyed by normalized name/IP."""

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = timedelta(seconds=window_seconds)
        self._attempts: dict[tuple[str, str], deque[datetime]] = {}
        self._lock = threading.Lock()

    def allow(self, *, username: str, ip_address: str, now: datetime) -> bool:
        key = (username, ip_address)
        cutoff = now - self._window
        with self._lock:
            attempts = self._attempts.setdefault(key, deque())
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self._limit:
                return False
            attempts.append(now)
            return True


def create_browser_session(
    database_session: Session,
    *,
    username: str,
    password: str,
    ip_address: str,
    ttl_seconds: int,
    limiter: LoginRateLimiter,
    now: datetime | None = None,
) -> BrowserSession:
    current_time = _current_time(now)
    try:
        normalized_username = normalize_username(username)
    except InvalidUsernameError as error:
        raise InvalidCredentialsError from error
    if not limiter.allow(
        username=normalized_username, ip_address=ip_address, now=current_time
    ):
        raise LoginRateLimitError

    staff_user = database_session.scalar(
        select(StaffUser)
        .where(StaffUser.username == normalized_username)
        .with_for_update()
    )
    if (
        staff_user is None
        or not staff_user.active
        or not verify_password(staff_user.password_hash, password)
    ):
        raise InvalidCredentialsError

    session_token = _new_token()
    csrf_token = _new_token()
    expires_at = current_time + timedelta(seconds=ttl_seconds)
    database_session.add(
        StaffSession(
            staff_user_id=staff_user.id,
            token_hash_sha256=_token_hash(session_token),
            csrf_token_hash_sha256=_token_hash(csrf_token),
            created_at=current_time,
            expires_at=expires_at,
        )
    )
    database_session.commit()
    return BrowserSession(
        session_token=session_token,
        csrf_token=csrf_token,
        expires_at=expires_at,
    )


def get_current_principal(
    database_session: Session,
    *,
    session_token: str | None,
    now: datetime | None = None,
) -> StaffPrincipal:
    _, staff_user = _active_session(
        database_session,
        session_token=session_token,
        now=_current_time(now),
    )
    return StaffPrincipal(
        staff_user_id=staff_user.id,
        username=staff_user.username,
        role=staff_user.role,
    )


def authenticate_unsafe_staff_request(
    database_session: Session,
    *,
    session_token: str | None,
    csrf_cookie_token: str | None,
    csrf_header_token: str | None,
    now: datetime | None = None,
) -> StaffPrincipal:
    """Authenticate an unsafe browser request without acquiring domain authorization."""
    staff_session, staff_user = _active_session(
        database_session,
        session_token=session_token,
        now=_current_time(now),
    )
    _validate_csrf(
        staff_session,
        csrf_cookie_token=csrf_cookie_token,
        csrf_header_token=csrf_header_token,
    )
    return StaffPrincipal(
        staff_user_id=staff_user.id,
        username=staff_user.username,
        role=staff_user.role,
    )


def reset_staff_password_and_revoke_sessions(
    database_session: Session,
    *,
    username: str,
    password: str,
    now: datetime | None = None,
) -> StaffPrincipal:
    current_time = _current_time(now)
    principal = reset_staff_password(
        database_session,
        username=username,
        password=password,
        now=current_time,
    )
    _revoke_all_staff_sessions(
        database_session, staff_user_id=principal.staff_user_id, now=current_time
    )
    database_session.commit()
    return principal


def deactivate_staff_user_and_revoke_sessions(
    database_session: Session,
    *,
    username: str,
    now: datetime | None = None,
) -> StaffPrincipal:
    current_time = _current_time(now)
    principal = deactivate_staff_user(
        database_session,
        username=username,
        now=current_time,
    )
    _revoke_all_staff_sessions(
        database_session, staff_user_id=principal.staff_user_id, now=current_time
    )
    database_session.commit()
    return principal


def revoke_current_browser_session(
    database_session: Session,
    *,
    session_token: str | None,
    csrf_cookie_token: str | None,
    csrf_header_token: str | None,
    now: datetime | None = None,
) -> None:
    current_time = _current_time(now)
    staff_session, _ = _active_session(
        database_session, session_token=session_token, now=current_time
    )
    _validate_csrf(
        staff_session,
        csrf_cookie_token=csrf_cookie_token,
        csrf_header_token=csrf_header_token,
    )
    staff_session.revoked_at = current_time
    database_session.commit()


def _revoke_all_staff_sessions(
    database_session: Session, *, staff_user_id: uuid.UUID, now: datetime
) -> None:
    database_session.execute(
        update(StaffSession)
        .where(
            StaffSession.staff_user_id == staff_user_id,
            StaffSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )


def _active_session(
    database_session: Session,
    *,
    session_token: str | None,
    now: datetime,
) -> tuple[StaffSession, StaffUser]:
    if not session_token:
        raise InvalidSessionError
    result = database_session.execute(
        select(StaffSession, StaffUser)
        .join(StaffUser, StaffSession.staff_user_id == StaffUser.id)
        .where(
            StaffSession.token_hash_sha256 == _token_hash(session_token),
            StaffSession.revoked_at.is_(None),
            StaffSession.expires_at > now,
            StaffUser.active.is_(True),
        )
    ).one_or_none()
    if result is None:
        raise InvalidSessionError
    return result[0], result[1]


def _validate_csrf(
    staff_session: StaffSession,
    *,
    csrf_cookie_token: str | None,
    csrf_header_token: str | None,
) -> None:
    if (
        csrf_cookie_token is None
        or csrf_header_token is None
        or not hmac.compare_digest(csrf_cookie_token, csrf_header_token)
        or not hmac.compare_digest(
            _token_hash(csrf_cookie_token), staff_session.csrf_token_hash_sha256
        )
    ):
        raise CsrfValidationError


def _new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def _token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def _current_time(now: datetime | None) -> datetime:
    return datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)

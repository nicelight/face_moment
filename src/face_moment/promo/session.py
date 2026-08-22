"""Promo-owned immutable result-session publication."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import base64
import hashlib
import hmac
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    Uuid,
    UniqueConstraint,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import func

from face_moment.infrastructure.database import Base
from face_moment.promo.attempt import PromoAttempt
from face_moment.promo.result_assembly import ResultAssembly

FIRST_OPEN_TTL = timedelta(minutes=30)
_TICKET_BYTES = 32
FailureHook = Callable[[str], None]


class PromoSession(Base):
    """Immutable participant result truth owned by ``promo``."""

    __tablename__ = "promo_sessions"
    __table_args__ = (
        CheckConstraint(
            "n >= 4",
            name="ck_promo_sessions_n_minimum",
        ),
        CheckConstraint(
            "octet_length(qr_ticket_hash_sha256) = 32",
            name="ck_promo_sessions_qr_ticket_hash_sha256_length",
        ),
        ForeignKeyConstraint(
            ["attempt_id"],
            ["face_moment.promo_attempts.id"],
            name="fk_promo_sessions_attempt_id_promo_attempts",
            ondelete="CASCADE",
        ),
        UniqueConstraint("attempt_id", name="uq_promo_sessions_attempt_id"),
        UniqueConstraint(
            "qr_ticket_hash_sha256",
            name="uq_promo_sessions_qr_ticket_hash_sha256",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    spa_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    visit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    session_result_photo_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid(as_uuid=True)), nullable=False
    )
    teaser_photo_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid(as_uuid=True)), nullable=False
    )
    n: Mapped[int] = mapped_column(Integer, nullable=False)
    qr_ticket_hash_sha256: Mapped[bytes] = mapped_column(
        LargeBinary(length=_TICKET_BYTES), nullable=False
    )
    qr_issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    qr_first_open_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


@dataclass(frozen=True, slots=True)
class ResultSessionResponse:
    """Domain handoff for the later transport serializer.

    ``teasers`` contains the ordered Photo IDs. Media URL projection and HTTP
    JSON serialization remain outside this publication boundary.
    """

    session_id: uuid.UUID
    teasers: tuple[uuid.UUID, ...]
    n: int
    qr_url: str
    qr_first_open_expires_at: datetime

    @property
    def teaser_photo_ids(self) -> tuple[uuid.UUID, ...]:
        return self.teasers


class PromoSessionNotFoundError(LookupError):
    pass


class PromoSessionRepository:
    """Only-writer/read-back boundary for promo result sessions."""

    def __init__(
        self,
        session: Session,
        *,
        qr_ticket_secret: bytes | str,
        failure_hook: FailureHook | None = None,
    ) -> None:
        self._session = session
        self._qr_ticket_secret = _secret_bytes(qr_ticket_secret)
        self._failure_hook = failure_hook

    def publish_result(
        self,
        attempt: PromoAttempt,
        assembly: ResultAssembly,
        *,
        display_expires_at: datetime,
        qr_issued_at: datetime | None = None,
    ) -> ResultSessionResponse:
        """Publish one result/session pair in the caller's transaction.

        The nested transaction gives this method an atomic savepoint while the
        caller retains commit ownership. A terminal repeat is reconstructed
        from the persisted session and never creates a new ticket or row.
        """

        if attempt.processing_status == "result_issued":
            return self.response_for_attempt(attempt.id)
        if attempt.processing_status != "searching":
            raise ValueError("only a searching Attempt can publish a result")
        _validate_assembly(attempt, assembly)
        issued_at = _utc(qr_issued_at)
        expires_at = _utc(display_expires_at)
        if expires_at <= issued_at:
            raise ValueError("display_expires_at must be after qr_issued_at")
        first_open_expires_at = issued_at + FIRST_OPEN_TTL
        session_id = uuid.uuid4()
        ticket = derive_qr_ticket(
            session_id, issued_at, qr_ticket_secret=self._qr_ticket_secret
        )
        session_row = PromoSession(
            id=session_id,
            attempt_id=attempt.id,
            spa_id=attempt.spa_id,
            visit_date=attempt.visit_date,
            session_result_photo_ids=list(assembly.session_result_photo_ids),
            teaser_photo_ids=list(assembly.teaser_photo_ids),
            n=assembly.n,
            qr_ticket_hash_sha256=hash_qr_ticket(ticket),
            qr_issued_at=issued_at,
            qr_first_open_expires_at=first_open_expires_at,
        )

        try:
            with self._session.begin_nested():
                self._session.add(session_row)
                self._session.flush()
                self._inject_failure("session_inserted")
                result = self._session.execute(
                    update(PromoAttempt)
                    .where(
                        PromoAttempt.id == attempt.id,
                        PromoAttempt.processing_status == "searching",
                        PromoAttempt.domain_outcome.is_(None),
                    )
                    .values(
                        processing_status="result_issued",
                        domain_outcome="result",
                        display_status="pending",
                        display_expires_at=expires_at,
                        search_finished_at=issued_at,
                        updated_at=issued_at,
                    )
                )
                if result.rowcount != 1:
                    self._session.refresh(attempt)
                    if attempt.processing_status == "result_issued":
                        return self.response_for_attempt(attempt.id)
                    raise ValueError("Attempt changed before result publication")
                self._session.flush()
                self._inject_failure("attempt_transitioned")
        except IntegrityError:
            self._session.refresh(attempt)
            if attempt.processing_status == "result_issued":
                return self.response_for_attempt(attempt.id)
            raise

        return self._response(session_row, ticket)

    def get_for_attempt(self, attempt_id: uuid.UUID) -> PromoSession:
        result = self._session.scalar(
            select(PromoSession).where(PromoSession.attempt_id == attempt_id)
        )
        if result is None:
            raise PromoSessionNotFoundError(str(attempt_id))
        return result

    def response_for_attempt(self, attempt_id: uuid.UUID) -> ResultSessionResponse:
        session_row = self.get_for_attempt(attempt_id)
        ticket = derive_qr_ticket(
            session_row.id,
            session_row.qr_issued_at,
            qr_ticket_secret=self._qr_ticket_secret,
        )
        if not hmac.compare_digest(
            session_row.qr_ticket_hash_sha256, hash_qr_ticket(ticket)
        ):
            raise ValueError("persisted QR ticket digest does not match session")
        return self._response(session_row, ticket)

    def _response(
        self, session_row: PromoSession, ticket: str
    ) -> ResultSessionResponse:
        return ResultSessionResponse(
            session_id=session_row.id,
            teasers=tuple(session_row.teaser_photo_ids),
            n=session_row.n,
            qr_url=f"/q?ticket={ticket}",
            qr_first_open_expires_at=_utc(session_row.qr_first_open_expires_at),
        )

    def _inject_failure(self, point: str) -> None:
        if self._failure_hook is not None:
            self._failure_hook(point)


def derive_qr_ticket(
    session_id: uuid.UUID,
    qr_issued_at: datetime,
    *,
    qr_ticket_secret: bytes | str,
) -> str:
    """Derive the URL-safe ticket from persisted identity and issue time."""

    issued_at = _utc(qr_issued_at)
    message = f"{session_id}:{issued_at.isoformat(timespec='microseconds')}".encode(
        "ascii"
    )
    digest = hmac.new(_secret_bytes(qr_ticket_secret), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def hash_qr_ticket(ticket: str) -> bytes:
    if not ticket:
        raise ValueError("QR ticket must be non-empty")
    return hashlib.sha256(ticket.encode("ascii")).digest()


def _validate_assembly(attempt: PromoAttempt, assembly: ResultAssembly) -> None:
    if assembly.outcome != "result":
        raise ValueError("only a successful result assembly can be published")
    union = tuple(assembly.session_result_photo_ids)
    teasers = tuple(assembly.teaser_photo_ids)
    if len(union) != assembly.n or assembly.n < 4:
        raise ValueError("result union cardinality must equal N and be at least four")
    if len(set(union)) != len(union):
        raise ValueError("result union must contain unique Photo IDs")
    if len(teasers) != 4 or len(set(teasers)) != 4:
        raise ValueError("result must contain exactly four unique teasers")
    if not set(teasers).issubset(union):
        raise ValueError("teasers must be members of the complete result union")
    if attempt.visit_date is not None and not isinstance(attempt.visit_date, date):
        raise ValueError("Attempt visit_date is invalid")


def _secret_bytes(value: bytes | str) -> bytes:
    if isinstance(value, str):
        value = value.encode("utf-8")
    if not isinstance(value, bytes) or not value:
        raise ValueError("QR ticket secret must be non-empty")
    return value


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("promo session timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)

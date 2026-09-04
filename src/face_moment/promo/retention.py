from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Uuid,
    delete,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.diagnostics.retention import (
    DiagnosticRetentionProvider,
    DiagnosticRetentionResult,
    RetentionObjectStore,
)
from face_moment.infrastructure.database import Base
from face_moment.promo.attempt import PromoAttempt
from face_moment.promo.session import PromoSession

ORDINARY_RETENTION_DAYS = 90
TECHNICAL_LOG_RETENTION_DAYS = 30
LATEST_SINGLETON_KEY = 1
_ADVISORY_LOCK_KEY = 7_391_042_611_827
_MAX_ERROR_LENGTH = 255


class RetentionCleanupState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class RetentionCleanupLatest(Base):
    """Promo-owned singleton projection of the latest cleanup invocation."""

    __tablename__ = "retention_cleanup_latest"
    __table_args__ = (
        CheckConstraint(
            "singleton_key = 1",
            name="ck_retention_cleanup_latest_singleton_key",
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'interrupted')",
            name="ck_retention_cleanup_latest_status",
        ),
        CheckConstraint(
            "core_attempts_deleted >= 0 AND ordinary_evidence_expired >= 0 "
            "AND technical_logs_deleted >= 0 AND private_artifacts_deleted >= 0 "
            "AND promoted_subsets_preserved >= 0",
            name="ck_retention_cleanup_latest_counts_nonnegative",
        ),
        CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND error IS NULL) OR "
            "(status = 'succeeded' AND finished_at IS NOT NULL AND error IS NULL) OR "
            "(status IN ('failed', 'interrupted') AND finished_at IS NOT NULL "
            "AND error IS NOT NULL)",
            name="ck_retention_cleanup_latest_terminal_shape",
        ),
    )

    singleton_key: Mapped[int] = mapped_column(
        Integer, primary_key=True, default=LATEST_SINGLETON_KEY, server_default="1"
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    technical_logs_before: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempts_and_evidence_before: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    core_attempts_deleted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    ordinary_evidence_expired: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    technical_logs_deleted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    private_artifacts_deleted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    promoted_subsets_preserved: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error: Mapped[str | None] = mapped_column(String(_MAX_ERROR_LENGTH), nullable=True)

    def as_response(self) -> dict[str, object]:
        return {
            "run_id": str(self.run_id),
            "state": self.status,
            "started_at": _utc_iso(self.started_at),
            "finished_at": None if self.finished_at is None else _utc_iso(self.finished_at),
            "cutoffs": {
                "technical_logs_before": _utc_iso(self.technical_logs_before),
                "attempts_and_evidence_before": _utc_iso(
                    self.attempts_and_evidence_before
                ),
            },
            "counts": {
                "core_attempts_deleted": self.core_attempts_deleted,
                "ordinary_evidence_expired": self.ordinary_evidence_expired,
                "technical_logs_deleted": self.technical_logs_deleted,
                "private_artifacts_deleted": self.private_artifacts_deleted,
                "promoted_subsets_preserved": self.promoted_subsets_preserved,
            },
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class RetentionCleanupCounts:
    core_attempts_deleted: int = 0
    ordinary_evidence_expired: int = 0
    technical_logs_deleted: int = 0
    private_artifacts_deleted: int = 0
    promoted_subsets_preserved: int = 0


@dataclass(frozen=True, slots=True)
class RetentionCleanupOutcome:
    exit_code: int
    state: str
    run_id: uuid.UUID | None = None
    counts: RetentionCleanupCounts = RetentionCleanupCounts()
    error: str | None = None

    @property
    def core_attempts_deleted(self) -> int:
        return self.counts.core_attempts_deleted

    @property
    def ordinary_evidence_expired(self) -> int:
        return self.counts.ordinary_evidence_expired

    @property
    def technical_logs_deleted(self) -> int:
        return self.counts.technical_logs_deleted

    @property
    def private_artifacts_deleted(self) -> int:
        return self.counts.private_artifacts_deleted

    @property
    def promoted_subsets_preserved(self) -> int:
        return self.counts.promoted_subsets_preserved


class PromoRetentionService:
    """Owner-ordered retention command service."""

    def __init__(
        self,
        session: Session,
        *,
        diagnostics: DiagnosticRetentionProvider | None = None,
        object_store: RetentionObjectStore | None = None,
    ) -> None:
        self._session = session
        self._diagnostics = diagnostics
        self._object_store = object_store

    def run(self, *, now: datetime | None = None) -> RetentionCleanupOutcome:
        return run_retention_cleanup(
            self._session,
            now=now,
            diagnostics=self._diagnostics,
            object_store=self._object_store,
        )


def run_retention_cleanup(
    session: Session,
    *,
    now: datetime | None = None,
    diagnostics: DiagnosticRetentionProvider | None = None,
    object_store: RetentionObjectStore | None = None,
) -> RetentionCleanupOutcome:
    """Run one non-blocking, owner-ordered cleanup invocation."""

    timestamp = _utc(now)
    lock_connection, owns_lock_connection = _open_lock_connection(session)
    lock_acquired = False
    try:
        lock_acquired = _try_advisory_lock(lock_connection)
        if not lock_acquired:
            lock_connection.rollback()
            session.rollback()
            return RetentionCleanupOutcome(exit_code=2, state="overlap")

        cutoff = timestamp - timedelta(days=ORDINARY_RETENTION_DAYS)
        technical_cutoff = timestamp - timedelta(days=TECHNICAL_LOG_RETENTION_DAYS)
        run_id = uuid.uuid4()
        _mark_orphaned_run(session, timestamp)
        _start_run(
            session,
            run_id=run_id,
            started_at=timestamp,
            technical_cutoff=technical_cutoff,
            attempts_cutoff=cutoff,
        )
        try:
            diagnostic_provider = diagnostics or DiagnosticRetentionProvider(session)
            technical_logs_deleted = diagnostic_provider.expire_server_events(
                cutoff=technical_cutoff
            )
            attempt_ids = tuple(
                session.scalars(
                    select(PromoAttempt.id).where(PromoAttempt.created_at < cutoff)
                ).all()
            )
            diagnostic_result = diagnostic_provider.expire(
                attempt_ids,
                cutoff=cutoff,
                now=timestamp,
                object_store=object_store,
            )
            deleted = _delete_confirmed_promo_state(
                session, diagnostic_result.eligible_attempt_ids
            )
            session.commit()
            counts = RetentionCleanupCounts(
                core_attempts_deleted=deleted,
                ordinary_evidence_expired=(
                    diagnostic_result.ordinary_evidence_expired
                ),
                technical_logs_deleted=technical_logs_deleted,
                private_artifacts_deleted=diagnostic_result.private_artifacts_deleted,
                promoted_subsets_preserved=(
                    diagnostic_result.promoted_subsets_preserved
                ),
            )
            _finish_run(
                session,
                status=RetentionCleanupState.SUCCEEDED.value,
                finished_at=timestamp,
                counts=counts,
                error=None,
            )
            return RetentionCleanupOutcome(
                exit_code=0,
                state=RetentionCleanupState.SUCCEEDED.value,
                run_id=run_id,
                counts=counts,
            )
        except Exception as error:
            session.rollback()
            safe_error = _safe_error(error)
            _finish_run(
                session,
                status=RetentionCleanupState.FAILED.value,
                finished_at=timestamp,
                counts=RetentionCleanupCounts(),
                error=safe_error,
            )
            return RetentionCleanupOutcome(
                exit_code=1,
                state=RetentionCleanupState.FAILED.value,
                run_id=run_id,
                error=safe_error,
            )
    finally:
        if lock_acquired:
            try:
                lock_connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": _ADVISORY_LOCK_KEY},
                )
            except SQLAlchemyError:
                pass
        lock_connection.rollback()
        if owns_lock_connection:
            lock_connection.close()


def read_latest_retention_result(session: Session) -> dict[str, object]:
    latest = session.get(RetentionCleanupLatest, LATEST_SINGLETON_KEY)
    if latest is None:
        return {"schema_version": 1, "status": "never_run", "result": None}
    return {
        "schema_version": 1,
        "status": "available",
        "result": latest.as_response(),
    }


def _open_lock_connection(session: Session) -> tuple[Connection, bool]:
    bind = session.get_bind()
    if isinstance(bind, Engine):
        return bind.connect(), True
    return bind, False


def _try_advisory_lock(connection: Connection) -> bool:
    value = connection.scalar(
        text("SELECT pg_try_advisory_lock(:lock_key)"),
        {"lock_key": _ADVISORY_LOCK_KEY},
    )
    return bool(value)


def _mark_orphaned_run(session: Session, timestamp: datetime) -> None:
    latest = session.get(RetentionCleanupLatest, LATEST_SINGLETON_KEY, with_for_update=True)
    if latest is not None and latest.status == RetentionCleanupState.RUNNING.value:
        latest.status = RetentionCleanupState.INTERRUPTED.value
        latest.finished_at = timestamp
        latest.error = "previous cleanup interrupted"
        session.commit()


def _start_run(
    session: Session,
    *,
    run_id: uuid.UUID,
    started_at: datetime,
    technical_cutoff: datetime,
    attempts_cutoff: datetime,
) -> None:
    latest = session.get(RetentionCleanupLatest, LATEST_SINGLETON_KEY, with_for_update=True)
    if latest is None:
        latest = RetentionCleanupLatest(singleton_key=LATEST_SINGLETON_KEY)
        session.add(latest)
    latest.run_id = run_id
    latest.status = RetentionCleanupState.RUNNING.value
    latest.started_at = started_at
    latest.finished_at = None
    latest.technical_logs_before = technical_cutoff
    latest.attempts_and_evidence_before = attempts_cutoff
    latest.core_attempts_deleted = 0
    latest.ordinary_evidence_expired = 0
    latest.technical_logs_deleted = 0
    latest.private_artifacts_deleted = 0
    latest.promoted_subsets_preserved = 0
    latest.error = None
    session.commit()


def _delete_confirmed_promo_state(
    session: Session,
    attempt_ids: tuple[uuid.UUID, ...],
) -> int:
    if not attempt_ids:
        return 0
    session.execute(delete(PromoSession).where(PromoSession.attempt_id.in_(attempt_ids)))
    deleted = session.execute(
        delete(PromoAttempt).where(PromoAttempt.id.in_(attempt_ids))
    )
    return int(deleted.rowcount or 0)


def _finish_run(
    session: Session,
    *,
    status: str,
    finished_at: datetime,
    counts: RetentionCleanupCounts,
    error: str | None,
) -> None:
    latest = session.get(RetentionCleanupLatest, LATEST_SINGLETON_KEY, with_for_update=True)
    if latest is None:
        raise RuntimeError("retention result row is missing")
    latest.status = status
    latest.finished_at = finished_at
    latest.core_attempts_deleted = counts.core_attempts_deleted
    latest.ordinary_evidence_expired = counts.ordinary_evidence_expired
    latest.technical_logs_deleted = counts.technical_logs_deleted
    latest.private_artifacts_deleted = counts.private_artifacts_deleted
    latest.promoted_subsets_preserved = counts.promoted_subsets_preserved
    latest.error = error
    session.commit()


def _safe_error(error: Exception) -> str:
    if isinstance(error, SQLAlchemyError):
        return "database operation failed"
    return "owner cleanup failed"


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("retention timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _utc_iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


__all__ = [
    "ORDINARY_RETENTION_DAYS",
    "TECHNICAL_LOG_RETENTION_DAYS",
    "PromoRetentionService",
    "RetentionCleanupCounts",
    "RetentionCleanupLatest",
    "RetentionCleanupOutcome",
    "RetentionCleanupState",
    "read_latest_retention_result",
    "run_retention_cleanup",
]

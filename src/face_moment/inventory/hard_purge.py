"""Inventory-owned restore exclusion and resumable fixed-snapshot deletion.

@docs .memory-bank/domains/photo-inventory.md#purge-orchestration
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Uuid, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.infrastructure.database import Base
from face_moment.inventory.photo_persistence import Photo
from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import (
    authenticate_unsafe_staff_request,
    get_current_principal,
)
from face_moment.processing.purge_cleanup import ProcessingPurgeCleanup, PrivateDerivativeDeletion
from face_moment.processing.worker_claims import (
    begin_hard_purge,
    finish_hard_purge,
    read_worker_operation,
)

_WAITING_NAMES = {
    "photo_processing": "Обработка фото",
    "calibration": "Калибровка",
    "retention_cleanup": "Очистка диагностических данных",
}
_logger = logging.getLogger(__name__)


class InventoryPurgeConflictError(RuntimeError):
    """A current immutable snapshot excludes the requested mutation."""


class InventoryPurgeAccessDeniedError(PermissionError):
    """Project-wide inventory operations require an operator or developer."""


class InventoryHardPurgeRun(Base):
    __tablename__ = "inventory_hard_purge_run"
    __table_args__ = (
        CheckConstraint("singleton_id = 1", name="ck_inventory_purge_singleton"),
        CheckConstraint("state IN ('confirmed_waiting', 'running', 'completed')", name="ck_inventory_purge_state"),
        CheckConstraint("completed_count >= 0 AND completed_count <= cardinality(target_photo_ids)", name="ck_inventory_purge_prefix"),
        CheckConstraint(
            "(state = 'confirmed_waiting' AND started_at IS NULL AND completed_at IS NULL "
            "AND completed_count = 0 AND cardinality(target_photo_ids) > 0) OR "
            "(state = 'running' AND started_at IS NOT NULL AND completed_at IS NULL "
            "AND completed_count < cardinality(target_photo_ids)) OR "
            "(state = 'completed' AND completed_at IS NOT NULL "
            "AND completed_count = cardinality(target_photo_ids))",
            name="ck_inventory_purge_lifecycle",
        ),
    )

    singleton_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    target_photo_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def lock_inventory_visibility(session: Session) -> None:
    """Serialize confirmations and restores even before the singleton exists."""
    session.execute(text("SELECT pg_advisory_xact_lock(12012, 1)"))


def current_snapshot(session: Session) -> list[uuid.UUID]:
    run = session.get(InventoryHardPurgeRun, 1)
    return [] if run is None or run.state == "completed" else run.target_photo_ids


class HardPurgeService:
    """Authorize staff operations before taking inventory mutation locks."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def authorize(self, *, session_token: str | None) -> None:
        principal = get_current_principal(self._session, session_token=session_token)
        if principal.role not in {StaffRole.OPERATOR, StaffRole.DEVELOPER}:
            raise InventoryPurgeAccessDeniedError

    def _authorize_mutation(
        self, *, session_token: str | None, csrf_cookie_token: str | None,
        csrf_header_token: str | None,
    ) -> None:
        principal = authenticate_unsafe_staff_request(
            self._session, session_token=session_token,
            csrf_cookie_token=csrf_cookie_token, csrf_header_token=csrf_header_token,
        )
        if principal.role not in {StaffRole.OPERATOR, StaffRole.DEVELOPER}:
            raise InventoryPurgeAccessDeniedError

    def read(self, *, session_token: str | None) -> dict[str, object]:
        self.authorize(session_token=session_token)
        return self._projection(self._session.get(InventoryHardPurgeRun, 1))

    def restore_all(
        self, *, session_token: str | None, csrf_cookie_token: str | None,
        csrf_header_token: str | None,
    ) -> dict[str, object]:
        self._authorize_mutation(session_token=session_token, csrf_cookie_token=csrf_cookie_token, csrf_header_token=csrf_header_token)
        lock_inventory_visibility(self._session)
        snapshot = set(current_snapshot(self._session))
        photos = self._session.scalars(select(Photo).where(Photo.is_active.is_(False)).with_for_update())
        restored = excluded = 0
        for photo in photos:
            if photo.id in snapshot:
                excluded += 1
            else:
                photo.is_active = True
                restored += 1
        self._session.commit()
        return {"schema_version": 1, "restored_count": restored, "excluded_snapshot_count": excluded}

    def confirm(
        self, *, session_token: str | None, csrf_cookie_token: str | None,
        csrf_header_token: str | None,
    ) -> dict[str, object]:
        self._authorize_mutation(session_token=session_token, csrf_cookie_token=csrf_cookie_token, csrf_header_token=csrf_header_token)
        lock_inventory_visibility(self._session)
        run = self._session.scalar(select(InventoryHardPurgeRun).where(InventoryHardPurgeRun.singleton_id == 1).with_for_update())
        if run is not None and run.state != "completed":
            raise InventoryPurgeConflictError
        targets = list(self._session.scalars(select(Photo.id).where(Photo.is_active.is_(False)).order_by(Photo.id)))
        now = datetime.now(UTC)
        if run is None:
            run = InventoryHardPurgeRun(singleton_id=1)
            self._session.add(run)
        run.run_id = uuid.uuid4()
        run.target_photo_ids = targets
        run.completed_count = 0
        run.confirmed_at = now
        run.started_at = None
        run.state = "confirmed_waiting" if targets else "completed"
        run.completed_at = None if targets else now
        self._session.flush()
        projection = self._projection(run)
        self._session.commit()
        return projection

    def _projection(self, run: InventoryHardPurgeRun | None) -> dict[str, object]:
        if run is None:
            return {"schema_version": 1, "run": None}
        waiting_for = _WAITING_NAMES.get(read_worker_operation(self._session)) if run.state == "confirmed_waiting" else None
        return {"schema_version": 1, "run": {
            "run_id": str(run.run_id), "state": run.state,
            "completed": run.completed_count, "total": len(run.target_photo_ids),
            "waiting_for": waiting_for, "confirmed_at": _iso(run.confirmed_at),
            "started_at": _iso(run.started_at), "completed_at": _iso(run.completed_at),
        }}


class InventoryHardPurge:
    """One inventory step, invoked on the existing worker before new claims."""

    def __init__(self, *, session_factory: Callable[[], Session], object_store: PrivateDerivativeDeletion) -> None:
        self._session_factory = session_factory
        self._object_store = object_store

    def process_one(self) -> bool | None:
        """None: no purge; False: wait/retry; True: one target completed.

        Errors keep the durable snapshot/prefix and suppress ordinary claims.
        A process crash is recovered by the existing worker startup path.
        """
        try:
            return self._process_one()
        except Exception as error:
            _logger.warning("Photo purge step waits for retry: %s", type(error).__name__)
            return False

    def _process_one(self) -> bool | None:
        with self._session_factory() as session:
            run = session.scalar(select(InventoryHardPurgeRun).where(InventoryHardPurgeRun.singleton_id == 1).with_for_update())
            if run is None or run.state == "completed":
                return None
            if not begin_hard_purge(session):
                return False
            if run.state == "confirmed_waiting":
                run.state = "running"
                run.started_at = datetime.now(UTC)
            # Commit the visible running state before potentially slow storage IO.
            session.commit()

        with self._session_factory() as session:
            run = session.scalar(select(InventoryHardPurgeRun).where(InventoryHardPurgeRun.singleton_id == 1).with_for_update())
            if run is None or run.state != "running":
                return None
            photo_id = run.target_photo_ids[run.completed_count]
            photo = session.scalar(select(Photo).where(Photo.id == photo_id).with_for_update())
            if photo is None or photo.is_active:
                raise RuntimeError("purge target no longer matches its confirmed snapshot")
            self._object_store.delete(key=photo.original_object_key)
            ProcessingPurgeCleanup(session, self._object_store).cleanup(photo_id=photo_id)
            session.delete(photo)
            run.completed_count += 1
            if run.completed_count == len(run.target_photo_ids):
                run.state = "completed"
                run.completed_at = datetime.now(UTC)
                finish_hard_purge(session)
            session.commit()
            return True


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat().replace("+00:00", "Z")

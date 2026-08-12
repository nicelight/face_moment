from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import func

from face_moment.infrastructure.database import Base

_PENDING_STATUS = "pending"


class PhotoPipelineState(Base):
    """Processing-owned serving state for one Photo and pipeline revision."""

    __tablename__ = "photo_pipeline_states"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'no_faces', 'failed')",
            name="ck_photo_pipeline_states_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_photo_pipeline_states_attempt_count_nonnegative",
        ),
    )

    photo_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("face_moment.photos.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    pipeline_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("face_moment.pipeline_revisions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(
        String(length=16), nullable=False, server_default=_PENDING_STATUS
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    searchable_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    preview_object_key: Mapped[str | None] = mapped_column(String, nullable=True)
    thumbnail_object_key: Mapped[str | None] = mapped_column(String, nullable=True)


class InitialPendingRepository:
    """Processing application boundary for initial serving-pending creation."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_initial_pending(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> PhotoPipelineState:
        state = PhotoPipelineState(
            photo_id=photo_id,
            pipeline_revision_id=pipeline_revision_id,
            status=_PENDING_STATUS,
            attempt_count=0,
        )
        self._session.add(state)
        self._session.flush()
        self._session.refresh(state)
        return state

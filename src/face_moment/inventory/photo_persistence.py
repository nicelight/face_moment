from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import func

from face_moment.infrastructure.database import Base
from face_moment.inventory.validation import CapturedAtSource


class Photo(Base):
    """Inventory-owned Photo identity; admission remains a later boundary."""

    __tablename__ = "photos"
    __table_args__ = (
        CheckConstraint(
            "captured_at_source IN "
            "('exif', 'upload_started_at', 'visit_date_fallback')",
            name="ck_photos_captured_at_source",
        ),
        CheckConstraint(
            "octet_length(checksum_sha256) = 32",
            name="ck_photos_checksum_sha256_length",
        ),
        CheckConstraint(
            "original_byte_size > 0",
            name="ck_photos_original_byte_size_positive",
        ),
        CheckConstraint("width > 0", name="ck_photos_width_positive"),
        CheckConstraint("height > 0", name="ck_photos_height_positive"),
        UniqueConstraint(
            "spa_id",
            "visit_date",
            "checksum_sha256",
            name="uq_photos_spa_id_visit_date_checksum_sha256",
        ),
        UniqueConstraint("original_object_key", name="uq_photos_original_object_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    spa_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("face_moment.spas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    visit_date: Mapped[date] = mapped_column(Date, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    captured_at_source: Mapped[CapturedAtSource] = mapped_column(
        Enum(
            CapturedAtSource,
            name="captured_at_source",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            values_callable=lambda sources: [source.value for source in sources],
        ),
        nullable=False,
    )
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    admission_pipeline_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("face_moment.pipeline_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uploader_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    checksum_sha256: Mapped[bytes] = mapped_column(LargeBinary(length=32), nullable=False)
    original_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class PhotoIdentityRepository:
    """Read-only identity lookup; later admission owns Photo creation."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_identity(
        self,
        *,
        spa_id: uuid.UUID,
        visit_date: date,
        checksum_sha256: bytes,
    ) -> Photo | None:
        return self._session.scalar(
            select(Photo).where(
                Photo.spa_id == spa_id,
                Photo.visit_date == visit_date,
                Photo.checksum_sha256 == checksum_sha256,
            )
        )

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Enum, String, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import func

from face_moment.infrastructure.database import Base


class PipelineCode(StrEnum):
    OPENCV_SFACE = "opencv_sface"
    INSIGHTFACE_BUFFALO_M = "insightface_buffalo_m"


class PipelineRevision(Base):
    __tablename__ = "pipeline_revisions"
    __table_args__ = (
        CheckConstraint(
            "pipeline_code IN ('opencv_sface', 'insightface_buffalo_m')",
            name="ck_pipeline_revisions_pipeline_code",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    pipeline_code: Mapped[PipelineCode] = mapped_column(
        Enum(
            PipelineCode,
            name="pipeline_code",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            values_callable=lambda codes: [code.value for code in codes],
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


@dataclass(frozen=True, slots=True)
class EligiblePipelineRevision:
    id: uuid.UUID
    pipeline_code: PipelineCode
    created_at: datetime
    validated_at: datetime


class UnsupportedPipelineCodeError(ValueError):
    pass


class IneligiblePipelineRevisionError(LookupError):
    pass


class PipelineRevisionRepository:
    """Processing-owned publication and eligibility projection boundary."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def publish_eligible(
        self,
        *,
        pipeline_code: PipelineCode,
        validated_at: datetime | None,
    ) -> EligiblePipelineRevision:
        if not isinstance(pipeline_code, PipelineCode):
            raise UnsupportedPipelineCodeError(str(pipeline_code))
        if validated_at is None:
            raise ValueError("validated_at is required for an eligible revision")

        revision = PipelineRevision(
            pipeline_code=pipeline_code,
            validated_at=validated_at,
        )
        self._session.add(revision)
        self._session.flush()
        self._session.refresh(revision)
        return self._as_eligible(revision)

    def resolve_eligible(
        self, revision_id: uuid.UUID
    ) -> EligiblePipelineRevision:
        revision = self._session.scalar(
            select(PipelineRevision).where(
                PipelineRevision.id == revision_id,
                PipelineRevision.validated_at.is_not(None),
            )
        )
        if revision is None:
            raise IneligiblePipelineRevisionError(str(revision_id))
        return self._as_eligible(revision)

    @staticmethod
    def _as_eligible(revision: PipelineRevision) -> EligiblePipelineRevision:
        if revision.validated_at is None:
            raise IneligiblePipelineRevisionError(str(revision.id))
        return EligiblePipelineRevision(
            id=revision.id,
            pipeline_code=revision.pipeline_code,
            created_at=revision.created_at,
            validated_at=revision.validated_at,
        )

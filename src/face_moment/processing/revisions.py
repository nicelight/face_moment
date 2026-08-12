from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Enum, Integer, String, Uuid, select
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
    detector_id: Mapped[str] = mapped_column(String(length=128), nullable=False)
    detector_version: Mapped[str] = mapped_column(
        String(length=128), nullable=False
    )
    recognizer_id: Mapped[str] = mapped_column(
        String(length=128), nullable=False
    )
    recognizer_version: Mapped[str] = mapped_column(
        String(length=128), nullable=False
    )
    weights_sha256: Mapped[str] = mapped_column(
        String(length=64), nullable=False
    )
    preprocessing_version: Mapped[str] = mapped_column(
        String(length=128), nullable=False
    )
    alignment_version: Mapped[str] = mapped_column(
        String(length=128), nullable=False
    )
    normalization_version: Mapped[str] = mapped_column(
        String(length=128), nullable=False
    )
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
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
    detector_id: str
    detector_version: str
    recognizer_id: str
    recognizer_version: str
    weights_sha256: str
    preprocessing_version: str
    alignment_version: str
    normalization_version: str
    embedding_dimension: int
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
        detector_id: str,
        detector_version: str,
        recognizer_id: str,
        recognizer_version: str,
        weights_sha256: str,
        preprocessing_version: str,
        alignment_version: str,
        normalization_version: str,
        embedding_dimension: int,
    ) -> EligiblePipelineRevision:
        if not isinstance(pipeline_code, PipelineCode):
            raise UnsupportedPipelineCodeError(str(pipeline_code))
        if validated_at is None:
            raise ValueError("validated_at is required for an eligible revision")
        if embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be positive")

        revision = PipelineRevision(
            pipeline_code=pipeline_code,
            validated_at=validated_at,
            detector_id=detector_id,
            detector_version=detector_version,
            recognizer_id=recognizer_id,
            recognizer_version=recognizer_version,
            weights_sha256=weights_sha256,
            preprocessing_version=preprocessing_version,
            alignment_version=alignment_version,
            normalization_version=normalization_version,
            embedding_dimension=embedding_dimension,
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
            detector_id=revision.detector_id,
            detector_version=revision.detector_version,
            recognizer_id=revision.recognizer_id,
            recognizer_version=revision.recognizer_version,
            weights_sha256=revision.weights_sha256,
            preprocessing_version=revision.preprocessing_version,
            alignment_version=revision.alignment_version,
            normalization_version=revision.normalization_version,
            embedding_dimension=revision.embedding_dimension,
            created_at=revision.created_at,
            validated_at=revision.validated_at,
        )

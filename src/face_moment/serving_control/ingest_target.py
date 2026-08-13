from __future__ import annotations

import uuid
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Boolean, ForeignKey, String, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.infrastructure.database import Base
from face_moment.processing.revisions import (
    EligiblePipelineRevision,
    IneligiblePipelineRevisionError,
    PipelineRevisionRepository,
)

_MAX_SPA_NAME_LENGTH = 255
_MAX_TIMEZONE_LENGTH = 255


class Spa(Base):
    __tablename__ = "spas"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(_MAX_SPA_NAME_LENGTH), nullable=False)
    timezone: Mapped[str] = mapped_column(String(_MAX_TIMEZONE_LENGTH), nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    serving_pipeline_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "face_moment.pipeline_revisions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )


@dataclass(frozen=True, slots=True)
class IngestTarget:
    spa_id: uuid.UUID
    name: str
    timezone: str
    pipeline_revision_id: uuid.UUID


class UnknownIngestTargetError(LookupError):
    pass


class InactiveIngestTargetError(LookupError):
    pass


class InvalidIngestTargetTimezoneError(ValueError):
    pass


class IneligibleIngestTargetError(LookupError):
    pass


class IngestTargetRepository:
    """Serving-control owner boundary for pilot SPA target configuration."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def configure_spa(
        self,
        *,
        name: str,
        timezone: str,
        serving_pipeline_revision_id: uuid.UUID,
    ) -> IngestTarget:
        normalized_name = self._normalize_name(name)
        normalized_timezone = self._validate_timezone(timezone)
        revision = self._resolve_eligible_revision(serving_pipeline_revision_id)
        spa = Spa(
            name=normalized_name,
            timezone=normalized_timezone,
            active=True,
            serving_pipeline_revision_id=revision.id,
        )
        self._session.add(spa)
        self._session.flush()
        self._session.refresh(spa)
        return self._as_ingest_target(spa, revision)

    def resolve_ingest_target(self, spa_id: uuid.UUID) -> IngestTarget:
        spa = self._session.get(Spa, spa_id)
        if spa is None:
            raise UnknownIngestTargetError(str(spa_id))
        if not spa.active:
            raise InactiveIngestTargetError(str(spa.id))

        self._validate_timezone(spa.timezone)
        revision = self._resolve_eligible_revision(spa.serving_pipeline_revision_id)
        return self._as_ingest_target(spa, revision)

    def list_active_eligible_ingest_targets(self) -> list[IngestTarget]:
        """Publish only active, valid targets for an authorized consumer read."""
        active_spas = self._session.scalars(
            select(Spa).where(Spa.active.is_(True)).order_by(Spa.name, Spa.id)
        )
        targets: list[IngestTarget] = []
        for spa in active_spas:
            try:
                targets.append(self.resolve_ingest_target(spa.id))
            except (InvalidIngestTargetTimezoneError, IneligibleIngestTargetError):
                continue
        return targets

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("SPA name is required")
        if len(normalized_name) > _MAX_SPA_NAME_LENGTH:
            raise ValueError("SPA name exceeds 255 characters")
        return normalized_name

    @staticmethod
    def _validate_timezone(timezone: str) -> str:
        normalized_timezone = timezone.strip()
        if len(normalized_timezone) > _MAX_TIMEZONE_LENGTH:
            raise InvalidIngestTargetTimezoneError("timezone exceeds 255 characters")
        try:
            ZoneInfo(normalized_timezone)
        except ZoneInfoNotFoundError as error:
            raise InvalidIngestTargetTimezoneError(normalized_timezone) from error
        return normalized_timezone

    def _resolve_eligible_revision(
        self, revision_id: uuid.UUID
    ) -> EligiblePipelineRevision:
        try:
            return PipelineRevisionRepository(self._session).resolve_eligible(revision_id)
        except IneligiblePipelineRevisionError as error:
            raise IneligibleIngestTargetError(str(revision_id)) from error

    @staticmethod
    def _as_ingest_target(
        spa: Spa, revision: EligiblePipelineRevision
    ) -> IngestTarget:
        return IngestTarget(
            spa_id=spa.id,
            name=spa.name,
            timezone=spa.timezone,
            pipeline_revision_id=revision.id,
        )

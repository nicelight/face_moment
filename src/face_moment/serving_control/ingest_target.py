from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Boolean, ForeignKey, String, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.infrastructure.database import Base

if TYPE_CHECKING:
    from face_moment.processing.revisions import EligiblePipelineRevision

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


@dataclass(frozen=True, slots=True)
class ServingRevisionSwitchResult:
    """Audited result of one ordinary serving-revision switch request."""

    spa_id: uuid.UUID
    requested_pipeline_revision_id: uuid.UUID
    committed_pipeline_revision_id: uuid.UUID
    outcome: Literal["committed", "rejected"]
    reason: str


class UnknownIngestTargetError(LookupError):
    pass


class InactiveIngestTargetError(LookupError):
    pass


class InvalidIngestTargetTimezoneError(ValueError):
    pass


class IneligibleIngestTargetError(LookupError):
    pass


class CommittedServingTargetUnavailableError(LookupError):
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
        return self._target_from_spa(self._load_spa(spa_id))

    def lock_ingest_target(self, spa_id: uuid.UUID) -> IngestTarget:
        """Lock and publish the current target for the admission transaction."""
        return self._target_from_spa(
            self._load_spa(spa_id, for_update=True),
        )

    def switch_serving_revision(
        self,
        *,
        spa_id: uuid.UUID,
        target_pipeline_revision_id: uuid.UUID,
    ) -> ServingRevisionSwitchResult:
        """Apply one guarded ordinary A-to-B serving-revision decision."""
        with self._session.begin():
            spa = self._load_spa(spa_id, for_update=True)
            current_pipeline_revision_id = spa.serving_pipeline_revision_id

            try:
                target_revision = self._resolve_eligible_revision(
                    target_pipeline_revision_id
                )
            except IneligibleIngestTargetError:
                return ServingRevisionSwitchResult(
                    spa_id=spa.id,
                    requested_pipeline_revision_id=target_pipeline_revision_id,
                    committed_pipeline_revision_id=current_pipeline_revision_id,
                    outcome="rejected",
                    reason="target_invalid",
                )

            if target_revision.id == current_pipeline_revision_id:
                return ServingRevisionSwitchResult(
                    spa_id=spa.id,
                    requested_pipeline_revision_id=target_pipeline_revision_id,
                    committed_pipeline_revision_id=current_pipeline_revision_id,
                    outcome="rejected",
                    reason="already_committed",
                )

            from face_moment.processing.serving_revision_guard import (
                read_serving_revision_guard,
            )

            guard = read_serving_revision_guard(
                self._session,
                spa_id=spa.id,
                pipeline_revision_id=current_pipeline_revision_id,
            )
            if guard.blocks_revision_change:
                return ServingRevisionSwitchResult(
                    spa_id=spa.id,
                    requested_pipeline_revision_id=target_pipeline_revision_id,
                    committed_pipeline_revision_id=current_pipeline_revision_id,
                    outcome="rejected",
                    reason="current_revision_has_active_processing",
                )

            spa.serving_pipeline_revision_id = target_revision.id
            self._session.flush()
            return ServingRevisionSwitchResult(
                spa_id=spa.id,
                requested_pipeline_revision_id=target_pipeline_revision_id,
                committed_pipeline_revision_id=target_revision.id,
                outcome="committed",
                reason="committed",
            )

    def _load_spa(self, spa_id: uuid.UUID, *, for_update: bool = False) -> Spa:
        statement = select(Spa).where(Spa.id == spa_id)
        if for_update:
            statement = statement.with_for_update()
        spa = self._session.scalar(statement)
        if spa is None:
            raise UnknownIngestTargetError(str(spa_id))
        if not spa.active:
            raise InactiveIngestTargetError(str(spa.id))
        return spa

    def _target_from_spa(self, spa: Spa) -> IngestTarget:
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

    def resolve_committed_serving_target(self) -> IngestTarget:
        """Return the one active target whose revision is committed to serve."""

        spa_ids = list(
            self._session.scalars(
                select(Spa.id).where(Spa.active.is_(True)).order_by(Spa.id).limit(2)
            )
        )
        if len(spa_ids) != 1:
            raise CommittedServingTargetUnavailableError(
                "exactly one active SPA target is required"
            )
        return self.resolve_ingest_target(spa_ids[0])

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
        from face_moment.processing.revisions import (
            IneligiblePipelineRevisionError,
            PipelineRevisionRepository,
        )

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

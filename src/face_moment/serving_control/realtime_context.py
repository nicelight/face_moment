from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
import json
import math
from types import MappingProxyType
from typing import cast
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    JSON,
    String,
    Uuid,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import func

from face_moment.infrastructure.database import Base
from face_moment.processing.revisions import (
    IneligiblePipelineRevisionError,
    PipelineCode,
    PipelineRevisionRepository,
)
from face_moment.serving_control.ingest_target import Spa

_MAX_QUALITY_SETTINGS_KEYS = 16
_MAX_QUALITY_SETTINGS_BYTES = 4096
_MAX_QUERY_SOURCE_LENGTH = 32
_MAX_RELEASE_ID_LENGTH = 255


class QuerySource(StrEnum):
    REFERENCE = "reference"


class ReferenceSearchSettings(Base):
    """Serving-control-owned threshold and query-quality settings."""

    __tablename__ = "reference_search_settings"
    __table_args__ = (
        CheckConstraint(
            "pipeline_code IN ('opencv_sface', 'insightface_buffalo_m')",
            name="ck_reference_search_settings_pipeline_code",
        ),
        CheckConstraint(
            "query_source = 'reference'",
            name="ck_reference_search_settings_query_source",
        ),
    )

    spa_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("face_moment.spas.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    pipeline_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    query_source: Mapped[str] = mapped_column(
        String(_MAX_QUERY_SOURCE_LENGTH), primary_key=True
    )
    reference_threshold: Mapped[float] = mapped_column(Double, nullable=False)
    min_query_face_quality: Mapped[float] = mapped_column(Double, nullable=False)
    quality_settings: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False
    )
    calibration_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReferenceSearchSettingsNotFoundError(LookupError):
    pass


class ReferenceSearchSettingsAlreadyExistsError(ValueError):
    pass


class UnknownRealtimeContextSpaError(LookupError):
    pass


class RealtimeReadinessClosedError(RuntimeError):
    """The realtime boundary must return 503 before promo admission."""

    status_code = 503

    def __init__(self, missing_fields: tuple[str, ...]) -> None:
        self.missing_fields = missing_fields
        super().__init__("realtime readiness is closed")


@dataclass(frozen=True, slots=True)
class RealtimeContext:
    """One copied, server-authoritative context for a realtime Attempt."""

    settings_revision: int
    spa_id: uuid.UUID
    visit_date: date
    pipeline_revision_id: uuid.UUID
    pipeline_code: PipelineCode
    query_source: QuerySource
    reference_threshold: float
    min_query_face_quality: float
    quality_settings: Mapping[str, object]
    calibration_id: uuid.UUID | None
    release_id: str


class RealtimeContextRepository:
    """Owner boundary for active-search settings and revision changes."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def provision_reference_settings(
        self,
        *,
        spa_id: uuid.UUID,
        pipeline_code: PipelineCode,
        reference_threshold: float,
        min_query_face_quality: float,
        quality_settings: Mapping[str, object],
        calibration_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> ReferenceSearchSettings:
        spa = self._load_spa(spa_id, for_update=True)
        normalized_pipeline = self._pipeline_code(pipeline_code)
        normalized_quality = self._quality_settings(quality_settings)
        existing = self._session.scalar(
            select(ReferenceSearchSettings).where(
                ReferenceSearchSettings.spa_id == spa_id,
                ReferenceSearchSettings.pipeline_code == normalized_pipeline,
                ReferenceSearchSettings.query_source == QuerySource.REFERENCE.value,
            )
        )
        if existing is not None:
            raise ReferenceSearchSettingsAlreadyExistsError(
                f"reference settings already exist for {spa_id}/{normalized_pipeline}"
            )
        settings = ReferenceSearchSettings(
            spa_id=spa.id,
            pipeline_code=normalized_pipeline,
            query_source=QuerySource.REFERENCE.value,
            reference_threshold=self._finite(
                reference_threshold, "reference_threshold"
            ),
            min_query_face_quality=self._finite(
                min_query_face_quality, "min_query_face_quality"
            ),
            quality_settings=normalized_quality,
            calibration_id=calibration_id,
            updated_at=self._utc(now),
        )
        self._session.add(settings)
        self._touch_spa(spa, now)
        self._session.flush()
        return settings

    def update_reference_settings(
        self,
        *,
        spa_id: uuid.UUID,
        pipeline_code: PipelineCode,
        reference_threshold: float,
        min_query_face_quality: float,
        quality_settings: Mapping[str, object],
        calibration_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> ReferenceSearchSettings:
        spa = self._load_spa(spa_id, for_update=True)
        normalized_pipeline = self._pipeline_code(pipeline_code)
        settings = self._session.scalar(
            select(ReferenceSearchSettings)
            .where(
                ReferenceSearchSettings.spa_id == spa_id,
                ReferenceSearchSettings.pipeline_code == normalized_pipeline,
                ReferenceSearchSettings.query_source == QuerySource.REFERENCE.value,
            )
            .with_for_update()
        )
        if settings is None:
            raise ReferenceSearchSettingsNotFoundError(
                f"reference settings not found for {spa_id}/{normalized_pipeline}"
            )
        normalized_threshold = self._finite(
            reference_threshold, "reference_threshold"
        )
        normalized_min_quality = self._finite(
            min_query_face_quality, "min_query_face_quality"
        )
        normalized_quality = self._quality_settings(quality_settings)
        normalized_updated_at = self._utc(now)
        settings.reference_threshold = normalized_threshold
        settings.min_query_face_quality = normalized_min_quality
        settings.quality_settings = normalized_quality
        settings.calibration_id = calibration_id
        settings.updated_at = normalized_updated_at
        self._touch_spa(spa, normalized_updated_at)
        self._session.flush()
        return settings

    def update_active_visit_date(
        self,
        *,
        spa_id: uuid.UUID,
        active_visit_date: date | None,
        now: datetime | None = None,
    ) -> Spa:
        spa = self._load_spa(spa_id, for_update=True)
        if isinstance(active_visit_date, datetime):
            raise ValueError("active_visit_date must be a date or None")
        normalized_updated_at = self._utc(now)
        spa.active_visit_date = active_visit_date
        self._touch_spa(spa, normalized_updated_at)
        self._session.flush()
        return spa

    def get_reference_settings(
        self, *, spa_id: uuid.UUID, pipeline_code: PipelineCode
    ) -> ReferenceSearchSettings:
        normalized_pipeline = self._pipeline_code(pipeline_code)
        settings = self._session.scalar(
            select(ReferenceSearchSettings).where(
                ReferenceSearchSettings.spa_id == spa_id,
                ReferenceSearchSettings.pipeline_code == normalized_pipeline,
                ReferenceSearchSettings.query_source == QuerySource.REFERENCE.value,
            )
        )
        if settings is None:
            raise ReferenceSearchSettingsNotFoundError(
                f"reference settings not found for {spa_id}/{normalized_pipeline}"
            )
        return settings

    def list_reference_settings(
        self, *, spa_id: uuid.UUID
    ) -> list[ReferenceSearchSettings]:
        return list(
            self._session.scalars(
                select(ReferenceSearchSettings)
                .where(ReferenceSearchSettings.spa_id == spa_id)
                .order_by(
                    ReferenceSearchSettings.pipeline_code,
                    ReferenceSearchSettings.query_source,
                )
            )
        )

    def resolve_realtime_context(
        self,
        *,
        spa_id: uuid.UUID,
        admitted_pipeline_revision_id: uuid.UUID | None,
        release_id: str,
    ) -> RealtimeContext:
        """Resolve the complete owner snapshot before realtime admission.

        The caller supplies only the authenticated SPA identity and the
        already-admitted model revision identity. Date, revision, query source,
        threshold, quality settings and calibration are read from owner state.
        This method performs reads only; a closed result is intentionally
        represented as a bounded 503-classified exception for the realtime
        boundary to map before promo admission.
        """

        # Supported serving-control updates lock this owner row before changing
        # the revision, active date, or settings. Holding the same lock across
        # all reads keeps those values in one coherent owner snapshot.
        spa = self._load_spa(spa_id, for_update=True)
        missing_fields: list[str] = []
        if spa.settings_revision <= 0:
            missing_fields.append("settings_revision")
        if spa.active_visit_date is None:
            missing_fields.append("visit_date")

        try:
            revision = PipelineRevisionRepository(self._session).resolve_eligible(
                spa.serving_pipeline_revision_id
            )
        except IneligiblePipelineRevisionError:
            revision = None
            missing_fields.append("pipeline_revision")

        settings: ReferenceSearchSettings | None = None
        if revision is not None:
            settings = self._session.scalar(
                select(ReferenceSearchSettings).where(
                    ReferenceSearchSettings.spa_id == spa.id,
                    ReferenceSearchSettings.pipeline_code == revision.pipeline_code.value,
                    ReferenceSearchSettings.query_source
                    == QuerySource.REFERENCE.value,
                )
            )
            if settings is None:
                missing_fields.append("reference_search_settings")

            if admitted_pipeline_revision_id is None:
                missing_fields.append("model_admission")
            elif admitted_pipeline_revision_id != revision.id:
                missing_fields.append("model_revision")
        else:
            if admitted_pipeline_revision_id is None:
                missing_fields.append("model_admission")

        try:
            normalized_release_id = self._release_id(release_id)
        except ValueError:
            normalized_release_id = ""
            missing_fields.append("release_id")

        if missing_fields or revision is None or settings is None:
            raise RealtimeReadinessClosedError(tuple(dict.fromkeys(missing_fields)))

        try:
            threshold = self._finite(
                settings.reference_threshold, "reference_threshold"
            )
            min_query_face_quality = self._finite(
                settings.min_query_face_quality, "min_query_face_quality"
            )
            quality_settings = self._quality_settings(settings.quality_settings)
        except ValueError as error:
            raise RealtimeReadinessClosedError((str(error).split(" ", 1)[0],)) from None

        if spa.active_visit_date is None:
            raise RealtimeReadinessClosedError(("visit_date",))

        frozen_quality_settings = cast(
            Mapping[str, object], _freeze_json(quality_settings)
        )
        return RealtimeContext(
            settings_revision=spa.settings_revision,
            spa_id=spa.id,
            visit_date=spa.active_visit_date,
            pipeline_revision_id=revision.id,
            pipeline_code=revision.pipeline_code,
            query_source=QuerySource.REFERENCE,
            reference_threshold=threshold,
            min_query_face_quality=min_query_face_quality,
            quality_settings=frozen_quality_settings,
            calibration_id=settings.calibration_id,
            release_id=normalized_release_id,
        )

    def _load_spa(self, spa_id: uuid.UUID, *, for_update: bool) -> Spa:
        statement = select(Spa).where(Spa.id == spa_id)
        if for_update:
            statement = statement.with_for_update()
        spa = self._session.scalar(statement)
        if spa is None:
            raise UnknownRealtimeContextSpaError(str(spa_id))
        if not spa.active:
            raise UnknownRealtimeContextSpaError(str(spa_id))
        return spa

    @staticmethod
    def _pipeline_code(pipeline_code: PipelineCode) -> str:
        if not isinstance(pipeline_code, PipelineCode):
            raise ValueError(f"unsupported pipeline code: {pipeline_code}")
        return pipeline_code.value

    @staticmethod
    def _release_id(release_id: str) -> str:
        if not isinstance(release_id, str):
            raise ValueError("release_id must be a non-empty string")
        normalized = release_id.strip()
        if not normalized:
            raise ValueError("release_id must be a non-empty string")
        if len(normalized) > _MAX_RELEASE_ID_LENGTH:
            raise ValueError("release_id exceeds 255 characters")
        return normalized

    @staticmethod
    def _finite(value: float, field_name: str) -> float:
        if not isinstance(value, (float, int)) or isinstance(value, bool):
            raise ValueError(f"{field_name} must be finite")
        normalized = float(value)
        if not math.isfinite(normalized):
            raise ValueError(f"{field_name} must be finite")
        return normalized

    @staticmethod
    def _quality_settings(
        quality_settings: Mapping[str, object],
    ) -> dict[str, object]:
        if not isinstance(quality_settings, Mapping):
            raise ValueError("quality_settings must be a JSON object")
        if len(quality_settings) > _MAX_QUALITY_SETTINGS_KEYS:
            raise ValueError("quality_settings contains too many keys")
        try:
            encoded = json.dumps(
                dict(quality_settings),
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as error:
            raise ValueError("quality_settings must be bounded JSON") from error
        if len(encoded.encode("utf-8")) > _MAX_QUALITY_SETTINGS_BYTES:
            raise ValueError("quality_settings exceeds the bounded size")
        return cast(dict[str, object], json.loads(encoded))

    @staticmethod
    def _utc(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if value.tzinfo is None:
            raise ValueError("realtime-context timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _touch_spa(spa: Spa, now: datetime | None) -> None:
        spa.settings_revision += 1
        spa.settings_updated_at = RealtimeContextRepository._utc(now)


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value

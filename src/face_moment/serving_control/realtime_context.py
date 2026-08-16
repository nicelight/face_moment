from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from enum import StrEnum
import json
import math
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
from face_moment.processing.revisions import PipelineCode
from face_moment.serving_control.ingest_target import Spa

_MAX_QUALITY_SETTINGS_KEYS = 16
_MAX_QUALITY_SETTINGS_BYTES = 4096
_MAX_QUERY_SOURCE_LENGTH = 32


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

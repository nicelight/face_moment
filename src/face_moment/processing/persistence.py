from __future__ import annotations

import uuid
import math
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from collections.abc import Sequence
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    JSON,
    String,
    Uuid,
    UniqueConstraint,
    asc,
    bindparam,
    cast as sql_cast,
    desc,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import UserDefinedType

from face_moment.infrastructure.database import Base
from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.initial_pending import PhotoPipelineState


class Vector(UserDefinedType[list[float]]):
    """Minimal pgvector type kept local because the runtime has no Python adapter."""

    cache_ok = True

    def get_col_spec(self, **_kw: Any) -> str:
        return "vector"


def _vector_literal(values: Sequence[float]) -> str:
    normalized = tuple(float(value) for value in values)
    if not normalized or any(not math.isfinite(value) for value in normalized):
        raise ValueError("query embedding must be finite and non-empty")
    return "[" + ",".join(format(value, ".9g") for value in normalized) + "]"


@dataclass(frozen=True, slots=True)
class CompatiblePhotoMatch:
    """One threshold-valid Photo match for one prepared detection."""

    photo_id: uuid.UUID
    pipeline_revision_id: uuid.UUID
    cosine_similarity: float
    preview_object_key: str


class PhotoFace(Base):
    """Processing-owned compatible face result for one Photo revision."""

    __tablename__ = "photo_faces"
    __table_args__ = (
        CheckConstraint("bbox_w > 0", name="ck_photo_faces_bbox_w_positive"),
        CheckConstraint("bbox_h > 0", name="ck_photo_faces_bbox_h_positive"),
        CheckConstraint(
            "bbox_x NOT IN ('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision) AND bbox_y NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision) AND bbox_w NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision) AND bbox_h NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision) AND detection_confidence NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_required_values_finite",
        ),
        CheckConstraint(
            "quality_score IS NULL OR quality_score NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_quality_score_finite",
        ),
        CheckConstraint(
            "blur_score IS NULL OR blur_score NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_blur_score_finite",
        ),
        CheckConstraint(
            "brightness_score IS NULL OR brightness_score NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_brightness_score_finite",
        ),
        CheckConstraint(
            "pose_yaw IS NULL OR pose_yaw NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_pose_yaw_finite",
        ),
        CheckConstraint(
            "pose_pitch IS NULL OR pose_pitch NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_pose_pitch_finite",
        ),
        CheckConstraint(
            "pose_roll IS NULL OR pose_roll NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_pose_roll_finite",
        ),
        UniqueConstraint(
            "photo_id",
            "pipeline_revision_id",
            "face_index",
            name="uq_photo_faces_photo_revision_face_index",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    photo_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("face_moment.photos.id", ondelete="RESTRICT"),
        nullable=False,
    )
    pipeline_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("face_moment.pipeline_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    face_index: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_x: Mapped[float] = mapped_column(Double, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Double, nullable=False)
    bbox_w: Mapped[float] = mapped_column(Double, nullable=False)
    bbox_h: Mapped[float] = mapped_column(Double, nullable=False)
    landmarks_json: Mapped[object] = mapped_column(JSON, nullable=False)
    detection_confidence: Mapped[float] = mapped_column(Double, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Double, nullable=True)
    blur_score: Mapped[float | None] = mapped_column(Double, nullable=True)
    brightness_score: Mapped[float | None] = mapped_column(Double, nullable=True)
    pose_yaw: Mapped[float | None] = mapped_column(Double, nullable=True)
    pose_pitch: Mapped[float | None] = mapped_column(Double, nullable=True)
    pose_roll: Mapped[float | None] = mapped_column(Double, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExactCompatibleSearchRepository:
    """Processing-owned read boundary for exact compatible Photo search."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def search(
        self,
        *,
        spa_id: uuid.UUID,
        visit_date: date,
        pipeline_revision_id: uuid.UUID,
        query_embedding: Sequence[float],
        reference_threshold: float,
    ) -> tuple[CompatiblePhotoMatch, ...]:
        """Search the immutable compatible ready scope using exact cosine distance."""

        if not math.isfinite(float(reference_threshold)):
            raise ValueError("reference_threshold must be finite")

        query_vector = sql_cast(
            bindparam("query_embedding", value=_vector_literal(query_embedding)),
            Vector(),
        )
        cosine_distance = PhotoFace.embedding.op("<=>")(query_vector)
        scoped = (
            select(
                Photo.id.label("photo_id"),
                PhotoPipelineState.pipeline_revision_id.label(
                    "pipeline_revision_id"
                ),
                PhotoPipelineState.preview_object_key.label("preview_object_key"),
                func.min(cosine_distance).label("cosine_distance"),
            )
            .select_from(PhotoFace)
            .join(Photo, Photo.id == PhotoFace.photo_id)
            .join(
                PhotoPipelineState,
                (PhotoPipelineState.photo_id == Photo.id)
                & (
                    PhotoPipelineState.pipeline_revision_id
                    == PhotoFace.pipeline_revision_id
                ),
            )
            .where(
                Photo.spa_id == spa_id,
                Photo.visit_date == visit_date,
                Photo.is_active.is_(True),
                Photo.admission_pipeline_revision_id == pipeline_revision_id,
                PhotoFace.pipeline_revision_id == pipeline_revision_id,
                PhotoPipelineState.pipeline_revision_id == pipeline_revision_id,
                PhotoPipelineState.status == "ready",
                PhotoPipelineState.preview_object_key.is_not(None),
                PhotoPipelineState.thumbnail_object_key.is_not(None),
            )
            .group_by(
                Photo.id,
                PhotoPipelineState.pipeline_revision_id,
                PhotoPipelineState.preview_object_key,
            )
            .subquery("compatible_scope")
        )
        similarity = 1.0 - scoped.c.cosine_distance
        statement = (
            select(
                scoped.c.photo_id,
                scoped.c.pipeline_revision_id,
                similarity.label("cosine_similarity"),
                scoped.c.preview_object_key,
            )
            .where(similarity >= float(reference_threshold))
            .order_by(desc(similarity), asc(scoped.c.photo_id))
        )
        rows = self._session.execute(statement).all()
        return tuple(
            CompatiblePhotoMatch(
                photo_id=row.photo_id,
                pipeline_revision_id=row.pipeline_revision_id,
                cosine_similarity=float(row.cosine_similarity),
                preview_object_key=row.preview_object_key,
            )
            for row in rows
        )


class ProcessingRuntimeStatus(Base):
    """Narrow singleton durable projection for the configured worker."""

    __tablename__ = "processing_runtime_status"
    __table_args__ = (
        CheckConstraint("singleton_id = 1", name="ck_processing_runtime_status_singleton"),
        CheckConstraint(
            "current_operation IN "
            "('idle', 'photo_processing', 'calibration', 'hard_purge', "
            "'retention_cleanup')",
            name="ck_processing_runtime_status_operation",
        ),
        CheckConstraint(
            "(current_operation = 'idle' AND operation_started_at IS NULL) "
            "OR (current_operation <> 'idle' AND operation_started_at IS NOT NULL)",
            name="ck_processing_runtime_status_operation_started_at",
        ),
    )

    singleton_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    worker_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_recovery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_recovered_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    current_operation: Mapped[str] = mapped_column(
        String(length=20), nullable=False, server_default="idle"
    )
    operation_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

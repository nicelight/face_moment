from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace
from face_moment.processing.revisions import PipelineRevision
from face_moment.serving_control.ingest_target import Spa

_READY = "ready"


@dataclass(frozen=True, slots=True)
class SearchablePhotoProjection:
    """Processing-owned eligibility facts for one persisted Photo state."""

    photo_id: uuid.UUID
    pipeline_revision_id: uuid.UUID
    pipeline_code: str
    processing_status: str
    attempt_count: int
    status_changed_at: datetime
    searchable_at: datetime | None
    failure_reason: str | None
    photo_is_active: bool
    is_current_serving_revision: bool
    has_complete_derivatives: bool
    has_valid_face: bool
    searchable: bool


class SearchableProjectionRepository:
    """Read the complete compatible-searchability rule without querying faces."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> SearchablePhotoProjection | None:
        """Return one exact owner-backed eligibility projection, if state exists."""

        return self._resolve(
            photo_id=photo_id,
            pipeline_revision_id=pipeline_revision_id,
        )

    def resolve_for_photo(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> SearchablePhotoProjection | None:
        """Return the exact admission-selected processing projection for a Photo."""

        return self._resolve(
            photo_id=photo_id,
            pipeline_revision_id=pipeline_revision_id,
        )

    def _resolve(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> SearchablePhotoProjection | None:
        """Read owner facts and derive the completed searchable truth."""

        has_face = exists(
            select(1).where(
                PhotoFace.photo_id == PhotoPipelineState.photo_id,
                PhotoFace.pipeline_revision_id
                == PhotoPipelineState.pipeline_revision_id,
            )
        )
        statement = (
            select(
                PhotoPipelineState.photo_id,
                PhotoPipelineState.pipeline_revision_id,
                PipelineRevision.pipeline_code,
                PhotoPipelineState.status,
                PhotoPipelineState.attempt_count,
                PhotoPipelineState.status_changed_at,
                PhotoPipelineState.searchable_at,
                PhotoPipelineState.last_error,
                Photo.is_active,
                Spa.serving_pipeline_revision_id,
                PhotoPipelineState.preview_object_key,
                PhotoPipelineState.thumbnail_object_key,
                has_face,
            )
            .join(Photo, Photo.id == PhotoPipelineState.photo_id)
            .join(Spa, Spa.id == Photo.spa_id)
            .join(
                PipelineRevision,
                PipelineRevision.id == PhotoPipelineState.pipeline_revision_id,
            )
            .where(
                PhotoPipelineState.photo_id == photo_id,
                PhotoPipelineState.pipeline_revision_id == pipeline_revision_id,
            )
        )
        row = self._session.execute(statement).one_or_none()
        if row is None:
            return None

        (
            resolved_photo_id,
            resolved_revision_id,
            pipeline_code,
            status,
            attempt_count,
            status_changed_at,
            searchable_at,
            failure_reason,
            photo_is_active,
            serving_revision_id,
            preview_object_key,
            thumbnail_object_key,
            has_valid_face,
        ) = row
        is_current_serving_revision = resolved_revision_id == serving_revision_id
        has_complete_derivatives = (
            preview_object_key is not None and thumbnail_object_key is not None
        )
        searchable = (
            photo_is_active
            and status == _READY
            and is_current_serving_revision
            and has_complete_derivatives
            and has_valid_face
        )
        return SearchablePhotoProjection(
            photo_id=resolved_photo_id,
            pipeline_revision_id=resolved_revision_id,
            pipeline_code=pipeline_code,
            processing_status=status,
            attempt_count=attempt_count,
            status_changed_at=status_changed_at,
            searchable_at=searchable_at,
            failure_reason=failure_reason,
            photo_is_active=photo_is_active,
            is_current_serving_revision=is_current_serving_revision,
            has_complete_derivatives=has_complete_derivatives,
            has_valid_face=has_valid_face,
            searchable=searchable,
        )


def read_photo_processing_projection(
    session: Session,
    *,
    photo_id: uuid.UUID,
    pipeline_revision_id: uuid.UUID,
) -> SearchablePhotoProjection | None:
    """Public processing read boundary for one inventory-owned staff outcome."""

    return SearchableProjectionRepository(session).resolve_for_photo(
        photo_id=photo_id,
        pipeline_revision_id=pipeline_revision_id,
    )

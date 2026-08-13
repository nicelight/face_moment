from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace
from face_moment.serving_control.ingest_target import Spa

_READY = "ready"


@dataclass(frozen=True, slots=True)
class SearchablePhotoProjection:
    """Processing-owned eligibility facts for one persisted Photo state."""

    photo_id: uuid.UUID
    pipeline_revision_id: uuid.UUID
    processing_status: str
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
        """Return the current owner-backed eligibility projection, if state exists."""

        has_face = exists(
            select(1).where(
                PhotoFace.photo_id == PhotoPipelineState.photo_id,
                PhotoFace.pipeline_revision_id
                == PhotoPipelineState.pipeline_revision_id,
            )
        )
        row = self._session.execute(
            select(
                PhotoPipelineState.photo_id,
                PhotoPipelineState.pipeline_revision_id,
                PhotoPipelineState.status,
                Photo.is_active,
                Spa.serving_pipeline_revision_id,
                PhotoPipelineState.preview_object_key,
                PhotoPipelineState.thumbnail_object_key,
                has_face,
            )
            .join(Photo, Photo.id == PhotoPipelineState.photo_id)
            .join(Spa, Spa.id == Photo.spa_id)
            .where(
                PhotoPipelineState.photo_id == photo_id,
                PhotoPipelineState.pipeline_revision_id == pipeline_revision_id,
            )
        ).one_or_none()
        if row is None:
            return None

        (
            resolved_photo_id,
            resolved_revision_id,
            status,
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
            processing_status=status,
            photo_is_active=photo_is_active,
            is_current_serving_revision=is_current_serving_revision,
            has_complete_derivatives=has_complete_derivatives,
            has_valid_face=has_valid_face,
            searchable=searchable,
        )

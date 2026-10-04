"""Native current-selfie preparation and all-date exact public Photo search."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from collections.abc import Sequence
import uuid
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from face_moment.inventory.public_photo_projection import PublicPhotoReference, public_active_photo_scope
from face_moment.processing.initial_pending import PhotoPipelineState
from typing import TYPE_CHECKING
import numpy as np
from numpy.typing import NDArray

from face_moment.processing.persistence import PublicExactSearchRepository, PublicPhotoMatch
from face_moment.processing.reference_query import PreparedReferenceQuery

if TYPE_CHECKING:
    from face_moment.processing.face_engine import FaceEngine
    from face_moment.serving_control.public_search_context import PublicSearchContext


@dataclass(frozen=True, slots=True)
class PublicSelfieObservation:
    native_face_count: int
    reference_quality_score: float
    quality_gate_passed: bool
    rejection_reason: str | None
    query: PreparedReferenceQuery | None


def prepare_public_selfie(
    *, context: PublicSearchContext, engine: FaceEngine, selfie: NDArray[np.uint8],
) -> PublicSelfieObservation:
    """Prepare only the current selfie before any profile change or search."""
    quality = engine.inspect_reference_crop(selfie, context.venues[0].quality_settings)
    reason = None
    if quality.native_face_count != 1:
        reason = "no_face" if quality.native_face_count == 0 else "multiple_faces"
    elif quality.reference_quality_score < context.min_query_face_quality:
        reason = "low_quality"
    query = quality.prepared_query if reason is None else None
    if reason is None and query is None:
        query = engine.prepare_reference_query(selfie)
        if query is None:
            reason = "unacceptable_query"
    if query is not None:
        if query.pipeline_revision_id != context.pipeline_revision_id:
            raise ValueError("selfie query revision does not match admission")
        if not np.isclose(np.linalg.norm(query.embedding), 1., rtol=1e-3, atol=1e-3):
            raise ValueError("selfie embedding must be normalized")
    return PublicSelfieObservation(
        native_face_count=quality.native_face_count,
        reference_quality_score=quality.reference_quality_score,
        quality_gate_passed=reason is None,
        rejection_reason=reason, query=query,
    )


def search_public_selfie(
    *, repository: PublicExactSearchRepository, context: PublicSearchContext,
    query: PreparedReferenceQuery,
) -> tuple[PublicPhotoMatch, ...]:
    """Search an accepted current query; Promo owns A/B admission/result writes."""
    if query.pipeline_revision_id != context.pipeline_revision_id:
        raise ValueError("selfie query revision does not match admission")
    return repository.search(
        pipeline_revision_id=context.pipeline_revision_id,
        query_embedding=tuple(float(value) for value in query.embedding),
        venue_thresholds=tuple((item.spa_id, item.reference_threshold) for item in context.venues),
    )


def read_public_common_photos(
    session: "Session", *, pipeline_revision_id: "uuid.UUID",
    matched_dates: "Sequence[tuple[uuid.UUID, date]]",
) -> tuple["PublicPhotoReference", ...]:
    """Processing publishes no_faces only inside inventory active matched dates."""
    if not matched_dates:
        return ()
    photos = public_active_photo_scope(tuple({venue for venue, _ in matched_dates}))
    statement = (select(photos.c.photo_id, photos.c.spa_id, photos.c.visit_date)
        .join(PhotoPipelineState, (PhotoPipelineState.photo_id == photos.c.photo_id)
              & (PhotoPipelineState.pipeline_revision_id == pipeline_revision_id))
        .where(PhotoPipelineState.status == "no_faces",
               or_(*((photos.c.spa_id == venue) & (photos.c.visit_date == day) for venue, day in matched_dates)))
        .order_by(photos.c.spa_id, photos.c.visit_date, photos.c.photo_id))
    return tuple(PublicPhotoReference(row.photo_id, row.spa_id, row.visit_date) for row in session.execute(statement))

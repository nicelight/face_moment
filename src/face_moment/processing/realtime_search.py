from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING
import uuid

import cv2
import numpy as np

from face_moment.processing.derivatives import PrivateDerivativeObjectStore
from face_moment.processing.persistence import (
    CompatiblePhotoMatch,
    ExactCompatibleSearchRepository,
)
from face_moment.processing.reference_query import (
    ReferenceOccurrence,
    ReferenceQueryObservation,
    select_reference_queries,
)

if TYPE_CHECKING:
    from face_moment.processing.face_engine import FaceEngine
    from face_moment.serving_control.realtime_context import RealtimeContext


@dataclass(frozen=True, slots=True)
class PhotoMatchObservation:
    """One threshold-valid Photo plus its ranking-only private-preview pHash."""

    photo_id: uuid.UUID
    cosine_similarity: float
    preview_object_key: str
    phash64: int


@dataclass(frozen=True, slots=True)
class DetectionSearchObservation:
    """One selected detection and all of its independent exact matches."""

    occurrence_index: int
    rank: int
    reference_quality_score: float
    quality_gate_passed: bool
    rejection_reason: str | None
    matches: tuple[PhotoMatchObservation, ...]


@dataclass(frozen=True, slots=True)
class RealtimeSearchResult:
    """Processing result; Promo owns any union, teaser or session outcome."""

    detections: tuple[DetectionSearchObservation, ...]


def opencv_phash64_v1(image_bytes: bytes) -> int:
    """Compute the deterministic 64-bit OpenCV-compatible pHash value."""

    decoded = cv2.imdecode(
        np.frombuffer(image_bytes, dtype=np.uint8),
        cv2.IMREAD_GRAYSCALE,
    )
    if decoded is None:
        raise ValueError("private preview cannot be decoded")
    resized = cv2.resize(decoded, (32, 32), interpolation=cv2.INTER_AREA)
    coefficients = np.asarray(
        cv2.dct(np.asarray(resized, dtype=np.float32))[:8, :8],
        dtype=np.float32,
    )
    average = float(np.mean(coefficients))
    value = 0
    for coefficient in coefficients.reshape(-1):
        value = (value << 1) | int(float(coefficient) > average)
    return value


class RealtimeSearchService:
    """Compose W1 selection with processing-owned exact compatible search."""

    def __init__(
        self,
        repository: ExactCompatibleSearchRepository,
        object_store: PrivateDerivativeObjectStore,
    ) -> None:
        self._repository = repository
        self._object_store = object_store

    def search(
        self,
        *,
        context: RealtimeContext,
        engine: FaceEngine,
        occurrences: Sequence[ReferenceOccurrence],
    ) -> RealtimeSearchResult:
        """Search every selected acceptable occurrence independently."""

        selected = select_reference_queries(
            engine=engine,
            occurrences=occurrences,
            min_query_face_quality=context.min_query_face_quality,
            quality_settings=context.quality_settings,
        )
        phash_cache: dict[uuid.UUID, int] = {}
        detections = tuple(
            self._search_detection(
                context=context,
                observation=observation,
                phash_cache=phash_cache,
            )
            for observation in selected
        )
        return RealtimeSearchResult(detections=detections)

    def _search_detection(
        self,
        *,
        context: RealtimeContext,
        observation: ReferenceQueryObservation,
        phash_cache: dict[uuid.UUID, int],
    ) -> DetectionSearchObservation:
        query = observation.query
        if query is None:
            return DetectionSearchObservation(
                occurrence_index=observation.occurrence_index,
                rank=observation.rank,
                reference_quality_score=observation.reference_quality_score,
                quality_gate_passed=observation.quality_gate_passed,
                rejection_reason=observation.rejection_reason,
                matches=(),
            )
        if query.pipeline_revision_id != context.pipeline_revision_id:
            raise ValueError("reference query revision does not match search context")

        matches = self._repository.search(
            spa_id=context.spa_id,
            visit_date=context.visit_date,
            pipeline_revision_id=context.pipeline_revision_id,
            query_embedding=tuple(float(value) for value in query.embedding),
            reference_threshold=context.reference_threshold,
        )
        return DetectionSearchObservation(
            occurrence_index=observation.occurrence_index,
            rank=observation.rank,
            reference_quality_score=observation.reference_quality_score,
            quality_gate_passed=observation.quality_gate_passed,
            rejection_reason=observation.rejection_reason,
            matches=tuple(
                self._with_phash(match=match, phash_cache=phash_cache)
                for match in matches
            ),
        )

    def _with_phash(
        self,
        *,
        match: CompatiblePhotoMatch,
        phash_cache: dict[uuid.UUID, int],
    ) -> PhotoMatchObservation:
        phash = phash_cache.get(match.photo_id)
        if phash is None:
            phash = opencv_phash64_v1(
                self._object_store.read(key=match.preview_object_key)
            )
            phash_cache[match.photo_id] = phash
        return PhotoMatchObservation(
            photo_id=match.photo_id,
            cosine_similarity=match.cosine_similarity,
            preview_object_key=match.preview_object_key,
            phash64=phash,
        )


def search_realtime_references(
    *,
    repository: ExactCompatibleSearchRepository,
    object_store: PrivateDerivativeObjectStore,
    context: RealtimeContext,
    engine: FaceEngine,
    occurrences: Sequence[ReferenceOccurrence],
) -> RealtimeSearchResult:
    """Public processing application boundary for one realtime search."""

    return RealtimeSearchService(repository, object_store).search(
        context=context,
        engine=engine,
        occurrences=occurrences,
    )

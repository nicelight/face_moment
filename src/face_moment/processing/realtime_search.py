from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING
import uuid

from face_moment.processing.persistence import (
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
    best_cosine_similarity: float | None = None
    eligible_photo_count: int | None = None


@dataclass(frozen=True, slots=True)
class RealtimeSearchResult:
    """Processing result; Promo owns any union, teaser or session outcome."""

    detections: tuple[DetectionSearchObservation, ...]


class RealtimeSearchService:
    """Compose W1 selection with processing-owned exact compatible search."""

    def __init__(
        self,
        repository: ExactCompatibleSearchRepository,
    ) -> None:
        self._repository = repository

    def search(
        self,
        *,
        context: RealtimeContext,
        engine: FaceEngine,
        occurrences: Sequence[ReferenceOccurrence],
        capture_observations: dict[int, dict[str, object]] | None = None,
    ) -> RealtimeSearchResult:
        """Search every selected acceptable occurrence independently."""

        selected = select_reference_queries(
            engine=engine,
            occurrences=occurrences,
            min_query_face_quality=context.min_query_face_quality,
            quality_settings=context.quality_settings,
            capture_observations=capture_observations,
        )
        detections = tuple(
            self._search_detection(
                context=context,
                observation=observation,
            )
            for observation in selected
        )
        return RealtimeSearchResult(detections=detections)

    def _search_detection(
        self,
        *,
        context: RealtimeContext,
        observation: ReferenceQueryObservation,
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

        search = self._repository.search_with_diagnostics(
            spa_id=context.spa_id,
            visit_date=context.visit_date,
            visit_date_to=context.visit_date_to,
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
                PhotoMatchObservation(
                    photo_id=match.photo_id,
                    cosine_similarity=match.cosine_similarity,
                    preview_object_key=match.preview_object_key,
                    phash64=match.phash64,
                )
                for match in search.matches
            ),
            best_cosine_similarity=search.best_cosine_similarity,
            eligible_photo_count=search.eligible_photo_count,
        )


def search_realtime_references(
    *,
    repository: ExactCompatibleSearchRepository,
    context: RealtimeContext,
    engine: FaceEngine,
    occurrences: Sequence[ReferenceOccurrence],
    capture_observations: dict[int, dict[str, object]] | None = None,
) -> RealtimeSearchResult:
    """Public processing application boundary for one realtime search."""

    return RealtimeSearchService(repository).search(
        context=context,
        engine=engine,
        occurrences=occurrences,
        capture_observations=capture_observations,
    )

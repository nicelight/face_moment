from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from face_moment.processing.face_engine import FaceEngine


@dataclass(frozen=True, slots=True)
class ReferenceQualityObservation:
    """Native, bounded quality observations for one request-local occurrence."""

    reference_quality_score: float
    native_face_count: int
    gate_observations: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not math.isfinite(self.reference_quality_score):
            raise ValueError("reference_quality_score must be finite")
        if self.native_face_count < 0:
            raise ValueError("native_face_count must not be negative")
        if any(not math.isfinite(value) for _, value in self.gate_observations):
            raise ValueError("gate observations must be finite")


@dataclass(frozen=True, slots=True)
class PreparedReferenceQuery:
    """One normalized embedding prepared by the admitted native revision."""

    pipeline_revision_id: uuid.UUID
    embedding: NDArray[np.float32]

    def __post_init__(self) -> None:
        embedding = np.asarray(self.embedding, dtype=np.float32).reshape(-1)
        if embedding.size == 0 or not np.isfinite(embedding).all():
            raise ValueError("reference query embedding must be finite and non-empty")
        object.__setattr__(self, "embedding", np.array(embedding, copy=True))


@dataclass(frozen=True, slots=True)
class ReferenceOccurrence:
    """One client-admitted crop with its request-local occurrence identity."""

    occurrence_index: int
    crop: NDArray[np.uint8]

    def __post_init__(self) -> None:
        if self.occurrence_index < 0:
            raise ValueError("occurrence_index must not be negative")


@dataclass(frozen=True, slots=True)
class ReferenceQueryObservation:
    """One selected occurrence, including a bounded rejected outcome when needed."""

    occurrence_index: int
    rank: int
    reference_quality_score: float
    quality_gate_passed: bool
    query: PreparedReferenceQuery | None
    rejection_reason: str | None


def select_reference_queries(
    *,
    engine: FaceEngine,
    occurrences: Sequence[ReferenceOccurrence],
    min_query_face_quality: float,
    quality_settings: Mapping[str, object],
) -> tuple[ReferenceQueryObservation, ...]:
    """Inspect all occurrences and prepare the deterministic top five."""

    if isinstance(min_query_face_quality, bool) or not math.isfinite(
        float(min_query_face_quality)
    ):
        raise ValueError("min_query_face_quality must be finite")

    indexed_occurrences = tuple(occurrences)
    occurrence_indices = [item.occurrence_index for item in indexed_occurrences]
    if len(set(occurrence_indices)) != len(occurrence_indices):
        raise ValueError("occurrence_index must be unique within one request")

    inspected = tuple(
        (
            occurrence,
            engine.inspect_reference_crop(
                occurrence.crop,
                quality_settings,
            ),
        )
        for occurrence in indexed_occurrences
    )
    ranked = sorted(
        inspected,
        key=lambda item: (
            -item[1].reference_quality_score,
            item[0].occurrence_index,
        ),
    )[:5]

    observations: list[ReferenceQueryObservation] = []
    for rank, (occurrence, quality) in enumerate(ranked, start=1):
        quality_gate_passed = (
            quality.native_face_count > 0
            and quality.reference_quality_score >= float(min_query_face_quality)
        )
        if not quality_gate_passed:
            observations.append(
                ReferenceQueryObservation(
                    occurrence_index=occurrence.occurrence_index,
                    rank=rank,
                    reference_quality_score=quality.reference_quality_score,
                    quality_gate_passed=False,
                    query=None,
                    rejection_reason="low_quality",
                )
            )
            continue

        query = engine.prepare_reference_query(occurrence.crop)
        observations.append(
            ReferenceQueryObservation(
                occurrence_index=occurrence.occurrence_index,
                rank=rank,
                reference_quality_score=quality.reference_quality_score,
                quality_gate_passed=True,
                query=query,
                rejection_reason=None if query is not None else "unacceptable_query",
            )
        )
    return tuple(observations)

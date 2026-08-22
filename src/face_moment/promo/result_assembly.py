from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal
import uuid

from face_moment.processing.realtime_search import (
    DetectionSearchObservation,
    PhotoMatchObservation,
    RealtimeSearchResult,
)

_SUCCESS: Literal["result"] = "result"
_INSUFFICIENT: Literal["insufficient_results"] = "insufficient_results"


@dataclass(frozen=True, slots=True)
class ResultAssembly:
    """Promo-owned result truth produced from processing match observations."""

    outcome: Literal["result", "insufficient_results"]
    session_result_photo_ids: tuple[uuid.UUID, ...]
    teaser_photo_ids: tuple[uuid.UUID, ...]
    n: int


def assemble_result(
    search_result: RealtimeSearchResult | Sequence[DetectionSearchObservation],
) -> ResultAssembly:
    """Assemble four teasers and the complete valid Photo union.

    Processing has already applied query-quality and similarity thresholds.
    This pure Promo boundary only unions those typed observations and ranks
    valid candidates for teaser diversity; it performs no persistence or I/O.
    """

    detections = _detections(search_result)
    session_result_photo_ids = _unique_union(detections)
    diverse_pool: list[PhotoMatchObservation] = []
    fallback_pool: list[PhotoMatchObservation] = []
    reserved_photo_ids: set[uuid.UUID] = set()

    for detection in detections:
        if not detection.quality_gate_passed:
            continue
        candidates = [
            match
            for match in _ordered_unique_matches(detection.matches)
            if match.photo_id not in reserved_photo_ids
        ]
        selected_for_detection: list[PhotoMatchObservation] = []
        if candidates:
            selected_for_detection.append(candidates[0])
            while len(selected_for_detection) < 4:
                remaining = [
                    candidate
                    for candidate in candidates
                    if candidate.photo_id
                    not in {item.photo_id for item in selected_for_detection}
                ]
                if not remaining:
                    break
                next_candidate = _farthest_first(
                    remaining, selected_for_detection
                )
                if _minimum_distance(next_candidate, selected_for_detection) == 0:
                    break
                selected_for_detection.append(next_candidate)

            for candidate in selected_for_detection:
                diverse_pool.append(candidate)
                reserved_photo_ids.add(candidate.photo_id)

            remaining_capacity = 4 - len(selected_for_detection)
            for candidate in candidates:
                if remaining_capacity == 0:
                    break
                if candidate.photo_id in reserved_photo_ids:
                    continue
                fallback_pool.append(candidate)
                reserved_photo_ids.add(candidate.photo_id)
                remaining_capacity -= 1

    if len(diverse_pool) < 4:
        for candidate in fallback_pool:
            diverse_pool.append(candidate)
            if len(diverse_pool) == 4:
                break

    if len(session_result_photo_ids) < 4 or len(diverse_pool) < 4:
        return ResultAssembly(
            outcome=_INSUFFICIENT,
            session_result_photo_ids=session_result_photo_ids,
            teaser_photo_ids=(),
            n=len(session_result_photo_ids),
        )

    teasers = (
        tuple(diverse_pool)
        if len(diverse_pool) == 4
        else _final_teasers(diverse_pool)
    )
    return ResultAssembly(
        outcome=_SUCCESS,
        session_result_photo_ids=session_result_photo_ids,
        teaser_photo_ids=tuple(item.photo_id for item in teasers),
        n=len(session_result_photo_ids),
    )


def _detections(
    search_result: RealtimeSearchResult | Sequence[DetectionSearchObservation],
) -> tuple[DetectionSearchObservation, ...]:
    if isinstance(search_result, RealtimeSearchResult):
        return search_result.detections
    return tuple(search_result)


def _unique_union(
    detections: Iterable[DetectionSearchObservation],
) -> tuple[uuid.UUID, ...]:
    photo_ids: dict[uuid.UUID, None] = {}
    for detection in detections:
        if not detection.quality_gate_passed:
            continue
        for match in detection.matches:
            photo_ids.setdefault(match.photo_id, None)
    return tuple(photo_ids)


def _ordered_unique_matches(
    matches: Iterable[PhotoMatchObservation],
) -> tuple[PhotoMatchObservation, ...]:
    ordered = sorted(matches, key=_similarity_order_key)
    unique: dict[uuid.UUID, PhotoMatchObservation] = {}
    for match in ordered:
        unique.setdefault(match.photo_id, match)
    return tuple(unique.values())


def _similarity_order_key(
    match: PhotoMatchObservation,
) -> tuple[float, bytes]:
    return (-match.cosine_similarity, match.photo_id.bytes)


def _minimum_distance(
    candidate: PhotoMatchObservation,
    selected: Sequence[PhotoMatchObservation],
) -> int:
    return min(
        (candidate.phash64 ^ item.phash64).bit_count() for item in selected
    )


def _farthest_first(
    candidates: Sequence[PhotoMatchObservation],
    selected: Sequence[PhotoMatchObservation],
) -> PhotoMatchObservation:
    return min(
        candidates,
        key=lambda candidate: (
            -_minimum_distance(candidate, selected),
            -candidate.cosine_similarity,
            candidate.photo_id.bytes,
        ),
    )


def _final_teasers(
    candidates: Sequence[PhotoMatchObservation],
) -> tuple[PhotoMatchObservation, ...]:
    first = min(candidates, key=_similarity_order_key)
    selected = [first]
    remaining = [candidate for candidate in candidates if candidate is not first]
    while len(selected) < 4 and remaining:
        next_candidate = _farthest_first(remaining, selected)
        selected.append(next_candidate)
        remaining.remove(next_candidate)
    return tuple(selected)

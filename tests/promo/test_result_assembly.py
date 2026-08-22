from __future__ import annotations

import uuid

from face_moment.processing import (
    DetectionSearchObservation,
    PhotoMatchObservation,
    RealtimeSearchResult,
)
from face_moment.promo import ResultAssembly, assemble_result


def _photo(number: int) -> uuid.UUID:
    return uuid.UUID(int=number)


def _match(number: int, similarity: float, phash64: int) -> PhotoMatchObservation:
    return PhotoMatchObservation(
        photo_id=_photo(number),
        cosine_similarity=similarity,
        preview_object_key=f"preview/{number}",
        phash64=phash64,
    )


def _detection(
    rank: int, matches: tuple[PhotoMatchObservation, ...], *, passed: bool = True
) -> DetectionSearchObservation:
    return DetectionSearchObservation(
        occurrence_index=rank - 1,
        rank=rank,
        reference_quality_score=1.0,
        quality_gate_passed=passed,
        rejection_reason=None if passed else "low_quality",
        matches=matches,
    )


def _search_result(
    *detections: DetectionSearchObservation,
) -> RealtimeSearchResult:
    return RealtimeSearchResult(detections=detections)


def test_assembly_deduplicates_repeated_photos_and_issues_truthful_n() -> None:
    result = assemble_result(
        _search_result(
            _detection(
                1,
                (
                    _match(1, 0.99, 0x0000000000000000),
                    _match(2, 0.98, 0xFFFFFFFFFFFFFFFF),
                    _match(3, 0.97, 0x0F0F0F0F0F0F0F0F),
                    _match(4, 0.96, 0xF0F0F0F0F0F0F0F0),
                ),
            ),
            _detection(
                2,
                (
                    _match(1, 0.97, 0x0000000000000000),
                    _match(5, 0.96, 0xAAAAAAAAAAAAAAAA),
                    _match(6, 0.95, 0x5555555555555555),
                ),
            ),
            _detection(
                3,
                (
                    _match(5, 0.94, 0xAAAAAAAAAAAAAAAA),
                    _match(7, 0.93, 0x3333333333333333),
                ),
            ),
        )
    )

    assert isinstance(result, ResultAssembly)
    assert result.outcome == "result"
    assert result.session_result_photo_ids == tuple(_photo(number) for number in range(1, 8))
    assert result.teaser_photo_ids == tuple(_photo(number) for number in range(1, 5))
    assert result.n == 7
    assert len(result.teaser_photo_ids) == len(set(result.teaser_photo_ids)) == 4
    assert set(result.teaser_photo_ids) <= set(result.session_result_photo_ids)


def test_assembly_ignores_matches_from_rejected_detection() -> None:
    weak = _match(99, 0.01, 0)
    result = assemble_result(
        _search_result(
            _detection(
                1,
                (
                    _match(1, 0.99, 0),
                    _match(2, 0.98, 1),
                    _match(3, 0.97, 2),
                    _match(4, 0.96, 4),
                ),
            ),
            _detection(2, (weak,), passed=False),
        )
    )

    assert result.outcome == "result"
    assert result.n == 4
    assert _photo(99) not in result.session_result_photo_ids
    assert _photo(99) not in result.teaser_photo_ids


def test_assembly_preserves_order_for_exact_four_multi_detection_pool() -> None:
    result = assemble_result(
        _search_result(
            _detection(1, (_match(1, 0.50, 0),)),
            _detection(
                2,
                (
                    _match(2, 0.99, 1),
                    _match(3, 0.98, 2),
                    _match(4, 0.97, 4),
                ),
            ),
        )
    )

    assert result.outcome == "result"
    assert result.session_result_photo_ids == tuple(_photo(number) for number in range(1, 5))
    assert result.teaser_photo_ids == tuple(_photo(number) for number in range(1, 5))
    assert result.n == 4


def test_assembly_resolves_diversity_ties_by_similarity_then_photo_id() -> None:
    result = assemble_result(
        _search_result(
            _detection(
                1,
                (
                    _match(1, 1.00, 0),
                    _match(2, 0.90, 1),
                    _match(3, 0.90, 2),
                    _match(4, 0.80, 4),
                    _match(5, 0.70, 8),
                ),
            )
        )
    )

    assert result.outcome == "result"
    assert result.teaser_photo_ids == tuple(_photo(number) for number in range(1, 5))
    assert result.n == 5


def test_assembly_fallback_fills_four_when_phash_distance_is_zero() -> None:
    result = assemble_result(
        _search_result(
            _detection(
                1,
                (
                    _match(1, 0.99, 0),
                    _match(2, 0.98, 0),
                    _match(3, 0.97, 0),
                    _match(4, 0.96, 0),
                ),
            )
        )
    )

    assert result.outcome == "result"
    assert result.teaser_photo_ids == tuple(_photo(number) for number in range(1, 5))
    assert result.n == 4


def test_assembly_returns_insufficient_results_without_partial_teasers() -> None:
    result = assemble_result(
        _search_result(
            _detection(1, (_match(1, 0.99, 0), _match(2, 0.98, 1))),
            _detection(2, (_match(1, 0.97, 0), _match(3, 0.96, 2))),
        )
    )

    assert result.outcome == "insufficient_results"
    assert result.session_result_photo_ids == (_photo(1), _photo(2), _photo(3))
    assert result.teaser_photo_ids == ()
    assert result.n == 3

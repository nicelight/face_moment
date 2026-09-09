from face_moment.diagnostics.http import _render_search_evidence
from face_moment.processing.realtime_search import DetectionSearchObservation, RealtimeSearchResult
from face_moment.promo.realtime_evidence import _detections_manifest


def test_rejected_scores_reach_summary_without_becoming_matches() -> None:
    search = RealtimeSearchResult(detections=tuple(
        DetectionSearchObservation(
            occurrence_index=index, rank=index + 1, reference_quality_score=0.95,
            quality_gate_passed=True, rejection_reason=None, matches=(),
            best_cosine_similarity=score, eligible_photo_count=6,
        ) for index, score in enumerate((-0.2, 0.53))
    ))
    detections = _detections_manifest(search)
    assert all(item["matches"] == [] for item in detections)
    html = _render_search_evidence({"detections": detections, "serving": {"threshold": 0.6}})
    assert 'id="best-cosine-similarity">0.5300<' in html
    assert '<td>6</td><td>0</td><td>0.5300</td>' in html
    assert '-0.2000' in html


def test_legacy_missing_and_negative_scores_are_truthful() -> None:
    assert _render_search_evidence(None) == ""
    legacy = _render_search_evidence({"detections": [{"matches": []}]})
    assert 'id="best-cosine-similarity">нет данных<' in legacy
    assert '<td>не сохранено</td>' in legacy
    empty = _render_search_evidence({"detections": [{"best_cosine_similarity": None, "eligible_photo_count": 0}]})
    assert '<td>нет оценки</td>' in empty
    negative = _render_search_evidence({"detections": [{"best_cosine_similarity": -0.2}]})
    assert 'id="best-cosine-similarity">-0.2000<' in negative

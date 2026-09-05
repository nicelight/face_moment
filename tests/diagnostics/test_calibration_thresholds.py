"""Fixed independent oracle for Calibration threshold profiles (FT-011-AC-001/006)."""

from __future__ import annotations

import json

import pytest

from face_moment.diagnostics.calibration_thresholds import (
    ThresholdCandidate,
    calculate_threshold_profiles,
)


def _candidate(
    threshold: float,
    correct: int,
    false: int,
    missed: int,
    *attempt_ids: str,
) -> ThresholdCandidate:
    return ThresholdCandidate(
        threshold=threshold,
        correct=correct,
        false=false,
        missed=missed,
        contributing_attempt_ids=attempt_ids,
    )


@pytest.mark.parametrize(
    ("correct", "false", "missed"),
    ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
)
def test_rejects_positive_aggregate_without_contributing_attempt_locator(
    correct: int,
    false: int,
    missed: int,
) -> None:
    with pytest.raises(ValueError, match="positive aggregates require contributing Attempt locators"):
        calculate_threshold_profiles(
            pipeline_revision_id="sface-r1",
            candidates=(_candidate(0.4, correct, false, missed),),
            selected_attempt_count=1,
            applicable_attempt_count=1,
        )


@pytest.mark.parametrize(
    ("pipeline_revision_id", "candidates", "expected_profiles"),
    [
        (
            "sface-r1",
            (
                _candidate(0.3, 1, 0, 1, "sface-a"),
                _candidate(0.4, 2, 0, 2, "sface-a", "sface-b"),
                _candidate(0.5, 1, 1, 0, "sface-b"),
                _candidate(0.6, 1, 0, 1, "sface-a"),
            ),
            {
                "best_face_match": {
                    "threshold": 0.4,
                    "correct": 2,
                    "false": 0,
                    "missed": 2,
                    "precision": 1.0,
                    "recall": 0.5,
                    "f1": pytest.approx(2 / 3),
                    "contributing_attempt_ids": ["sface-a", "sface-b"],
                },
                "balance": {
                    "threshold": 0.6,
                    "correct": 1,
                    "false": 0,
                    "missed": 1,
                    "precision": 1.0,
                    "recall": 0.5,
                    "f1": pytest.approx(2 / 3),
                    "contributing_attempt_ids": ["sface-a"],
                },
                "minimum_missed_faces": {
                    "threshold": 0.5,
                    "correct": 1,
                    "false": 1,
                    "missed": 0,
                    "precision": 0.5,
                    "recall": 1.0,
                    "f1": pytest.approx(2 / 3),
                    "contributing_attempt_ids": ["sface-b"],
                },
            },
        ),
        (
            "buffalo-m-r1",
            (
                _candidate(0.3, 3, 1, 2, "buffalo-a", "buffalo-b"),
                _candidate(0.5, 2, 0, 1, "buffalo-a", "buffalo-b"),
                _candidate(0.7, 2, 0, 1, "buffalo-a", "buffalo-b"),
            ),
            {
                "best_face_match": {
                    "threshold": 0.7,
                    "correct": 2,
                    "false": 0,
                    "missed": 1,
                    "precision": 1.0,
                    "recall": pytest.approx(2 / 3),
                    "f1": pytest.approx(0.8),
                    "contributing_attempt_ids": ["buffalo-a", "buffalo-b"],
                },
                "balance": {
                    "threshold": 0.7,
                    "correct": 2,
                    "false": 0,
                    "missed": 1,
                    "precision": 1.0,
                    "recall": pytest.approx(2 / 3),
                    "f1": pytest.approx(0.8),
                    "contributing_attempt_ids": ["buffalo-a", "buffalo-b"],
                },
                "minimum_missed_faces": {
                    "threshold": 0.7,
                    "correct": 2,
                    "false": 0,
                    "missed": 1,
                    "precision": 1.0,
                    "recall": pytest.approx(2 / 3),
                    "f1": pytest.approx(0.8),
                    "contributing_attempt_ids": ["buffalo-a", "buffalo-b"],
                },
            },
        ),
    ],
)
def test_calculates_each_profile_with_exact_ranking_metrics_and_drill_down(
    pipeline_revision_id: str,
    candidates: tuple[ThresholdCandidate, ...],
    expected_profiles: dict[str, dict[str, object]],
) -> None:
    result = calculate_threshold_profiles(
        pipeline_revision_id=pipeline_revision_id,
        candidates=candidates,
        selected_attempt_count=3,
        applicable_attempt_count=2,
    )

    serialized = result.to_dict()

    assert serialized["pipeline_revision_id"] == pipeline_revision_id
    assert serialized["selected_attempt_count"] == 3
    assert serialized["applicable_attempt_count"] == 2
    for profile_name, expected in expected_profiles.items():
        proposal = serialized["profiles"][profile_name]["proposal"]
        assert proposal is not None
        assert proposal["annotated_sample_size"] == 2
        for key, value in expected.items():
            assert proposal[key] == value


@pytest.mark.parametrize(
    ("profile_name", "candidates", "expected_threshold"),
    [
        (
            "best_face_match",
            (
                _candidate(0.3, 1, 1, 0, "attempt-a"),
                _candidate(0.5, 1, 0, 2, "attempt-a"),
                _candidate(0.7, 2, 0, 3, "attempt-a", "attempt-b"),
                _candidate(0.9, 2, 0, 3, "attempt-a", "attempt-b"),
            ),
            0.9,
        ),
        (
            "balance",
            (
                _candidate(0.3, 1, 0, 2, "attempt-a"),
                _candidate(0.5, 2, 1, 0, "attempt-a", "attempt-b"),
                _candidate(0.7, 4, 0, 2, "attempt-a", "attempt-b"),
                _candidate(0.9, 2, 0, 1, "attempt-a", "attempt-b"),
            ),
            0.9,
        ),
        (
            "minimum_missed_faces",
            (
                _candidate(0.3, 2, 0, 1, "attempt-a", "attempt-b"),
                _candidate(0.5, 1, 1, 0, "attempt-a"),
                _candidate(0.7, 1, 0, 0, "attempt-a"),
                _candidate(0.9, 1, 0, 0, "attempt-a"),
            ),
            0.9,
        ),
    ],
)
@pytest.mark.parametrize("pipeline_revision_id", ("sface-r1", "buffalo-m-r1"))
def test_each_profile_honours_the_complete_accepted_tie_break_order(
    pipeline_revision_id: str,
    profile_name: str,
    candidates: tuple[ThresholdCandidate, ...],
    expected_threshold: float,
) -> None:
    result = calculate_threshold_profiles(
        pipeline_revision_id=pipeline_revision_id,
        candidates=candidates,
        selected_attempt_count=2,
        applicable_attempt_count=2,
    )

    proposal = result.to_dict()["profiles"][profile_name]["proposal"]

    assert proposal is not None
    assert proposal["threshold"] == expected_threshold


def test_all_undefined_candidates_serialize_unavailable_metrics_without_proposal() -> None:
    serving_state = {"settings_revision": 17, "face_threshold": 0.45}
    before = serving_state.copy()

    result = calculate_threshold_profiles(
        pipeline_revision_id="sface-r1",
        candidates=(
            _candidate(0.4, 0, 0, 0),
            _candidate(0.6, 0, 0, 0),
        ),
        selected_attempt_count=4,
        applicable_attempt_count=0,
    )

    serialized = result.to_dict()
    encoded = json.dumps(serialized, allow_nan=False)

    assert "NaN" not in encoded
    assert "Infinity" not in encoded
    assert serialized["selected_attempt_count"] == 4
    assert serialized["applicable_attempt_count"] == 0
    assert serving_state == before
    for profile in serialized["profiles"].values():
        assert profile == {
            "proposal": None,
            "warning": "insufficient_annotated_evidence",
            "metrics": {"precision": None, "recall": None, "f1": None},
        }

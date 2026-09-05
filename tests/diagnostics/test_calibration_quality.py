"""Fixed one-gate-at-a-time oracle for Calibration quality recommendations."""

from __future__ import annotations

from dataclasses import replace

import pytest

from face_moment.diagnostics.calibration_quality import (
    BrightnessRange,
    PoseMaximum,
    QualityEvaluation,
    QualityGate,
    QualityGateSettings,
    calculate_quality_recommendation,
)


def _settings() -> QualityGateSettings:
    return QualityGateSettings(
        face_match_threshold=0.5,
        face_size_minimum=40.0,
        detection_confidence_minimum=0.6,
        blur_maximum=6.0,
        brightness=BrightnessRange(minimum=20.0, maximum=220.0),
        pose=PoseMaximum(yaw=18.0, pitch=12.0, roll=10.0),
    )


def _evaluation(
    settings: QualityGateSettings,
    *,
    correct: int = 8,
    false: int = 3,
    missed: int = 2,
    kept: int = 11,
    rejected: int = 4,
) -> QualityEvaluation:
    return QualityEvaluation(
        pipeline_revision_id="sface-r1",
        settings=settings,
        annotated_sample_size=12,
        kept_detections=kept,
        rejected_detections=rejected,
        correct=correct,
        false=false,
        missed=missed,
    )


@pytest.mark.parametrize(
    ("gate", "proposed_settings", "expected_current", "expected_proposed"),
    [
        (
            QualityGate.FACE_SIZE,
            replace(_settings(), face_size_minimum=48.0),
            40.0,
            48.0,
        ),
        (
            QualityGate.DETECTION_CONFIDENCE,
            replace(_settings(), detection_confidence_minimum=0.7),
            0.6,
            0.7,
        ),
        (
            QualityGate.BLUR,
            replace(_settings(), blur_maximum=5.0),
            6.0,
            5.0,
        ),
        (
            QualityGate.BRIGHTNESS,
            replace(_settings(), brightness=BrightnessRange(minimum=40.0, maximum=200.0)),
            {"minimum": 20.0, "maximum": 220.0},
            {"minimum": 40.0, "maximum": 200.0},
        ),
        (
            QualityGate.POSE,
            replace(_settings(), pose=PoseMaximum(yaw=15.0, pitch=10.0, roll=8.0)),
            {"yaw": 18.0, "pitch": 12.0, "roll": 10.0},
            {"yaw": 15.0, "pitch": 10.0, "roll": 8.0},
        ),
    ],
)
def test_each_quality_gate_has_an_independent_explainable_recommendation(
    gate: QualityGate,
    proposed_settings: QualityGateSettings,
    expected_current: object,
    expected_proposed: object,
) -> None:
    current = _evaluation(_settings())
    proposed = _evaluation(
        proposed_settings,
        correct=7,
        false=1,
        missed=3,
        kept=9,
        rejected=6,
    )

    result = calculate_quality_recommendation(gate=gate, current=current, proposed=proposed)

    assert result.current_settings == current.settings
    assert result.proposed_settings == proposed.settings
    assert result.changed_gates == (gate,)
    assert result.current_value == expected_current
    assert result.proposed_value == expected_proposed
    assert result.annotated_sample_size == 12
    assert result.kept_detections == 9
    assert result.rejected_detections == 6
    assert result.expected_correct_change == -1
    assert result.expected_false_change == -2
    assert result.expected_missed_change == 1
    assert result.to_dict()["expected_changes"] == {"correct": -1, "false": -2, "missed": 1}


def test_blur_uses_the_lower_is_better_maximum_cutoff() -> None:
    settings = _settings()

    assert settings.keeps_blur_score(6.0)
    assert settings.keeps_blur_score(5.99)
    assert not settings.keeps_blur_score(6.01)


def test_gate_directions_cover_minimum_range_and_absolute_pose_limits() -> None:
    settings = _settings()

    assert settings.keeps_face_size(40.0)
    assert not settings.keeps_face_size(39.9)
    assert settings.keeps_detection_confidence(0.6)
    assert not settings.keeps_detection_confidence(0.59)
    assert settings.keeps_brightness(20.0)
    assert settings.keeps_brightness(220.0)
    assert not settings.keeps_brightness(220.1)
    assert settings.keeps_pose(yaw=-18.0, pitch=12.0, roll=-10.0)
    assert not settings.keeps_pose(yaw=18.1, pitch=0.0, roll=0.0)


def test_rejects_a_pair_that_changes_a_peer_gate_or_pipeline_or_sample() -> None:
    current = _evaluation(_settings())

    with pytest.raises(ValueError, match="exactly the named quality gate"):
        calculate_quality_recommendation(
            gate=QualityGate.FACE_SIZE,
            current=current,
            proposed=_evaluation(
                replace(
                    _settings(),
                    face_size_minimum=48.0,
                    detection_confidence_minimum=0.7,
                )
            ),
        )

    with pytest.raises(ValueError, match="same pipeline revision"):
        calculate_quality_recommendation(
            gate=QualityGate.FACE_SIZE,
            current=current,
            proposed=replace(
                _evaluation(replace(_settings(), face_size_minimum=48.0)),
                pipeline_revision_id="buffalo-m-r1",
            ),
        )

    with pytest.raises(ValueError, match="same annotated sample size"):
        calculate_quality_recommendation(
            gate=QualityGate.FACE_SIZE,
            current=current,
            proposed=replace(
                _evaluation(replace(_settings(), face_size_minimum=48.0)),
                annotated_sample_size=11,
            ),
        )

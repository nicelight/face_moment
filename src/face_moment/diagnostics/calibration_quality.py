"""Pure one-dimensional quality recommendations for completed Calibration evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math


class QualityGate(StrEnum):
    """The five accepted Calibration quality gates."""

    FACE_SIZE = "face_size"
    DETECTION_CONFIDENCE = "detection_confidence"
    BLUR = "blur"
    BRIGHTNESS = "brightness"
    POSE = "pose"


@dataclass(frozen=True, slots=True)
class BrightnessRange:
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        _require_finite(self.minimum, "brightness minimum")
        _require_finite(self.maximum, "brightness maximum")
        if self.minimum > self.maximum:
            raise ValueError("brightness minimum cannot exceed maximum")

    def to_dict(self) -> dict[str, float]:
        return {"minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True, slots=True)
class PoseMaximum:
    yaw: float
    pitch: float
    roll: float

    def __post_init__(self) -> None:
        for name, value in (("yaw", self.yaw), ("pitch", self.pitch), ("roll", self.roll)):
            _require_finite(value, f"pose {name}")
            if value < 0:
                raise ValueError(f"pose {name} maximum cannot be negative")

    def to_dict(self) -> dict[str, float]:
        return {"yaw": self.yaw, "pitch": self.pitch, "roll": self.roll}


@dataclass(frozen=True, slots=True)
class QualityGateSettings:
    """One immutable threshold and the five fixed quality-gate settings."""

    face_match_threshold: float
    face_size_minimum: float
    detection_confidence_minimum: float
    blur_maximum: float
    brightness: BrightnessRange
    pose: PoseMaximum

    def __post_init__(self) -> None:
        for name, value in (
            ("face match threshold", self.face_match_threshold),
            ("face size minimum", self.face_size_minimum),
            ("detection confidence minimum", self.detection_confidence_minimum),
            ("blur maximum", self.blur_maximum),
        ):
            _require_finite(value, name)

    def keeps_face_size(self, value: float) -> bool:
        return _finite_value(value, "face size") >= self.face_size_minimum

    def keeps_detection_confidence(self, value: float) -> bool:
        return _finite_value(value, "detection confidence") >= self.detection_confidence_minimum

    def keeps_blur_score(self, value: float) -> bool:
        """A lower blur score is better, so this is a maximum inclusive cutoff."""

        return _finite_value(value, "blur score") <= self.blur_maximum

    def keeps_brightness(self, value: float) -> bool:
        brightness = _finite_value(value, "brightness")
        return self.brightness.minimum <= brightness <= self.brightness.maximum

    def keeps_pose(self, *, yaw: float, pitch: float, roll: float) -> bool:
        return (
            abs(_finite_value(yaw, "pose yaw")) <= self.pose.yaw
            and abs(_finite_value(pitch, "pose pitch")) <= self.pose.pitch
            and abs(_finite_value(roll, "pose roll")) <= self.pose.roll
        )

    def value_for(self, gate: QualityGate) -> float | dict[str, float]:
        if gate is QualityGate.FACE_SIZE:
            return self.face_size_minimum
        if gate is QualityGate.DETECTION_CONFIDENCE:
            return self.detection_confidence_minimum
        if gate is QualityGate.BLUR:
            return self.blur_maximum
        if gate is QualityGate.BRIGHTNESS:
            return self.brightness.to_dict()
        return self.pose.to_dict()


@dataclass(frozen=True, slots=True)
class QualityEvaluation:
    """One retained candidate aggregate from one immutable native-pipeline run."""

    pipeline_revision_id: str
    settings: QualityGateSettings
    annotated_sample_size: int
    kept_detections: int
    rejected_detections: int
    correct: int
    false: int
    missed: int

    def __post_init__(self) -> None:
        if not self.pipeline_revision_id:
            raise ValueError("pipeline revision id is required")
        for name, value in (
            ("annotated sample size", self.annotated_sample_size),
            ("kept detections", self.kept_detections),
            ("rejected detections", self.rejected_detections),
            ("correct", self.correct),
            ("false", self.false),
            ("missed", self.missed),
        ):
            _require_count(value, name)


@dataclass(frozen=True, slots=True)
class QualityRecommendation:
    """One explainable comparison of retained candidates for exactly one gate."""

    gate: QualityGate
    pipeline_revision_id: str
    current_settings: QualityGateSettings
    proposed_settings: QualityGateSettings
    changed_gates: tuple[QualityGate, ...]
    current_value: float | dict[str, float]
    proposed_value: float | dict[str, float]
    annotated_sample_size: int
    kept_detections: int
    rejected_detections: int
    expected_correct_change: int
    expected_false_change: int
    expected_missed_change: int

    def to_dict(self) -> dict[str, object]:
        return {
            "gate": self.gate,
            "pipeline_revision_id": self.pipeline_revision_id,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "annotated_sample_size": self.annotated_sample_size,
            "kept_detections": self.kept_detections,
            "rejected_detections": self.rejected_detections,
            "expected_changes": {
                "correct": self.expected_correct_change,
                "false": self.expected_false_change,
                "missed": self.expected_missed_change,
            },
        }


def calculate_quality_recommendation(
    *,
    gate: QualityGate,
    current: QualityEvaluation,
    proposed: QualityEvaluation,
) -> QualityRecommendation:
    """Compare two retained candidates that differ at exactly one named gate.

    The caller supplies the deterministic candidate pair already calculated from
    immutable ground truth. This function neither ranks candidates nor derives
    outcomes, so no weighted or joint optimization is introduced.
    """

    if not isinstance(gate, QualityGate):
        raise ValueError("gate must be a QualityGate")
    if current.pipeline_revision_id != proposed.pipeline_revision_id:
        raise ValueError("quality candidates must use the same pipeline revision")
    if current.annotated_sample_size != proposed.annotated_sample_size:
        raise ValueError("quality candidates must use the same annotated sample size")
    changed_gates = _changed_gates(current.settings, proposed.settings)
    if changed_gates != (gate,):
        raise ValueError("quality candidates must change exactly the named quality gate")
    return QualityRecommendation(
        gate=gate,
        pipeline_revision_id=current.pipeline_revision_id,
        current_settings=current.settings,
        proposed_settings=proposed.settings,
        changed_gates=changed_gates,
        current_value=current.settings.value_for(gate),
        proposed_value=proposed.settings.value_for(gate),
        annotated_sample_size=current.annotated_sample_size,
        kept_detections=proposed.kept_detections,
        rejected_detections=proposed.rejected_detections,
        expected_correct_change=proposed.correct - current.correct,
        expected_false_change=proposed.false - current.false,
        expected_missed_change=proposed.missed - current.missed,
    )


def _changed_gates(
    current: QualityGateSettings, proposed: QualityGateSettings
) -> tuple[QualityGate, ...]:
    changes: list[QualityGate] = []
    if current.face_size_minimum != proposed.face_size_minimum:
        changes.append(QualityGate.FACE_SIZE)
    if current.detection_confidence_minimum != proposed.detection_confidence_minimum:
        changes.append(QualityGate.DETECTION_CONFIDENCE)
    if current.blur_maximum != proposed.blur_maximum:
        changes.append(QualityGate.BLUR)
    if current.brightness != proposed.brightness:
        changes.append(QualityGate.BRIGHTNESS)
    if current.pose != proposed.pose:
        changes.append(QualityGate.POSE)
    if current.face_match_threshold != proposed.face_match_threshold:
        raise ValueError("quality candidates must retain the face match threshold")
    return tuple(changes)


def _require_count(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_finite(value: object, name: str) -> None:
    _finite_value(value, name)


def _finite_value(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)

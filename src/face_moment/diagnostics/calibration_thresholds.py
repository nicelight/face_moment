"""Deterministic, diagnostics-owned threshold profiles for one Calibration result."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal, Sequence


ProfileName = Literal["best_face_match", "balance", "minimum_missed_faces"]

_PROFILE_NAMES: tuple[ProfileName, ...] = (
    "best_face_match",
    "balance",
    "minimum_missed_faces",
)


@dataclass(frozen=True, slots=True)
class ThresholdCandidate:
    """One retained finite threshold and its annotation-derived aggregate."""

    threshold: float
    correct: int
    false: int
    missed: int
    contributing_attempt_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ThresholdMetrics:
    precision: float | None
    recall: float | None
    f1: float | None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


@dataclass(frozen=True, slots=True)
class ThresholdProposal:
    threshold: float
    correct: int
    false: int
    missed: int
    metrics: ThresholdMetrics
    annotated_sample_size: int
    contributing_attempt_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "correct": self.correct,
            "false": self.false,
            "missed": self.missed,
            **self.metrics.to_dict(),
            "annotated_sample_size": self.annotated_sample_size,
            "contributing_attempt_ids": list(self.contributing_attempt_ids),
        }


@dataclass(frozen=True, slots=True)
class ThresholdProfile:
    proposal: ThresholdProposal | None
    warning: str | None
    metrics: ThresholdMetrics | None = None

    def to_dict(self) -> dict[str, object]:
        if self.proposal is not None:
            return {"proposal": self.proposal.to_dict(), "warning": self.warning}
        assert self.metrics is not None
        return {
            "proposal": None,
            "warning": self.warning,
            "metrics": self.metrics.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ThresholdProfileResult:
    """Profiles for exactly one native pipeline result from a completed run."""

    pipeline_revision_id: str
    selected_attempt_count: int
    applicable_attempt_count: int
    profiles: dict[ProfileName, ThresholdProfile]

    def to_dict(self) -> dict[str, object]:
        return {
            "pipeline_revision_id": self.pipeline_revision_id,
            "selected_attempt_count": self.selected_attempt_count,
            "applicable_attempt_count": self.applicable_attempt_count,
            "profiles": {name: self.profiles[name].to_dict() for name in _PROFILE_NAMES},
        }


def calculate_threshold_profiles(
    *,
    pipeline_revision_id: str,
    candidates: Sequence[ThresholdCandidate],
    selected_attempt_count: int,
    applicable_attempt_count: int,
) -> ThresholdProfileResult:
    """Apply the accepted profile rankings without coupling native pipelines.

    Candidate aggregates originate from the completed immutable run's persisted
    annotation projection. The calculation never inspects or changes serving
    settings; callers invoke it separately for SFace and Buffalo M results.
    """

    _validate_input(
        pipeline_revision_id=pipeline_revision_id,
        candidates=candidates,
        selected_attempt_count=selected_attempt_count,
        applicable_attempt_count=applicable_attempt_count,
    )
    candidate_metrics = tuple((candidate, _metrics(candidate)) for candidate in candidates)
    if all(metrics.f1 is None for _, metrics in candidate_metrics):
        unavailable = ThresholdProfile(
            proposal=None,
            warning="insufficient_annotated_evidence",
            metrics=ThresholdMetrics(precision=None, recall=None, f1=None),
        )
        return ThresholdProfileResult(
            pipeline_revision_id=pipeline_revision_id,
            selected_attempt_count=selected_attempt_count,
            applicable_attempt_count=applicable_attempt_count,
            profiles={name: unavailable for name in _PROFILE_NAMES},
        )

    by_candidate = {candidate: metrics for candidate, metrics in candidate_metrics}
    balance_candidates = tuple(
        candidate for candidate, metrics in candidate_metrics if metrics.f1 is not None
    )
    winners: dict[ProfileName, ThresholdCandidate] = {
        "best_face_match": min(candidates, key=lambda candidate: (candidate.false, -candidate.correct, -candidate.threshold)),
        "balance": min(
            balance_candidates,
            key=lambda candidate: (
                -_require_f1(by_candidate[candidate]),
                candidate.false,
                candidate.missed,
                -candidate.threshold,
            ),
        ),
        "minimum_missed_faces": min(
            candidates,
            key=lambda candidate: (candidate.missed, candidate.false, -candidate.threshold),
        ),
    }
    return ThresholdProfileResult(
        pipeline_revision_id=pipeline_revision_id,
        selected_attempt_count=selected_attempt_count,
        applicable_attempt_count=applicable_attempt_count,
        profiles={
            name: ThresholdProfile(
                proposal=_proposal(
                    winners[name],
                    by_candidate[winners[name]],
                    applicable_attempt_count,
                ),
                warning=None,
            )
            for name in _PROFILE_NAMES
        },
    )


def _proposal(
    candidate: ThresholdCandidate,
    metrics: ThresholdMetrics,
    applicable_attempt_count: int,
) -> ThresholdProposal:
    return ThresholdProposal(
        threshold=float(candidate.threshold),
        correct=candidate.correct,
        false=candidate.false,
        missed=candidate.missed,
        metrics=metrics,
        annotated_sample_size=applicable_attempt_count,
        contributing_attempt_ids=candidate.contributing_attempt_ids,
    )


def _metrics(candidate: ThresholdCandidate) -> ThresholdMetrics:
    precision_denominator = candidate.correct + candidate.false
    recall_denominator = candidate.correct + candidate.missed
    f1_denominator = 2 * candidate.correct + candidate.false + candidate.missed
    return ThresholdMetrics(
        precision=(candidate.correct / precision_denominator) if precision_denominator else None,
        recall=(candidate.correct / recall_denominator) if recall_denominator else None,
        f1=(2 * candidate.correct / f1_denominator) if f1_denominator else None,
    )


def _validate_input(
    *,
    pipeline_revision_id: str,
    candidates: Sequence[ThresholdCandidate],
    selected_attempt_count: int,
    applicable_attempt_count: int,
) -> None:
    if not pipeline_revision_id:
        raise ValueError("pipeline_revision_id is required")
    if not candidates:
        raise ValueError("at least one threshold candidate is required")
    if not _is_count(selected_attempt_count) or not _is_count(applicable_attempt_count):
        raise ValueError("sample counts must be non-negative integers")
    if applicable_attempt_count > selected_attempt_count:
        raise ValueError("applicable Attempt count cannot exceed selected Attempt count")
    thresholds: set[float] = set()
    for candidate in candidates:
        if not isinstance(candidate, ThresholdCandidate):
            raise ValueError("threshold candidates must be ThresholdCandidate values")
        if not isinstance(candidate.threshold, (int, float)) or isinstance(candidate.threshold, bool):
            raise ValueError("threshold must be a finite number")
        threshold = float(candidate.threshold)
        if not math.isfinite(threshold):
            raise ValueError("threshold must be a finite number")
        if threshold in thresholds:
            raise ValueError("threshold candidates must be unique")
        thresholds.add(threshold)
        if not all(_is_count(value) for value in (candidate.correct, candidate.false, candidate.missed)):
            raise ValueError("candidate counts must be non-negative integers")
        if not all(isinstance(attempt_id, str) and attempt_id for attempt_id in candidate.contributing_attempt_ids):
            raise ValueError("contributing Attempt locators must be non-empty strings")
        if len(set(candidate.contributing_attempt_ids)) != len(candidate.contributing_attempt_ids):
            raise ValueError("contributing Attempt locators must be unique")
        if (
            candidate.correct + candidate.false + candidate.missed > 0
            and not candidate.contributing_attempt_ids
        ):
            raise ValueError("positive aggregates require contributing Attempt locators")


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _require_f1(metrics: ThresholdMetrics) -> float:
    assert metrics.f1 is not None
    return metrics.f1

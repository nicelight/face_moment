"""Promo-to-diagnostics projection for realtime evidence."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session

from face_moment.diagnostics import DiagnosticEvidenceProvider
from face_moment.processing.realtime_search import RealtimeSearchResult
from face_moment.promo.attempt import PromoAttempt
from face_moment.promo.realtime_orchestration import RealtimeAttemptExecution

EvidenceSessionFactory = Callable[[], Session]


def project_realtime_evidence(
    attempt: PromoAttempt,
    *,
    execution: RealtimeAttemptExecution,
) -> tuple[dict[str, object], str, tuple[str, ...]]:
    """Project only immutable core/search/result observations for diagnostics."""

    manifest: dict[str, object] = {
        "schema_version": 1,
        "identity": {
            "attempt_id": str(attempt.id),
            "client_attempt_id": str(attempt.client_attempt_id),
            "trigger_source": attempt.trigger_source,
        },
        "client": {
            "trigger_source": attempt.trigger_source,
            "client_release": attempt.client_release,
            "detector_id": attempt.detector_id,
            "model_version": attempt.model_version,
            "jpeg_quality": attempt.jpeg_quality / 100,
            "camera_device_id": attempt.camera_device_id,
            "proposal_count": attempt.proposal_count,
            "reference_series_ready_at": _utc_iso(attempt.reference_series_ready_at),
            "local_detection_completed_ms": attempt.local_detection_completed_ms,
            "request_started_ms": attempt.request_started_ms,
        },
        "serving": {
            "release_id": attempt.release_id,
            "visit_date": None if attempt.visit_date is None else attempt.visit_date.isoformat(),
            "pipeline_revision_id": str(attempt.pipeline_revision_id),
            "pipeline_code": attempt.pipeline_code,
            "query_source": attempt.query_source,
            "settings_revision": attempt.settings_revision,
            "threshold": attempt.threshold,
            "quality_settings": dict(attempt.quality_settings),
        },
        "result": _result_manifest(attempt, execution),
        "artifacts": [],
    }
    if attempt.response_received_ms is not None:
        client = manifest["client"]
        assert isinstance(client, dict)
        client["response_received_ms"] = attempt.response_received_ms
    if execution.search_result is not None:
        manifest["detections"] = _detections_manifest(execution.search_result)
    if attempt.display_status in {"confirmed", "failed"}:
        display: dict[str, object] = {"status": attempt.display_status}
        if attempt.display_reported_at is not None:
            display["reported_at"] = _utc_iso(attempt.display_reported_at)
        if attempt.qr_fully_visible_elapsed_ms is not None:
            display["qr_fully_visible_elapsed_ms"] = attempt.qr_fully_visible_elapsed_ms
        manifest["display"] = display

    return manifest, _gap_reason(attempt, execution), _issue_tags(attempt, execution)


def attach_realtime_evidence(
    session_factory: EvidenceSessionFactory,
    *,
    attempt_id: uuid.UUID,
    ordinary_manifest: Mapping[str, object],
    gap_reason: str,
    issue_tags: Sequence[str],
) -> None:
    """Write one best-effort bundle after the Promo core transaction commits."""

    try:
        with session_factory() as session:
            outcome = DiagnosticEvidenceProvider(session).write(
                attempt_id=attempt_id,
                ordinary_manifest=ordinary_manifest,
                completeness="incomplete",
                gap_reason=gap_reason,
                issue_tags=issue_tags,
            )
            if outcome.accepted:
                session.commit()
    except Exception:
        return


def attach_realtime_evidence_patch(
    session_factory: EvidenceSessionFactory,
    *,
    attempt: PromoAttempt,
    ordinary_manifest: Mapping[str, object],
    issue_tags: Sequence[str],
) -> None:
    """Merge a response/display receipt or finalize without affecting Promo."""

    gap_reason = _gap_reason_for_patch(attempt)
    try:
        with session_factory() as session:
            provider = DiagnosticEvidenceProvider(session)
            if gap_reason is None:
                outcome = provider.finalize(
                    attempt_id=attempt.id,
                    ordinary_manifest=ordinary_manifest,
                    issue_tags=issue_tags,
                )
            else:
                outcome = provider.patch(
                    attempt_id=attempt.id,
                    ordinary_manifest=ordinary_manifest,
                    gap_reason=gap_reason,
                    issue_tags=issue_tags,
                )
            if outcome.accepted:
                session.commit()
    except Exception:
        return


def attach_realtime_evidence_patch_in_session(
    session: Session,
    *,
    attempt: PromoAttempt,
    ordinary_manifest: Mapping[str, object],
    issue_tags: Sequence[str],
) -> None:
    """Apply a best-effort patch after the caller committed Promo state."""

    gap_reason = _gap_reason_for_patch(attempt)
    try:
        provider = DiagnosticEvidenceProvider(session)
        if gap_reason is None:
            outcome = provider.finalize(
                attempt_id=attempt.id,
                ordinary_manifest=ordinary_manifest,
                issue_tags=issue_tags,
            )
        else:
            outcome = provider.patch(
                attempt_id=attempt.id,
                ordinary_manifest=ordinary_manifest,
                gap_reason=gap_reason,
                issue_tags=issue_tags,
            )
        if outcome.accepted:
            session.commit()
    except Exception:
        session.rollback()


def _result_manifest(
    attempt: PromoAttempt,
    execution: RealtimeAttemptExecution,
) -> dict[str, object]:
    outcome = (
        "internal_failure"
        if attempt.processing_status == "internal_failure"
        else attempt.domain_outcome
    )
    result: dict[str, object] = {"outcome": outcome}
    if (
        attempt.domain_outcome == "result"
        and execution.session is not None
        and execution.assembly is not None
    ):
        result.update(
            {
                "teaser_photo_ids": [
                    str(photo_id) for photo_id in execution.session.teasers
                ],
                "session_result_photo_ids": [
                    str(photo_id)
                    for photo_id in execution.assembly.session_result_photo_ids
                ],
                "n": execution.assembly.n,
            }
        )
    return result


def _detections_manifest(search_result: RealtimeSearchResult) -> list[dict[str, object]]:
    return [
        {
            "occurrence_index": detection.occurrence_index,
            "rank": detection.rank,
            "reference_quality_score": detection.reference_quality_score,
            "quality_gate_passed": detection.quality_gate_passed,
            "rejection_reason": detection.rejection_reason,
            "matches": [
                {
                    "photo_id": str(match.photo_id),
                    "cosine_similarity": match.cosine_similarity,
                    "phash64": match.phash64,
                }
                for match in detection.matches
            ],
        }
        for detection in search_result.detections
    ]


def _gap_reason(attempt: PromoAttempt, execution: RealtimeAttemptExecution) -> str:
    if attempt.processing_status == "internal_failure":
        return (
            "finalization_failed"
            if execution.search_result is not None
            else "search_evidence_missing"
        )
    if attempt.domain_outcome in {"busy", "deadline"}:
        return (
            "response_receipt_missing"
            if attempt.response_received_ms is None
            else "finalization_failed"
        )
    if attempt.response_received_ms is None:
        return "response_receipt_missing"
    if attempt.domain_outcome == "result" and attempt.display_status not in {
        "confirmed",
        "failed",
    }:
        return "display_event_missing"
    return "finalization_failed"


def _gap_reason_for_patch(attempt: PromoAttempt) -> str | None:
    if attempt.processing_status == "internal_failure":
        return "finalization_failed"
    if attempt.domain_outcome in {"busy", "deadline"}:
        return (
            "response_receipt_missing"
            if attempt.response_received_ms is None
            else None
        )
    if attempt.response_received_ms is None:
        return "response_receipt_missing"
    if attempt.domain_outcome == "result" and attempt.display_status not in {
        "confirmed",
        "failed",
    }:
        return "display_event_missing"
    return None


def _issue_tags(
    attempt: PromoAttempt,
    execution: RealtimeAttemptExecution,
) -> tuple[str, ...]:
    tags: set[str] = set()
    if attempt.domain_outcome is not None:
        tags.add(attempt.domain_outcome)
    if attempt.processing_status == "internal_failure":
        tags.add("internal_failure")
    if execution.search_result is None and attempt.processing_status == "internal_failure":
        tags.add("search_evidence_missing")
    if attempt.response_received_ms is None:
        tags.add("response_receipt_missing")
    if attempt.domain_outcome == "result" and attempt.display_status not in {
        "confirmed",
        "failed",
    }:
        tags.add("display_event_missing")
    if attempt.processing_status == "internal_failure" and execution.search_result is not None:
        tags.add("finalization_failed")
    return tuple(sorted(tags))


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("realtime evidence timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "attach_realtime_evidence",
    "attach_realtime_evidence_patch",
    "attach_realtime_evidence_patch_in_session",
    "project_realtime_evidence",
]

"""Diagnostics-owned role-scoped Attempt investigation application boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
import uuid

from sqlalchemy.orm import Session

from face_moment.diagnostics.evidence import (
    DiagnosticEvidence,
    DiagnosticEvidenceRepository,
    ORDINARY_REMOVED_GAP_REASON,
)
from face_moment.platform.auth.principals import StaffPrincipal, StaffRole
from face_moment.promo.attempt_queries import (
    AttemptInvestigationFilters,
    AttemptInvestigationProjection,
    query_attempts,
)


EvidenceAvailability = Literal["complete", "incomplete", "expired", "removed"]


class AttemptInvestigationAccessDeniedError(PermissionError):
    """The current authenticated principal cannot read diagnostic detail."""


class AttemptInvestigationNotFoundError(LookupError):
    """The promo owner has no core Attempt for the requested server identity."""


@dataclass(frozen=True, slots=True)
class DeveloperEvidenceProjection:
    schema_version: int | None
    completeness: str
    gap_reason: str | None
    ordinary_manifest: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class AttemptInvestigationView:
    core: AttemptInvestigationProjection
    evidence_availability: EvidenceAvailability
    issue_tags: tuple[str, ...]
    developer_evidence: DeveloperEvidenceProjection | None

    def server_durations_ms(self) -> tuple[tuple[str, int], ...]:
        timeline = self.core.timeline
        stages: list[tuple[str, int]] = []
        _append_duration(
            stages,
            "admission_to_slot",
            timeline.created_at,
            timeline.slot_decided_at,
        )
        _append_duration(
            stages,
            "slot_to_search",
            timeline.slot_decided_at,
            timeline.search_started_at,
        )
        _append_duration(
            stages,
            "search",
            timeline.search_started_at,
            timeline.search_finished_at,
        )
        return tuple(stages)


def read_attempts(
    database_session: Session,
    *,
    principal: StaffPrincipal,
    filters: AttemptInvestigationFilters,
) -> tuple[AttemptInvestigationView, ...]:
    """Authorize and compose bounded promo truth with diagnostics-owned evidence."""

    authorize_attempt_investigation(principal)
    repository = DiagnosticEvidenceRepository(database_session)
    return tuple(
        _project(principal, core, repository.get(core.attempt_id))
        for core in query_attempts(database_session, filters=filters)
    )


def read_attempt_detail(
    database_session: Session,
    *,
    principal: StaffPrincipal,
    attempt_id: uuid.UUID,
) -> AttemptInvestigationView:
    """Return one exact owner-provided core Attempt or a non-reconstructing miss."""

    authorize_attempt_investigation(principal)
    matches = query_attempts(
        database_session,
        filters=AttemptInvestigationFilters(attempt_id=attempt_id),
    )
    if not matches:
        raise AttemptInvestigationNotFoundError(str(attempt_id))
    core = matches[0]
    evidence = DiagnosticEvidenceRepository(database_session).get(core.attempt_id)
    return _project(principal, core, evidence)


def authorize_attempt_investigation(principal: StaffPrincipal) -> None:
    """Apply diagnostics-owned business authorization to the current principal."""

    if principal.role not in {StaffRole.OPERATOR, StaffRole.DEVELOPER}:
        raise AttemptInvestigationAccessDeniedError


def _project(
    principal: StaffPrincipal,
    core: AttemptInvestigationProjection,
    evidence: DiagnosticEvidence | None,
) -> AttemptInvestigationView:
    availability = _availability(evidence)
    evidence_tags = () if evidence is None else tuple(evidence.issue_tags)
    tags = tuple(sorted(set(core.timeline.issue_tags) | set(evidence_tags)))
    developer_evidence: DeveloperEvidenceProjection | None = None
    if principal.role is StaffRole.DEVELOPER and evidence is not None:
        readable_manifest = (
            evidence.ordinary_manifest if availability in {"complete", "incomplete"} else None
        )
        developer_evidence = DeveloperEvidenceProjection(
            schema_version=evidence.schema_version,
            completeness=evidence.completeness,
            gap_reason=evidence.gap_reason,
            ordinary_manifest=readable_manifest,
        )
    elif principal.role is StaffRole.DEVELOPER:
        developer_evidence = DeveloperEvidenceProjection(
            schema_version=None,
            completeness="incomplete",
            gap_reason="evidence_absent",
            ordinary_manifest=None,
        )
    return AttemptInvestigationView(
        core=core,
        evidence_availability=availability,
        issue_tags=tags,
        developer_evidence=developer_evidence,
    )


def _availability(evidence: DiagnosticEvidence | None) -> EvidenceAvailability:
    if evidence is None:
        return "incomplete"
    if (
        evidence.gap_reason == ORDINARY_REMOVED_GAP_REASON
        and evidence.ordinary_expired_at is None
        and evidence.ordinary_manifest is None
    ):
        return "removed"
    if evidence.ordinary_expired_at is not None:
        return "expired"
    if evidence.completeness == "complete" and evidence.ordinary_manifest is not None:
        return "complete"
    return "incomplete"


def _append_duration(
    target: list[tuple[str, int]],
    name: str,
    started: datetime | None,
    finished: datetime | None,
) -> None:
    if started is None or finished is None:
        return
    target.append((name, max(0, round((finished - started).total_seconds() * 1000))))


__all__ = [
    "AttemptInvestigationAccessDeniedError",
    "AttemptInvestigationNotFoundError",
    "AttemptInvestigationView",
    "DeveloperEvidenceProjection",
    "EvidenceAvailability",
    "authorize_attempt_investigation",
    "read_attempt_detail",
    "read_attempts",
]

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import re
from enum import StrEnum
from typing import Callable, Literal, cast
import uuid

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Uuid, select
from sqlalchemy.dialects.postgresql import JSONB, insert as postgresql_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import func

from face_moment.infrastructure.database import Base

CURRENT_SCHEMA_VERSION = 1
_MAX_JSON_BYTES = 1024 * 1024
_MAX_DETECTIONS = 5
_MAX_GAP_REASON_LENGTH = 255
_MAX_ISSUE_TAGS = 32
_MAX_ISSUE_TAG_LENGTH = 64
ORDINARY_REMOVED_GAP_REASON = "ordinary_removed"
_ISSUE_TAG_PATTERN = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")
_ORDINARY_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "identity",
        "client",
        "serving",
        "detections",
        "result",
        "display",
        "artifacts",
    }
)
_PROTECTED_ORDINARY_KEYS = frozenset(
    {
        "participant_name",
        "participant_names",
        "annotation",
        "annotations",
        "embedding",
        "embeddings",
        "credential",
        "credentials",
        "authorization",
        "auth",
        "auth_headers",
        "cookie",
        "cookies",
        "token",
        "tokens",
        "password",
        "session",
        "session_data",
        "session_payload",
        "request_body",
        "request_payload",
        "replay",
        "session_replay",
        "photo_original",
        "commercial_original",
        "original_bytes",
        "log",
        "logs",
        "log_payload",
        "selfie",
        "selfie_artifact",
    }
)
_PROMOTED_FORBIDDEN_KEYS = (
    _PROTECTED_ORDINARY_KEYS
    - {
        "participant_name",
        "participant_names",
        "annotation",
        "annotations",
    }
) | {"ordinary_manifest"}
_PROMOTED_FORBIDDEN_KEYS |= {
    "promo_screenshot",
    "screenshot",
    "technical_log",
    "technical_logs",
    "unselected_reference_series",
    "reference_series",
}
_PROMOTED_FORBIDDEN_BUNDLE_KEYS = (
    _ORDINARY_TOP_LEVEL_KEYS - {"schema_version"}
) | {"ordinary_manifest"}

CompletenessLiteral = Literal["incomplete", "complete"]


class Completeness(StrEnum):
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"


class DiagnosticEvidenceError(ValueError):
    """Raised by the repository for invalid or conflicting evidence state."""


class DiagnosticEvidenceNotFoundError(LookupError):
    """Raised when an operation requires an existing evidence row."""


class DiagnosticEvidence(Base):
    """Diagnostics-owned versioned evidence for one logical Promo Attempt."""

    __tablename__ = "diagnostic_evidence"
    __table_args__ = (
        CheckConstraint(
            "schema_version > 0",
            name="ck_diagnostic_evidence_schema_version_positive",
        ),
        CheckConstraint(
            "completeness IN ('incomplete', 'complete')",
            name="ck_diagnostic_evidence_completeness",
        ),
        CheckConstraint(
            "(completeness = 'incomplete' AND gap_reason IS NOT NULL "
            "AND length(btrim(gap_reason)) > 0) OR "
            "(completeness = 'complete' AND gap_reason IS NULL)",
            name="ck_diagnostic_evidence_gap_matches_completeness",
        ),
        CheckConstraint(
            "(completeness = 'incomplete' AND finalized_at IS NULL) OR "
            "(completeness = 'complete' AND finalized_at IS NOT NULL)",
            name="ck_diagnostic_evidence_finalized_matches_completeness",
        ),
        CheckConstraint(
            "(promoted_subset IS NULL AND promoted_at IS NULL) OR "
            "(promoted_subset IS NOT NULL AND promoted_at IS NOT NULL)",
            name="ck_diagnostic_evidence_promotion_pair",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=CURRENT_SCHEMA_VERSION, server_default="1"
    )
    completeness: Mapped[str] = mapped_column(String(length=16), nullable=False)
    gap_reason: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    issue_tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    ordinary_manifest: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )
    promoted_subset: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ordinary_expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


@dataclass(frozen=True, slots=True)
class EvidenceWriteOutcome:
    """Non-throwing result returned across the diagnostics application boundary."""

    accepted: bool
    attempt_id: uuid.UUID
    operation: str
    evidence_id: uuid.UUID | None = None
    completeness: CompletenessLiteral | None = None
    error_code: str | None = None

    @property
    def success(self) -> bool:
        return self.accepted


class DiagnosticEvidenceRepository:
    """Only-writer repository for the diagnostics-owned evidence table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(
        self,
        attempt_id: uuid.UUID,
        *,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        for_update: bool = False,
    ) -> DiagnosticEvidence | None:
        _validate_attempt_id(attempt_id)
        _validate_schema_version(schema_version)
        statement = select(DiagnosticEvidence).where(
            DiagnosticEvidence.attempt_id == attempt_id,
            DiagnosticEvidence.schema_version == schema_version,
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def require(
        self,
        attempt_id: uuid.UUID,
        *,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        for_update: bool = False,
    ) -> DiagnosticEvidence:
        evidence = self.get(
            attempt_id, schema_version=schema_version, for_update=for_update
        )
        if evidence is None:
            raise DiagnosticEvidenceNotFoundError(str(attempt_id))
        return evidence

    def write_bundle(
        self,
        *,
        attempt_id: uuid.UUID,
        ordinary_manifest: Mapping[str, object],
        completeness: CompletenessLiteral | str,
        gap_reason: str | None = None,
        issue_tags: Sequence[str] | None = None,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        now: datetime | None = None,
        create_if_missing: bool = True,
    ) -> DiagnosticEvidence:
        """Create or idempotently merge one ordinary versioned evidence row."""

        _validate_attempt_id(attempt_id)
        _validate_schema_version(schema_version)
        normalized_completeness = _validate_completeness(completeness)
        normalized_gap = _validate_gap_reason(
            gap_reason, completeness=normalized_completeness
        )
        normalized_manifest = _validate_ordinary_manifest(ordinary_manifest)
        normalized_tags = _normalise_issue_tags(
            issue_tags,
            completeness=normalized_completeness,
            gap_reason=normalized_gap,
        )
        timestamp = _utc(now)

        if create_if_missing:
            inserted = postgresql_insert(DiagnosticEvidence).values(
                id=uuid.uuid4(),
                attempt_id=attempt_id,
                schema_version=schema_version,
                completeness=normalized_completeness,
                gap_reason=normalized_gap,
                issue_tags=normalized_tags,
                ordinary_manifest=normalized_manifest,
                created_at=timestamp,
                updated_at=timestamp,
                finalized_at=(
                    timestamp
                    if normalized_completeness == Completeness.COMPLETE.value
                    else None
                ),
            )
            self._session.execute(
                inserted.on_conflict_do_nothing(
                    index_elements=["attempt_id", "schema_version"]
                )
            )
        evidence = self.require(
            attempt_id, schema_version=schema_version, for_update=True
        )

        if evidence.ordinary_expired_at is not None:
            raise DiagnosticEvidenceError("ordinary evidence has expired")
        if evidence.gap_reason == ORDINARY_REMOVED_GAP_REASON:
            raise DiagnosticEvidenceError("ordinary evidence has been removed")
        if evidence.completeness == Completeness.COMPLETE.value:
            return evidence

        merged_manifest = _merge_manifests(evidence.ordinary_manifest, normalized_manifest)
        if normalized_completeness == Completeness.COMPLETE.value:
            evidence.completeness = Completeness.COMPLETE.value
            evidence.gap_reason = None
            evidence.finalized_at = timestamp
        else:
            evidence.gap_reason = normalized_gap
        evidence.ordinary_manifest = merged_manifest
        evidence.issue_tags = sorted(set(evidence.issue_tags) | set(normalized_tags))
        _validate_issue_tags(evidence.issue_tags)
        evidence.updated_at = timestamp
        self._session.flush()
        self._session.refresh(evidence)
        return evidence

    def finalize(
        self,
        *,
        attempt_id: uuid.UUID,
        ordinary_manifest: Mapping[str, object] | None = None,
        issue_tags: Sequence[str] | None = None,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        now: datetime | None = None,
    ) -> DiagnosticEvidence:
        """Move an unexpired partial bundle to the terminal complete state."""

        _validate_attempt_id(attempt_id)
        _validate_schema_version(schema_version)
        timestamp = _utc(now)
        evidence = self.require(
            attempt_id, schema_version=schema_version, for_update=True
        )
        if evidence.ordinary_expired_at is not None:
            raise DiagnosticEvidenceError("ordinary evidence has expired")
        if evidence.gap_reason == ORDINARY_REMOVED_GAP_REASON:
            raise DiagnosticEvidenceError("ordinary evidence has been removed")
        normalized_manifest = (
            _validate_ordinary_manifest(ordinary_manifest)
            if ordinary_manifest is not None
            else None
        )
        if evidence.completeness == Completeness.COMPLETE.value:
            return evidence
        if evidence.ordinary_manifest is None and normalized_manifest is None:
            raise DiagnosticEvidenceError("complete evidence requires an ordinary manifest")

        if normalized_manifest is None:
            normalized_manifest = cast(dict[str, object], evidence.ordinary_manifest)
        merged_manifest = _merge_manifests(evidence.ordinary_manifest, normalized_manifest)
        evidence.ordinary_manifest = merged_manifest
        evidence.completeness = Completeness.COMPLETE.value
        evidence.gap_reason = None
        evidence.finalized_at = timestamp
        normalized_tags = _normalise_issue_tags(
            issue_tags,
            completeness=Completeness.COMPLETE.value,
            gap_reason=None,
        )
        evidence.issue_tags = sorted(set(evidence.issue_tags) | set(normalized_tags))
        _validate_issue_tags(evidence.issue_tags)
        evidence.updated_at = timestamp
        self._session.flush()
        self._session.refresh(evidence)
        return evidence

    def promote_subset(
        self,
        *,
        attempt_id: uuid.UUID,
        promoted_subset: Mapping[str, object],
        schema_version: int = CURRENT_SCHEMA_VERSION,
        now: datetime | None = None,
    ) -> DiagnosticEvidence:
        """Persist only the separately authorized curated promotion subset."""

        _validate_attempt_id(attempt_id)
        _validate_schema_version(schema_version)
        normalized_subset = _validate_promoted_subset(promoted_subset)
        timestamp = _utc(now)
        evidence = self.require(
            attempt_id, schema_version=schema_version, for_update=True
        )
        if evidence.promoted_subset is not None:
            if evidence.promoted_subset != normalized_subset:
                raise DiagnosticEvidenceError("promoted subset is already recorded")
            return evidence
        evidence.promoted_subset = normalized_subset
        evidence.promoted_at = timestamp
        evidence.updated_at = timestamp
        self._session.flush()
        self._session.refresh(evidence)
        return evidence

    def expire_ordinary(
        self,
        *,
        attempt_id: uuid.UUID,
        now: datetime | None = None,
        schema_version: int = CURRENT_SCHEMA_VERSION,
    ) -> bool:
        """Expire ordinary content and clear its manifest in one owner call."""

        if not self.mark_ordinary_expired(
            attempt_id=attempt_id,
            now=now,
            schema_version=schema_version,
        ):
            return False
        self.clear_expired_ordinary(
            attempt_id=attempt_id,
            schema_version=schema_version,
        )
        return True

    def remove_ordinary(
        self,
        *,
        attempt_id: uuid.UUID,
        now: datetime | None = None,
        schema_version: int = CURRENT_SCHEMA_VERSION,
    ) -> DiagnosticEvidence:
        """Irreversibly remove ordinary content while retaining owner provenance."""

        _validate_attempt_id(attempt_id)
        _validate_schema_version(schema_version)
        evidence = self.require(
            attempt_id, schema_version=schema_version, for_update=True
        )
        if evidence.gap_reason == ORDINARY_REMOVED_GAP_REASON:
            return evidence
        if evidence.ordinary_expired_at is not None:
            raise DiagnosticEvidenceError("ordinary evidence has expired")
        timestamp = _utc(now)
        evidence.ordinary_manifest = None
        evidence.completeness = Completeness.INCOMPLETE.value
        evidence.gap_reason = ORDINARY_REMOVED_GAP_REASON
        evidence.finalized_at = None
        evidence.updated_at = timestamp
        self._session.flush()
        self._session.refresh(evidence)
        return evidence

    def mark_ordinary_expired(
        self,
        *,
        attempt_id: uuid.UUID,
        now: datetime | None = None,
        schema_version: int = CURRENT_SCHEMA_VERSION,
    ) -> bool:
        """Make ordinary content inaccessible while retaining cleanup state."""

        _validate_attempt_id(attempt_id)
        _validate_schema_version(schema_version)
        evidence = self.get(
            attempt_id, schema_version=schema_version, for_update=True
        )
        if (
            evidence is None
            or evidence.ordinary_expired_at is not None
            or evidence.gap_reason == ORDINARY_REMOVED_GAP_REASON
        ):
            return False
        timestamp = _utc(now)
        evidence.ordinary_expired_at = timestamp
        evidence.updated_at = timestamp
        self._session.flush()
        self._session.refresh(evidence)
        return True

    def clear_expired_ordinary(
        self,
        *,
        attempt_id: uuid.UUID,
        schema_version: int = CURRENT_SCHEMA_VERSION,
    ) -> bool:
        """Clear retained ordinary cleanup state after object deletion."""

        _validate_attempt_id(attempt_id)
        _validate_schema_version(schema_version)
        evidence = self.get(
            attempt_id, schema_version=schema_version, for_update=True
        )
        if (
            evidence is None
            or evidence.ordinary_expired_at is None
            or evidence.ordinary_manifest is None
        ):
            return False
        evidence.ordinary_manifest = None
        evidence.updated_at = evidence.ordinary_expired_at
        self._session.flush()
        self._session.refresh(evidence)
        return True


class DiagnosticEvidenceProvider:
    """Best-effort diagnostics application boundary for promo consumers."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repository = DiagnosticEvidenceRepository(session)

    def write(
        self,
        *,
        attempt_id: uuid.UUID,
        ordinary_manifest: Mapping[str, object],
        completeness: CompletenessLiteral | str,
        gap_reason: str | None = None,
        issue_tags: Sequence[str] | None = None,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        now: datetime | None = None,
    ) -> EvidenceWriteOutcome:
        return self._run(
            "write",
            attempt_id,
            lambda: self._repository.write_bundle(
                attempt_id=attempt_id,
                ordinary_manifest=ordinary_manifest,
                completeness=completeness,
                gap_reason=gap_reason,
                issue_tags=issue_tags,
                schema_version=schema_version,
                now=now,
            ),
        )

    def patch(
        self,
        *,
        attempt_id: uuid.UUID,
        ordinary_manifest: Mapping[str, object],
        gap_reason: str,
        issue_tags: Sequence[str] | None = None,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        now: datetime | None = None,
    ) -> EvidenceWriteOutcome:
        """Merge a later receipt without creating an anchor if the base is absent."""

        return self._run(
            "patch",
            attempt_id,
            lambda: self._repository.write_bundle(
                attempt_id=attempt_id,
                ordinary_manifest=ordinary_manifest,
                completeness=Completeness.INCOMPLETE.value,
                gap_reason=gap_reason,
                issue_tags=issue_tags,
                schema_version=schema_version,
                now=now,
                create_if_missing=False,
            ),
        )

    def finalize(
        self,
        *,
        attempt_id: uuid.UUID,
        ordinary_manifest: Mapping[str, object] | None = None,
        issue_tags: Sequence[str] | None = None,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        now: datetime | None = None,
    ) -> EvidenceWriteOutcome:
        return self._run(
            "finalize",
            attempt_id,
            lambda: self._repository.finalize(
                attempt_id=attempt_id,
                ordinary_manifest=ordinary_manifest,
                issue_tags=issue_tags,
                schema_version=schema_version,
                now=now,
            ),
        )

    def promote_subset(
        self,
        *,
        attempt_id: uuid.UUID,
        promoted_subset: Mapping[str, object],
        schema_version: int = CURRENT_SCHEMA_VERSION,
        now: datetime | None = None,
    ) -> EvidenceWriteOutcome:
        return self._run(
            "promote_subset",
            attempt_id,
            lambda: self._repository.promote_subset(
                attempt_id=attempt_id,
                promoted_subset=promoted_subset,
                schema_version=schema_version,
                now=now,
            ),
        )

    def remove_ordinary(
        self,
        *,
        attempt_id: uuid.UUID,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        now: datetime | None = None,
    ) -> EvidenceWriteOutcome:
        """Run the internal diagnostics-owned explicit removal transition."""

        return self._run(
            "remove_ordinary",
            attempt_id,
            lambda: self._repository.remove_ordinary(
                attempt_id=attempt_id,
                schema_version=schema_version,
                now=now,
            ),
        )

    def _run(
        self,
        operation: str,
        attempt_id: uuid.UUID,
        action: Callable[[], DiagnosticEvidence],
    ) -> EvidenceWriteOutcome:
        try:
            result = action()
            return EvidenceWriteOutcome(
                accepted=True,
                attempt_id=attempt_id,
                operation=operation,
                evidence_id=result.id,
                completeness=cast(CompletenessLiteral, result.completeness),
            )
        except Exception as error:
            self._session.rollback()
            if isinstance(error, DiagnosticEvidenceNotFoundError):
                error_code = "evidence_not_found"
            elif isinstance(error, DiagnosticEvidenceError):
                error_code = "invalid_or_conflicting_evidence"
            elif isinstance(error, SQLAlchemyError):
                error_code = "evidence_store_unavailable"
            else:
                error_code = "evidence_write_failed"
            return EvidenceWriteOutcome(
                accepted=False,
                attempt_id=attempt_id,
                operation=operation,
                error_code=error_code,
            )


def _validate_attempt_id(attempt_id: uuid.UUID) -> None:
    if not isinstance(attempt_id, uuid.UUID):
        raise DiagnosticEvidenceError("attempt_id must be a UUID")


def _validate_schema_version(schema_version: int) -> None:
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != CURRENT_SCHEMA_VERSION
    ):
        raise DiagnosticEvidenceError("unsupported evidence schema version")


def _validate_completeness(completeness: CompletenessLiteral | str) -> CompletenessLiteral:
    if completeness not in {
        Completeness.INCOMPLETE.value,
        Completeness.COMPLETE.value,
    }:
        raise DiagnosticEvidenceError("completeness must be incomplete or complete")
    return cast(CompletenessLiteral, completeness)


def _validate_gap_reason(
    gap_reason: str | None, *, completeness: CompletenessLiteral
) -> str | None:
    if completeness == Completeness.COMPLETE.value:
        if gap_reason is not None:
            raise DiagnosticEvidenceError("complete evidence cannot have a gap")
        return None
    if (
        not isinstance(gap_reason, str)
        or not gap_reason.strip()
        or len(gap_reason) > _MAX_GAP_REASON_LENGTH
    ):
        raise DiagnosticEvidenceError(
            "incomplete evidence requires a bounded non-empty gap"
        )
    return gap_reason


def _normalise_issue_tags(
    issue_tags: Sequence[str] | None,
    *,
    completeness: CompletenessLiteral,
    gap_reason: str | None,
) -> list[str]:
    values = list(issue_tags) if issue_tags is not None else []
    _validate_issue_tags(values)
    derived = {
        "evidence_complete"
        if completeness == Completeness.COMPLETE.value
        else "evidence_incomplete"
    }
    if completeness == Completeness.INCOMPLETE.value and gap_reason is not None:
        normalized_gap = gap_reason.casefold()
        derived.add(
            normalized_gap
            if _ISSUE_TAG_PATTERN.fullmatch(normalized_gap) is not None
            else "gap_observed"
        )
    result = sorted(set(values) | derived)
    _validate_issue_tags(result)
    return result


def _validate_issue_tags(issue_tags: Sequence[str]) -> None:
    if len(issue_tags) > _MAX_ISSUE_TAGS:
        raise DiagnosticEvidenceError("too many issue tags")
    if len(set(issue_tags)) != len(issue_tags):
        raise DiagnosticEvidenceError("issue tags must be unique")
    for tag in issue_tags:
        if (
            not isinstance(tag, str)
            or len(tag) > _MAX_ISSUE_TAG_LENGTH
            or _ISSUE_TAG_PATTERN.fullmatch(tag) is None
        ):
            raise DiagnosticEvidenceError("issue tags must be lowercase snake-case")


def _validate_ordinary_manifest(
    ordinary_manifest: Mapping[str, object],
) -> dict[str, object]:
    normalized = _normalise_json_object(ordinary_manifest, "ordinary manifest")
    unexpected = set(normalized) - _ORDINARY_TOP_LEVEL_KEYS
    if unexpected:
        raise DiagnosticEvidenceError("ordinary manifest has an unsupported section")
    if normalized.get("schema_version") != CURRENT_SCHEMA_VERSION:
        raise DiagnosticEvidenceError("ordinary manifest schema_version must be 1")
    detections = normalized.get("detections")
    if detections is not None and (
        not isinstance(detections, list) or len(detections) > _MAX_DETECTIONS
    ):
        raise DiagnosticEvidenceError(
            "ordinary manifest detections must contain at most five observations"
        )
    _reject_keys(normalized, _PROTECTED_ORDINARY_KEYS, "ordinary manifest")
    return normalized


def _validate_promoted_subset(
    promoted_subset: Mapping[str, object],
) -> dict[str, object]:
    normalized = _normalise_json_object(promoted_subset, "promoted subset")
    _reject_keys(normalized, _PROMOTED_FORBIDDEN_KEYS, "promoted subset")
    if any(
        key.casefold() in _PROMOTED_FORBIDDEN_BUNDLE_KEYS for key in normalized
    ):
        raise DiagnosticEvidenceError("promoted subset cannot retain the ordinary bundle")
    return normalized


def _normalise_json_object(value: Mapping[str, object], label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise DiagnosticEvidenceError(f"{label} must be a JSON object")
    _validate_json_value(value, label)
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise DiagnosticEvidenceError(f"{label} must contain JSON values") from error
    if len(encoded.encode("utf-8")) > _MAX_JSON_BYTES:
        raise DiagnosticEvidenceError(f"{label} exceeds the 1 MiB bound")
    normalized = json.loads(encoded)
    if not isinstance(normalized, dict):
        raise DiagnosticEvidenceError(f"{label} must be a JSON object")
    return cast(dict[str, object], normalized)


def _validate_json_value(value: object, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DiagnosticEvidenceError(f"{path} contains a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise DiagnosticEvidenceError(f"{path} has a non-string key")
            _validate_json_value(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_json_value(child, f"{path}[{index}]")
        return
    raise DiagnosticEvidenceError(f"{path} contains a non-JSON value")


def _reject_keys(value: object, forbidden: frozenset[str], label: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and key.casefold() in forbidden:
                raise DiagnosticEvidenceError(f"{label} contains a protected field")
            _reject_keys(child, forbidden, label)
    elif isinstance(value, list):
        for child in value:
            _reject_keys(child, forbidden, label)


def _merge_manifests(
    existing: dict[str, object] | None,
    incoming: dict[str, object],
) -> dict[str, object]:
    merged: dict[str, object] = dict(existing or {})
    for key, value in incoming.items():
        prior = merged.get(key)
        if isinstance(prior, dict) and isinstance(value, dict):
            merged[key] = _merge_json_objects(prior, value)
        else:
            merged[key] = value
    return _validate_ordinary_manifest(merged)


def _merge_json_objects(
    existing: Mapping[str, object], incoming: Mapping[str, object]
) -> dict[str, object]:
    merged: dict[str, object] = dict(existing)
    for key, value in incoming.items():
        prior = merged.get(key)
        if isinstance(prior, dict) and isinstance(value, dict):
            merged[key] = _merge_json_objects(prior, value)
        else:
            merged[key] = value
    return merged


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise DiagnosticEvidenceError("evidence timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)

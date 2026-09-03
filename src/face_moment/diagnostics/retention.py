from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
import uuid

from sqlalchemy.orm import Session

from face_moment.diagnostics.evidence import DiagnosticEvidenceRepository
from face_moment.diagnostics.server_events import ServerEventRepository


class RetentionObjectStore(Protocol):
    def delete(self, *, key: str) -> None:
        """Delete one diagnostics-owned private object idempotently."""


@dataclass(frozen=True, slots=True)
class DiagnosticRetentionResult:
    """Diagnostics-owned confirmation returned to Promo."""

    eligible_attempt_ids: tuple[uuid.UUID, ...]
    ordinary_evidence_expired: int
    private_artifacts_deleted: int
    promoted_subsets_preserved: int


class DiagnosticRetentionProvider:
    """Expire only diagnostics-owned ordinary evidence."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repository = DiagnosticEvidenceRepository(session)

    def expire_server_events(self, *, cutoff: datetime) -> int:
        """Delete diagnostics-owned event rows and confirm the new count."""

        deleted = ServerEventRepository(self._session).delete_before(cutoff)
        self._session.commit()
        return deleted

    def expire(
        self,
        attempt_ids: Iterable[uuid.UUID],
        *,
        cutoff: datetime,
        now: datetime | None = None,
        object_store: RetentionObjectStore | None = None,
    ) -> DiagnosticRetentionResult:
        """Make supplied ordinary evidence inaccessible and confirm ownership.

        Promo chooses the expired core Attempt IDs. A missing diagnostics row is
        deliberately confirmed as a no-op so Promo can still delete its own
        old Attempt.
        """

        cutoff_utc = _utc(cutoff)
        _ = cutoff_utc  # The candidate cutoff is enforced by Promo's owner.
        timestamp = _utc(now)
        unique_ids = _unique_attempt_ids(attempt_ids)
        eligible: list[uuid.UUID] = []
        evidence_expired = 0
        private_deleted = 0
        promoted_preserved = 0

        for attempt_id in unique_ids:
            evidence = self._repository.get(attempt_id, for_update=True)
            if evidence is None:
                eligible.append(attempt_id)
                continue

            promoted_artifact_keys = _promoted_private_artifact_keys(
                evidence.promoted_subset
            )
            artifact_keys = tuple(
                key
                for key in _private_artifact_keys(evidence.ordinary_manifest)
                if key not in promoted_artifact_keys
            )
            if evidence.promoted_subset is not None:
                promoted_preserved += 1
            if evidence.ordinary_expired_at is None:
                if self._repository.mark_ordinary_expired(
                    attempt_id=attempt_id,
                    now=timestamp,
                ):
                    # Commit the owner-local access boundary before touching
                    # the private object store. The manifest remains as
                    # retry state, but ordinary reads are expired already.
                    self._session.commit()
                    evidence_expired += 1

            if artifact_keys and object_store is None:
                raise RuntimeError("private artifact deletion unavailable")

            if object_store is not None:
                for key in artifact_keys:
                    object_store.delete(key=key)
                    private_deleted += 1

            # The manifest is the owner-local retry record. It is cleared only
            # after every listed private object deletion has returned success.
            self._repository.clear_expired_ordinary(attempt_id=attempt_id)
            self._session.commit()
            eligible.append(attempt_id)

        return DiagnosticRetentionResult(
            eligible_attempt_ids=tuple(eligible),
            ordinary_evidence_expired=evidence_expired,
            private_artifacts_deleted=private_deleted,
            promoted_subsets_preserved=promoted_preserved,
        )


def expire_diagnostic_attempts(
    session: Session,
    attempt_ids: Iterable[uuid.UUID],
    *,
    cutoff: datetime,
    now: datetime | None = None,
    object_store: RetentionObjectStore | None = None,
) -> DiagnosticRetentionResult:
    """Function-form diagnostics retention boundary for the Promo caller."""

    return DiagnosticRetentionProvider(session).expire(
        attempt_ids,
        cutoff=cutoff,
        now=now,
        object_store=object_store,
    )


def _unique_attempt_ids(attempt_ids: Iterable[uuid.UUID]) -> tuple[uuid.UUID, ...]:
    values: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for attempt_id in attempt_ids:
        if not isinstance(attempt_id, uuid.UUID):
            raise ValueError("retention attempt IDs must be UUIDs")
        if attempt_id not in seen:
            seen.add(attempt_id)
            values.append(attempt_id)
    return tuple(values)


def _private_artifact_keys(manifest: Mapping[str, object] | None) -> tuple[str, ...]:
    if manifest is None:
        return ()
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Sequence) or isinstance(artifacts, (str, bytes)):
        return ()
    keys: list[str] = []
    for descriptor in artifacts:
        if not isinstance(descriptor, Mapping):
            continue
        candidate = descriptor.get("object_key", descriptor.get("key"))
        if isinstance(candidate, str) and candidate:
            keys.append(candidate)
    return tuple(keys)


def _promoted_private_artifact_keys(
    promoted_subset: Mapping[str, object] | None,
) -> frozenset[str]:
    if promoted_subset is None:
        return frozenset()
    media_refs = promoted_subset.get("media_refs")
    if not isinstance(media_refs, Sequence) or isinstance(media_refs, (str, bytes)):
        return frozenset()
    return frozenset(
        reference
        for reference in media_refs
        if isinstance(reference, str) and reference
    )


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("retention timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


__all__ = [
    "DiagnosticRetentionProvider",
    "DiagnosticRetentionResult",
    "RetentionObjectStore",
    "expire_diagnostic_attempts",
]

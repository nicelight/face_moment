"""Diagnostics-owned normalized ground-truth annotation boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast
import uuid

from sqlalchemy import CheckConstraint, Index, Integer, String, Uuid, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.diagnostics.evidence import (
    DiagnosticEvidence,
    DiagnosticEvidenceRepository,
    ORDINARY_REMOVED_GAP_REASON,
)
from face_moment.infrastructure.database import Base


TargetKind = Literal["detection", "person"]
AnnotationOutcome = Literal["correct", "false", "missed"]
_ATTEMPT_TRANSACTION_BARRIER_NAMESPACE = 99_099


class GroundTruthAnnotationError(ValueError):
    """The requested annotation operation violates the normalized contract."""


class GroundTruthAnnotationNotFoundError(LookupError):
    """The requested Attempt or annotation does not exist."""


class GroundTruthAnnotationConflictError(GroundTruthAnnotationError):
    """The detection target already has an annotation."""


class GroundTruthAnnotation(Base):
    """One diagnostics-owned annotation linked logically to a Promo Attempt."""

    __tablename__ = "ground_truth_annotations"
    __table_args__ = (
        CheckConstraint(
            "target_kind IN ('detection', 'person')",
            name="ck_ground_truth_annotations_target_kind",
        ),
        CheckConstraint(
            "outcome IN ('correct', 'false', 'missed')",
            name="ck_ground_truth_annotations_outcome",
        ),
        CheckConstraint(
            r"char_length(btrim(participant_name, "
            r"U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020"
            r"\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006"
            r"\2007\2008\2009\200A\2028\2029\202F\205F\3000')) "
            "BETWEEN 1 AND 200",
            name="ck_ground_truth_annotations_participant_name",
        ),
        CheckConstraint(
            "(target_kind = 'detection' AND detection_occurrence_index IS NOT NULL "
            "AND detection_occurrence_index >= 0 AND outcome IN ('correct', 'false')) OR "
            "(target_kind = 'person' AND detection_occurrence_index IS NULL "
            "AND outcome = 'missed')",
            name="ck_ground_truth_annotations_target_outcome_shape",
        ),
        Index(
            "uq_ground_truth_annotations_detection_target",
            "attempt_id",
            "detection_occurrence_index",
            unique=True,
            postgresql_where=text("target_kind = 'detection'"),
        ),
    )

    annotation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(length=16), nullable=False)
    detection_occurrence_index: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    participant_name: Mapped[str] = mapped_column(String(length=200), nullable=False)
    outcome: Mapped[str] = mapped_column(String(length=16), nullable=False)


@dataclass(frozen=True, slots=True)
class GroundTruthAnnotationSnapshot:
    annotation_id: uuid.UUID
    attempt_id: uuid.UUID
    target_kind: TargetKind
    detection_occurrence_index: int | None
    participant_name: str
    outcome: AnnotationOutcome


@dataclass(frozen=True, slots=True)
class GroundTruthCalculationSnapshot:
    attempt_id: uuid.UUID
    annotations: tuple[GroundTruthAnnotationSnapshot, ...]


class GroundTruthAnnotationRepository:
    """Only-writer repository for normalized diagnostics annotation rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def acquire_attempt_transaction_barrier(self, attempt_id: uuid.UUID) -> None:
        """Serialize annotation creation and retention for one Attempt."""

        self._session.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(CAST(:attempt_id AS text), :namespace)"
                ")"
            ),
            {
                "attempt_id": str(_require_uuid(attempt_id, "attempt_id")),
                "namespace": _ATTEMPT_TRANSACTION_BARRIER_NAMESPACE,
            },
        )

    def get(
        self,
        *,
        attempt_id: uuid.UUID,
        annotation_id: uuid.UUID,
        for_update: bool = False,
    ) -> GroundTruthAnnotation | None:
        statement = select(GroundTruthAnnotation).where(
            GroundTruthAnnotation.attempt_id == attempt_id,
            GroundTruthAnnotation.annotation_id == annotation_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def require(
        self,
        *,
        attempt_id: uuid.UUID,
        annotation_id: uuid.UUID,
        for_update: bool = False,
    ) -> GroundTruthAnnotation:
        annotation = self.get(
            attempt_id=attempt_id,
            annotation_id=annotation_id,
            for_update=for_update,
        )
        if annotation is None:
            raise GroundTruthAnnotationNotFoundError(str(annotation_id))
        return annotation

    def list_for_attempt(
        self, attempt_id: uuid.UUID
    ) -> tuple[GroundTruthAnnotation, ...]:
        return tuple(
            self._session.scalars(
                select(GroundTruthAnnotation)
                .where(GroundTruthAnnotation.attempt_id == attempt_id)
                .order_by(GroundTruthAnnotation.annotation_id)
            )
        )

    def create(
        self,
        *,
        attempt_id: uuid.UUID,
        target_kind: TargetKind,
        detection_occurrence_index: int | None,
        participant_name: str,
        outcome: AnnotationOutcome,
    ) -> GroundTruthAnnotation:
        annotation = GroundTruthAnnotation(
            annotation_id=uuid.uuid4(),
            attempt_id=attempt_id,
            target_kind=target_kind,
            detection_occurrence_index=detection_occurrence_index,
            participant_name=participant_name,
            outcome=outcome,
        )
        try:
            with self._session.begin_nested():
                self._session.add(annotation)
                self._session.flush()
        except IntegrityError as error:
            raise GroundTruthAnnotationConflictError(
                "detection target already has an annotation"
            ) from error
        self._session.refresh(annotation)
        return annotation

    def correct(
        self,
        annotation: GroundTruthAnnotation,
        *,
        participant_name: str,
        outcome: AnnotationOutcome,
    ) -> GroundTruthAnnotation:
        annotation.participant_name = participant_name
        annotation.outcome = outcome
        self._session.flush()
        self._session.refresh(annotation)
        return annotation

    def remove(self, annotation: GroundTruthAnnotation) -> None:
        self._session.delete(annotation)
        self._session.flush()

    def delete_for_attempt(self, attempt_id: uuid.UUID) -> int:
        """Delete every ordinary annotation owned for one Attempt."""

        result = self._session.execute(
            delete(GroundTruthAnnotation).where(
                GroundTruthAnnotation.attempt_id
                == _require_uuid(attempt_id, "attempt_id")
            )
        )
        return int(result.rowcount or 0)


class GroundTruthAnnotationProvider:
    """Validated application boundary for annotation mutations and snapshots."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repository = GroundTruthAnnotationRepository(session)
        self._evidence_repository = DiagnosticEvidenceRepository(session)

    def create(
        self,
        *,
        attempt_id: uuid.UUID,
        target_kind: TargetKind | str,
        detection_occurrence_index: int | None,
        participant_name: str,
        outcome: AnnotationOutcome | str,
    ) -> GroundTruthAnnotationSnapshot:
        self._repository.acquire_attempt_transaction_barrier(attempt_id)
        self._require_attempt(attempt_id)
        evidence = self._require_writable_evidence(attempt_id)
        normalized_target, normalized_index, normalized_name, normalized_outcome = (
            _validate_annotation_values(
                target_kind=target_kind,
                detection_occurrence_index=detection_occurrence_index,
                participant_name=participant_name,
                outcome=outcome,
            )
        )
        if normalized_target == "detection":
            _require_detection_occurrence(evidence, cast(int, normalized_index))
        annotation = self._repository.create(
            attempt_id=attempt_id,
            target_kind=normalized_target,
            detection_occurrence_index=normalized_index,
            participant_name=normalized_name,
            outcome=normalized_outcome,
        )
        return _snapshot(annotation)

    def correct(
        self,
        *,
        attempt_id: uuid.UUID,
        annotation_id: uuid.UUID,
        participant_name: str,
        outcome: AnnotationOutcome | str,
    ) -> GroundTruthAnnotationSnapshot:
        self._require_attempt(attempt_id)
        evidence = self._require_writable_evidence(attempt_id)
        annotation = self._repository.require(
            attempt_id=attempt_id,
            annotation_id=_require_uuid(annotation_id, "annotation_id"),
            for_update=True,
        )
        _, _, normalized_name, normalized_outcome = _validate_annotation_values(
            target_kind=annotation.target_kind,
            detection_occurrence_index=annotation.detection_occurrence_index,
            participant_name=participant_name,
            outcome=outcome,
        )
        if annotation.target_kind == "detection":
            _require_detection_occurrence(
                evidence, cast(int, annotation.detection_occurrence_index)
            )
        corrected = self._repository.correct(
            annotation,
            participant_name=normalized_name,
            outcome=normalized_outcome,
        )
        return _snapshot(corrected)

    def remove(
        self, *, attempt_id: uuid.UUID, annotation_id: uuid.UUID
    ) -> None:
        self._require_attempt(attempt_id)
        self._require_writable_evidence(attempt_id)
        annotation = self._repository.require(
            attempt_id=attempt_id,
            annotation_id=_require_uuid(annotation_id, "annotation_id"),
            for_update=True,
        )
        self._repository.remove(annotation)

    def list(self, *, attempt_id: uuid.UUID) -> tuple[GroundTruthAnnotationSnapshot, ...]:
        self._require_attempt(attempt_id)
        return tuple(_snapshot(row) for row in self._repository.list_for_attempt(attempt_id))

    def calculation_snapshot(
        self, *, attempt_id: uuid.UUID
    ) -> GroundTruthCalculationSnapshot:
        return GroundTruthCalculationSnapshot(
            attempt_id=_require_uuid(attempt_id, "attempt_id"),
            annotations=self.list(attempt_id=attempt_id),
        )

    def _require_attempt(self, attempt_id: uuid.UUID) -> None:
        from face_moment.promo.attempt_queries import (
            AttemptInvestigationFilters,
            query_attempts,
        )

        attempt_id = _require_uuid(attempt_id, "attempt_id")
        matches = query_attempts(
            self._session,
            filters=AttemptInvestigationFilters(attempt_id=attempt_id),
        )
        if not matches:
            raise GroundTruthAnnotationNotFoundError(str(attempt_id))

    def _require_writable_evidence(
        self, attempt_id: uuid.UUID
    ) -> DiagnosticEvidence | None:
        evidence = self._evidence_repository.get(attempt_id, for_update=True)
        if evidence is not None and evidence.ordinary_expired_at is not None:
            raise GroundTruthAnnotationError("ordinary evidence has expired")
        if evidence is not None and evidence.gap_reason == ORDINARY_REMOVED_GAP_REASON:
            raise GroundTruthAnnotationError("ordinary evidence has been removed")
        return evidence


def _validate_annotation_values(
    *,
    target_kind: TargetKind | str,
    detection_occurrence_index: int | None,
    participant_name: str,
    outcome: AnnotationOutcome | str,
) -> tuple[TargetKind, int | None, str, AnnotationOutcome]:
    if target_kind not in {"detection", "person"}:
        raise GroundTruthAnnotationError("target_kind must be detection or person")
    if not isinstance(participant_name, str):
        raise GroundTruthAnnotationError("participant_name must be text")
    normalized_name = participant_name.strip()
    if not normalized_name or len(normalized_name) > 200:
        raise GroundTruthAnnotationError(
            "participant_name must contain 1 to 200 characters"
        )
    if target_kind == "detection":
        if (
            not isinstance(detection_occurrence_index, int)
            or isinstance(detection_occurrence_index, bool)
            or detection_occurrence_index < 0
        ):
            raise GroundTruthAnnotationError(
                "detection target requires a non-negative occurrence index"
            )
        if outcome not in {"correct", "false"}:
            raise GroundTruthAnnotationError(
                "detection outcome must be correct or false"
            )
    else:
        if detection_occurrence_index is not None:
            raise GroundTruthAnnotationError("person target cannot have an occurrence index")
        if outcome != "missed":
            raise GroundTruthAnnotationError("person outcome must be missed")
    return (
        cast(TargetKind, target_kind),
        detection_occurrence_index,
        normalized_name,
        cast(AnnotationOutcome, outcome),
    )


def _require_detection_occurrence(
    evidence: DiagnosticEvidence | None, occurrence_index: int
) -> None:
    manifest = None if evidence is None else evidence.ordinary_manifest
    detections = None if manifest is None else manifest.get("detections")
    if not isinstance(detections, list) or not any(
        isinstance(item, dict)
        and item.get("occurrence_index") == occurrence_index
        and not isinstance(item.get("occurrence_index"), bool)
        for item in detections
    ):
        raise GroundTruthAnnotationError("detection occurrence does not exist")


def _require_uuid(value: uuid.UUID, field_name: str) -> uuid.UUID:
    if not isinstance(value, uuid.UUID):
        raise GroundTruthAnnotationError(f"{field_name} must be a UUID")
    return value


def _snapshot(annotation: GroundTruthAnnotation) -> GroundTruthAnnotationSnapshot:
    return GroundTruthAnnotationSnapshot(
        annotation_id=annotation.annotation_id,
        attempt_id=annotation.attempt_id,
        target_kind=cast(TargetKind, annotation.target_kind),
        detection_occurrence_index=annotation.detection_occurrence_index,
        participant_name=annotation.participant_name,
        outcome=cast(AnnotationOutcome, annotation.outcome),
    )


__all__ = [
    "AnnotationOutcome",
    "GroundTruthAnnotation",
    "GroundTruthAnnotationConflictError",
    "GroundTruthAnnotationError",
    "GroundTruthAnnotationNotFoundError",
    "GroundTruthAnnotationProvider",
    "GroundTruthAnnotationRepository",
    "GroundTruthAnnotationSnapshot",
    "GroundTruthCalculationSnapshot",
    "TargetKind",
]

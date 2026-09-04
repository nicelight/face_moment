"""Diagnostics-owned immutable Calibration run persistence and comparison."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import math
from typing import TYPE_CHECKING, Mapping, Sequence
import uuid

from sqlalchemy import CheckConstraint, DateTime, String, Uuid, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import func

from face_moment.infrastructure.database import Base
from face_moment.processing.offline_calibration import (
    CalibrationDatasetUnavailableError,
    CalibrationObjectStore,
    CalibrationPhotoAdapter,
    evaluate_frozen_calibration,
    freeze_calibration_photos,
    result_bundle_from_offline,
)

_MAX_JSON_BYTES = 1024 * 1024
_FORBIDDEN_KEYS = frozenset(
    {
        "embedding",
        "embeddings",
        "token",
        "tokens",
        "credential",
        "credentials",
        "secret",
        "secrets",
        "object_key",
        "object_store_key",
        "request_body",
    }
)

if TYPE_CHECKING:
    from face_moment.diagnostics.ground_truth_annotations import GroundTruthAnnotationProvider


class CalibrationRunStatus(StrEnum):
    REQUESTED = "requested"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class CalibrationRunError(ValueError):
    """A Calibration operation violates the durable immutable-run contract."""


class CalibrationRunNotFoundError(LookupError):
    pass


class DatasetMismatchError(CalibrationRunError):
    pass


class CalibrationRun(Base):
    """One diagnostics-owned immutable selected dataset and terminal result."""

    __tablename__ = "calibration_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'running', 'complete', 'failed', 'interrupted')",
            name="ck_calibration_runs_status",
        ),
        CheckConstraint(
            "char_length(dataset_sha256) = 64",
            name="ck_calibration_runs_dataset_sha256_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    requested_by_staff_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(length=16), nullable=False)
    dataset_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    dataset_sha256: Mapped[str] = mapped_column(String(length=64), nullable=False)
    result_bundle: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True, slots=True)
class CalibrationRunComparison:
    before_run_id: uuid.UUID
    after_run_id: uuid.UUID
    dataset_sha256: str
    before_result: Mapping[str, object]
    after_result: Mapping[str, object]


class CalibrationRunRepository:
    """Only writer for the diagnostics-owned Calibration run lifecycle."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_requested(
        self,
        *,
        requested_by_staff_id: uuid.UUID,
        dataset_snapshot: Mapping[str, object],
    ) -> CalibrationRun:
        snapshot = _canonical_json_value(dataset_snapshot, field="dataset_snapshot")
        run = CalibrationRun(
            id=uuid.uuid4(),
            requested_by_staff_id=_require_uuid(requested_by_staff_id, "requested_by_staff_id"),
            status=CalibrationRunStatus.REQUESTED,
            dataset_snapshot=snapshot,
            dataset_sha256=_json_sha256(snapshot),
        )
        self._session.add(run)
        self._session.flush()
        self._session.refresh(run)
        return run

    def require(self, run_id: uuid.UUID, *, for_update: bool = False) -> CalibrationRun:
        statement = select(CalibrationRun).where(CalibrationRun.id == _require_uuid(run_id, "run_id"))
        if for_update:
            statement = statement.with_for_update()
        run = self._session.scalar(statement)
        if run is None:
            raise CalibrationRunNotFoundError(str(run_id))
        return run

    def start(self, run_id: uuid.UUID, *, now: datetime | None = None) -> CalibrationRun:
        run = self.require(run_id, for_update=True)
        if run.status != CalibrationRunStatus.REQUESTED:
            raise CalibrationRunError("Calibration run is not requested")
        run.status = CalibrationRunStatus.RUNNING
        run.started_at = _utc(now)
        self._session.flush()
        return run

    def complete(
        self,
        run_id: uuid.UUID,
        *,
        result_bundle: Mapping[str, object],
        now: datetime | None = None,
    ) -> CalibrationRun:
        run = self.require(run_id, for_update=True)
        if run.status != CalibrationRunStatus.RUNNING:
            raise CalibrationRunError("Calibration run is not running")
        run.status = CalibrationRunStatus.COMPLETE
        run.result_bundle = _canonical_json_value(result_bundle, field="result_bundle")
        run.finished_at = _utc(now)
        self._session.flush()
        return run

    def fail_unavailable(self, run_id: uuid.UUID, *, now: datetime | None = None) -> CalibrationRun:
        run = self.require(run_id, for_update=True)
        if run.status != CalibrationRunStatus.RUNNING:
            raise CalibrationRunError("Calibration run is not running")
        run.status = CalibrationRunStatus.FAILED
        run.error_code = "dataset_unavailable"
        run.finished_at = _utc(now)
        self._session.flush()
        return run

    def compare_complete(
        self, *, before_run_id: uuid.UUID, after_run_id: uuid.UUID
    ) -> CalibrationRunComparison:
        before = self.require(before_run_id)
        after = self.require(after_run_id)
        if before.status != CalibrationRunStatus.COMPLETE or after.status != CalibrationRunStatus.COMPLETE:
            raise CalibrationRunError("only complete Calibration runs are comparable")
        if before.dataset_sha256 != after.dataset_sha256:
            raise DatasetMismatchError("dataset_mismatch")
        assert before.result_bundle is not None
        assert after.result_bundle is not None
        return CalibrationRunComparison(
            before_run_id=before.id,
            after_run_id=after.id,
            dataset_sha256=before.dataset_sha256,
            before_result=before.result_bundle,
            after_result=after.result_bundle,
        )


class CalibrationRunService:
    """Diagnostics orchestration over its immutable snapshot and processing edge."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repository = CalibrationRunRepository(session)

    def request(
        self,
        *,
        requested_by_staff_id: uuid.UUID,
        photo_ids: Sequence[uuid.UUID],
        selected_attempt_ids: Sequence[uuid.UUID],
        sface_revision_id: uuid.UUID,
        buffalo_revision_id: uuid.UUID,
        serving_values: Mapping[str, object],
        candidate_values: Mapping[str, object],
    ) -> CalibrationRun:
        spa_id, photos = freeze_calibration_photos(self._session, photo_ids=photo_ids)
        from face_moment.diagnostics.ground_truth_annotations import GroundTruthAnnotationProvider

        attempts = _frozen_attempts(GroundTruthAnnotationProvider(self._session), selected_attempt_ids)
        snapshot: dict[str, object] = {
            "spa_id": str(spa_id),
            "photos": list(photos),
            "attempts": attempts,
            "pipeline_revisions": {
                "sface": str(_require_uuid(sface_revision_id, "sface_revision_id")),
                "buffalo_m": str(_require_uuid(buffalo_revision_id, "buffalo_revision_id")),
            },
            "serving_values": dict(serving_values),
            "candidate_values": dict(candidate_values),
        }
        return self._repository.create_requested(
            requested_by_staff_id=requested_by_staff_id,
            dataset_snapshot=snapshot,
        )

    def execute(
        self,
        *,
        run_id: uuid.UUID,
        sface_adapter: CalibrationPhotoAdapter,
        buffalo_adapter: CalibrationPhotoAdapter,
        object_store: CalibrationObjectStore,
    ) -> CalibrationRun:
        run = self._repository.start(run_id)
        snapshot = run.dataset_snapshot
        revisions = snapshot.get("pipeline_revisions")
        photos = snapshot.get("photos")
        attempts = snapshot.get("attempts")
        if not isinstance(revisions, Mapping) or not isinstance(photos, list) or not isinstance(attempts, list):
            raise CalibrationRunError("stored Calibration snapshot is malformed")
        sface_id = _snapshot_uuid(revisions.get("sface"), "sface revision")
        buffalo_id = _snapshot_uuid(revisions.get("buffalo_m"), "Buffalo M revision")
        attempt_ids = tuple(_snapshot_uuid(item.get("attempt_id"), "attempt") for item in attempts if isinstance(item, Mapping))
        if len(attempt_ids) != len(attempts):
            raise CalibrationRunError("stored Calibration Attempt snapshot is malformed")
        try:
            sface, buffalo = evaluate_frozen_calibration(
                self._session,
                photo_snapshot=photos,
                attempt_ids=attempt_ids,
                sface_revision_id=sface_id,
                buffalo_revision_id=buffalo_id,
                sface_adapter=sface_adapter,
                buffalo_adapter=buffalo_adapter,
                object_store=object_store,
            )
        except CalibrationDatasetUnavailableError:
            return self._repository.fail_unavailable(run.id)
        return self._repository.complete(
            run.id,
            result_bundle=result_bundle_from_offline(sface=sface, buffalo=buffalo),
        )


def _canonical_json_value(value: Mapping[str, object], *, field: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise CalibrationRunError(f"{field} must be an object")
    normalized = _normalize_json(value)
    if not isinstance(normalized, dict):
        raise CalibrationRunError(f"{field} must be an object")
    encoded = _canonical_json(normalized)
    if len(encoded) > _MAX_JSON_BYTES:
        raise CalibrationRunError(f"{field} exceeds 1 MiB")
    return normalized


def _normalize_json(value: object) -> object:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CalibrationRunError("Calibration JSON values must be finite")
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CalibrationRunError("Calibration JSON keys must be strings")
            if key.lower() in _FORBIDDEN_KEYS:
                raise CalibrationRunError(f"forbidden Calibration JSON key: {key}")
            normalized[key] = _normalize_json(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    raise CalibrationRunError("Calibration JSON contains an unsupported value")


def _json_sha256(value: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _require_uuid(value: uuid.UUID, field: str) -> uuid.UUID:
    if not isinstance(value, uuid.UUID):
        raise CalibrationRunError(f"{field} must be a UUID")
    return value


def _snapshot_uuid(value: object, field: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if not isinstance(value, str):
        raise CalibrationRunError(f"stored {field} must be a UUID")
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise CalibrationRunError(f"stored {field} must be a UUID") from error


def _frozen_attempts(
    annotation_provider: GroundTruthAnnotationProvider,
    selected_attempt_ids: Sequence[uuid.UUID],
) -> list[dict[str, object]]:
    if not selected_attempt_ids:
        raise CalibrationRunError("Calibration requires applicable annotated Attempts")
    frozen: list[dict[str, object]] = []
    identifiers: set[uuid.UUID] = set()
    for attempt_id in selected_attempt_ids:
        attempt_id = _require_uuid(attempt_id, "Attempt")
        if attempt_id in identifiers:
            raise CalibrationRunError("selected Attempts must be unique")
        identifiers.add(attempt_id)
        calculation = annotation_provider.calculation_snapshot(attempt_id=attempt_id)
        if not calculation.annotations:
            continue
        frozen.append(
            {
                "attempt_id": str(calculation.attempt_id),
                "annotations": [
                    {
                        "annotation_id": str(annotation.annotation_id),
                        "attempt_id": str(annotation.attempt_id),
                        "target_kind": annotation.target_kind,
                        "detection_occurrence_index": annotation.detection_occurrence_index,
                        "participant_name": annotation.participant_name,
                        "outcome": annotation.outcome,
                    }
                    for annotation in calculation.annotations
                ],
            }
        )
    if not frozen:
        raise CalibrationRunError("Calibration requires applicable annotated Attempts")
    return frozen


def _utc(value: datetime | None) -> datetime:
    timestamp = datetime.now(timezone.utc) if value is None else value
    if timestamp.tzinfo is None:
        raise CalibrationRunError("timestamps must be timezone-aware")
    return timestamp.astimezone(timezone.utc)

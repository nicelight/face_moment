"""Diagnostics-owned immutable Calibration run persistence and comparison."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import math
from typing import TYPE_CHECKING, Callable, Mapping, Sequence
import uuid

import cv2
from sqlalchemy import CheckConstraint, DateTime, String, Uuid, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import func

from face_moment.infrastructure.database import Base
from face_moment.processing.offline_calibration import (
    CalibrationDatasetUnavailableError,
    CalibrationOfflineInputError,
    CalibrationObjectStore,
    CalibrationPhotoAdapter,
    OfflineCalibrationResult,
    evaluate_frozen_calibration,
    evaluate_frozen_calibration_sequential,
    freeze_calibration_photos,
    result_bundle_from_offline,
)
from face_moment.processing.model_admission import ModelAdmissionError
from face_moment.processing.revisions import (
    IneligiblePipelineRevisionError,
    PipelineCode,
    PipelineRevisionRepository,
)
from face_moment.diagnostics.calibration_thresholds import (
    ThresholdCandidate,
    ThresholdProfileResult,
    calculate_threshold_profiles,
)
from face_moment.platform.auth.principals import StaffPrincipal, StaffRole
from face_moment.serving_control.realtime_context import (
    CalibrationRecommendationConflictError,
    CalibrationServingRecommendation,
    InvalidCalibrationRecommendationError,
    RealtimeContextRepository,
    UnknownRealtimeContextSpaError,
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


class CalibrationAccessDeniedError(PermissionError):
    pass


class CalibrationSelectionNotFoundError(LookupError):
    pass


class CalibrationSelectionConflictError(CalibrationRunError):
    pass


@dataclass(frozen=True, slots=True)
class StoredServingRecommendation:
    key: str
    recommendation: CalibrationServingRecommendation


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
    """Stored results sharing a derived data hash, excluding evaluation settings."""

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

    def list_recent(self, *, limit: int = 50) -> tuple[CalibrationRun, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise CalibrationRunError("Calibration list limit must be between 1 and 100")
        return tuple(
            self._session.scalars(
                select(CalibrationRun)
                .order_by(CalibrationRun.created_at.desc(), CalibrationRun.id.desc())
                .limit(limit)
            )
        )

    def start(self, run_id: uuid.UUID, *, now: datetime | None = None) -> CalibrationRun:
        run = self.require(run_id, for_update=True)
        if run.status != CalibrationRunStatus.REQUESTED:
            raise CalibrationRunError("Calibration run is not requested")
        run.status = CalibrationRunStatus.RUNNING
        run.started_at = _utc(now)
        self._session.flush()
        return run

    def next_requested_id(self) -> uuid.UUID | None:
        return self._session.scalar(
            select(CalibrationRun.id)
            .where(CalibrationRun.status == CalibrationRunStatus.REQUESTED)
            .order_by(CalibrationRun.created_at, CalibrationRun.id)
            .limit(1)
        )

    def interrupt_running(self, *, now: datetime | None = None) -> int:
        runs = list(
            self._session.scalars(
                select(CalibrationRun)
                .where(CalibrationRun.status == CalibrationRunStatus.RUNNING)
                .with_for_update()
            )
        )
        for run in runs:
            run.status = CalibrationRunStatus.INTERRUPTED
            run.error_code = "worker_interrupted"
            run.finished_at = _utc(now)
        self._session.flush()
        return len(runs)

    def fail(self, run_id: uuid.UUID, *, error_code: str, now: datetime | None = None) -> CalibrationRun:
        run = self.require(run_id, for_update=True)
        if run.status != CalibrationRunStatus.RUNNING:
            raise CalibrationRunError("Calibration run is not running")
        run.status = CalibrationRunStatus.FAILED
        run.error_code = error_code
        run.finished_at = _utc(now)
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
        before_dataset_sha256 = _comparison_dataset_sha256(before.dataset_snapshot)
        after_dataset_sha256 = _comparison_dataset_sha256(after.dataset_snapshot)
        if before_dataset_sha256 != after_dataset_sha256:
            raise DatasetMismatchError("dataset_mismatch")
        assert before.result_bundle is not None
        assert after.result_bundle is not None
        return CalibrationRunComparison(
            before_run_id=before.id,
            after_run_id=after.id,
            dataset_sha256=before_dataset_sha256,
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

        attempts, selected_attempt_snapshot, selection_exclusions = _frozen_attempt_selection(
            self._session,
            GroundTruthAnnotationProvider(self._session),
            selected_attempt_ids,
        )
        snapshot: dict[str, object] = {
            "spa_id": str(spa_id),
            "photos": list(photos),
            "selected_attempt_ids": selected_attempt_snapshot,
            "selection_exclusions": selection_exclusions,
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

    def request_from_selection(
        self,
        *,
        requested_by_staff_id: uuid.UUID,
        photo_ids: Sequence[uuid.UUID],
        selected_attempt_ids: Sequence[uuid.UUID],
        sface_revision_id: uuid.UUID,
        buffalo_revision_id: uuid.UUID,
    ) -> CalibrationRun:
        """Resolve only server-owned values around the submitted UUID selection."""

        photo_ids = _unique_uuid_selection(photo_ids, "Photo")
        selected_attempt_ids = _unique_uuid_selection(
            selected_attempt_ids, "Attempt"
        )
        try:
            spa_id, _photos = freeze_calibration_photos(
                self._session, photo_ids=photo_ids
            )
        except CalibrationOfflineInputError as error:
            if "missing" in str(error):
                raise CalibrationSelectionNotFoundError from error
            raise CalibrationSelectionConflictError(str(error)) from error

        from face_moment.promo.attempt import PromoAttempt

        attempts = tuple(
            self._session.scalars(
                select(PromoAttempt).where(PromoAttempt.id.in_(selected_attempt_ids))
            )
        )
        if len(attempts) != len(selected_attempt_ids):
            raise CalibrationSelectionNotFoundError
        if any(attempt.spa_id != spa_id for attempt in attempts):
            raise CalibrationSelectionConflictError(
                "selected Attempts must belong to the selected SPA"
            )

        try:
            sface = PipelineRevisionRepository(self._session).resolve_eligible(
                sface_revision_id
            )
            buffalo = PipelineRevisionRepository(self._session).resolve_eligible(
                buffalo_revision_id
            )
        except IneligiblePipelineRevisionError as error:
            raise CalibrationSelectionConflictError(
                "selected Calibration revision is not eligible"
            ) from error
        if (
            sface.pipeline_code is not PipelineCode.OPENCV_SFACE
            or buffalo.pipeline_code is not PipelineCode.INSIGHTFACE_BUFFALO_M
        ):
            raise CalibrationSelectionConflictError(
                "Calibration requires one SFace and one Buffalo M revision"
            )

        try:
            serving = RealtimeContextRepository(
                self._session
            ).read_calibration_serving_snapshot(spa_id=spa_id)
        except (
            CalibrationRecommendationConflictError,
            UnknownRealtimeContextSpaError,
        ) as error:
            raise CalibrationSelectionConflictError(str(error)) from error

        serving_values: dict[str, object] = {
            "settings_revision": serving.settings_revision,
            "pipeline_revision_id": str(serving.pipeline_revision_id),
            "pipeline_code": serving.pipeline_code.value,
            "reference_threshold": serving.reference_threshold,
            "min_query_face_quality": serving.min_query_face_quality,
            "quality_settings": dict(serving.quality_settings),
        }
        candidate_values: dict[str, object] = {
            "reference_thresholds": sorted(
                {float(attempt.threshold) for attempt in attempts}
            ),
            "quality_settings": [dict(serving.quality_settings)],
        }
        try:
            return self.request(
                requested_by_staff_id=requested_by_staff_id,
                photo_ids=photo_ids,
                selected_attempt_ids=selected_attempt_ids,
                sface_revision_id=sface.id,
                buffalo_revision_id=buffalo.id,
                serving_values=serving_values,
                candidate_values=candidate_values,
            )
        except CalibrationRunNotFoundError as error:
            raise CalibrationSelectionNotFoundError from error
        except (CalibrationRunError, CalibrationOfflineInputError) as error:
            raise CalibrationSelectionConflictError(str(error)) from error

    def list_recent(self) -> tuple[CalibrationRun, ...]:
        return self._repository.list_recent()

    def require(self, run_id: uuid.UUID) -> CalibrationRun:
        return self._repository.require(run_id)

    def serving_recommendations(
        self, run: CalibrationRun
    ) -> tuple[StoredServingRecommendation, ...]:
        if run.status != CalibrationRunStatus.COMPLETE or run.result_bundle is None:
            return ()
        raw_recommendations = run.result_bundle.get("serving_recommendations")
        if raw_recommendations is None:
            return ()
        if not isinstance(raw_recommendations, list) or len(raw_recommendations) > 64:
            raise CalibrationSelectionConflictError(
                "stored Calibration recommendations are malformed"
            )
        serving_values = run.dataset_snapshot.get("serving_values")
        if not isinstance(serving_values, Mapping):
            raise CalibrationSelectionConflictError(
                "stored Calibration serving snapshot is malformed"
            )
        expected_revision = serving_values.get("settings_revision")
        if (
            not isinstance(expected_revision, int)
            or isinstance(expected_revision, bool)
            or expected_revision <= 0
        ):
            raise CalibrationSelectionConflictError(
                "stored Calibration settings revision is malformed"
            )

        resolved: list[StoredServingRecommendation] = []
        keys: set[str] = set()
        for value in raw_recommendations:
            if not isinstance(value, Mapping):
                raise CalibrationSelectionConflictError(
                    "stored Calibration recommendation is malformed"
                )
            key = value.get("key")
            pipeline_code = value.get("pipeline_code")
            quality_settings = value.get("quality_settings")
            if (
                not isinstance(key, str)
                or not key
                or len(key) > 128
                or key in keys
                or not isinstance(pipeline_code, str)
                or not isinstance(quality_settings, Mapping)
            ):
                raise CalibrationSelectionConflictError(
                    "stored Calibration recommendation is malformed"
                )
            try:
                typed_pipeline = PipelineCode(pipeline_code)
                pipeline_revision_id = _snapshot_uuid(
                    value.get("pipeline_revision_id"),
                    "recommendation pipeline revision",
                )
                threshold = _stored_finite(
                    value.get("reference_threshold"), "reference_threshold"
                )
                min_quality = _stored_finite(
                    value.get("min_query_face_quality"),
                    "min_query_face_quality",
                )
            except (ValueError, TypeError, CalibrationRunError) as error:
                raise CalibrationSelectionConflictError(
                    "stored Calibration recommendation is malformed"
                ) from error
            keys.add(key)
            resolved.append(
                StoredServingRecommendation(
                    key=key,
                    recommendation=CalibrationServingRecommendation(
                        expected_settings_revision=expected_revision,
                        pipeline_revision_id=pipeline_revision_id,
                        pipeline_code=typed_pipeline,
                        reference_threshold=threshold,
                        min_query_face_quality=min_quality,
                        quality_settings=dict(quality_settings),
                    ),
                )
            )
        return tuple(resolved)

    def apply_stored_recommendation(
        self, *, run_id: uuid.UUID, recommendation_key: str
    ) -> int:
        run = self._repository.require(run_id, for_update=True)
        if run.status != CalibrationRunStatus.COMPLETE:
            raise CalibrationSelectionConflictError(
                "only a complete Calibration run can be applied"
            )
        recommendations = self.serving_recommendations(run)
        selected = next(
            (item for item in recommendations if item.key == recommendation_key),
            None,
        )
        if selected is None:
            raise CalibrationSelectionNotFoundError
        spa_id = _snapshot_uuid(run.dataset_snapshot.get("spa_id"), "SPA")
        try:
            owner = RealtimeContextRepository(self._session)
            owner.apply_calibration_recommendation(
                spa_id=spa_id,
                calibration_id=run.id,
                recommendation=selected.recommendation,
            )
            applied = owner.read_calibration_serving_snapshot(spa_id=spa_id)
        except (
            CalibrationRecommendationConflictError,
            InvalidCalibrationRecommendationError,
            UnknownRealtimeContextSpaError,
        ) as error:
            raise CalibrationSelectionConflictError(str(error)) from error
        if applied.calibration_id != run.id:
            raise CalibrationSelectionConflictError(
                "the stored Calibration apply result was not committed in owner state"
            )
        return applied.settings_revision

    def is_applied_result(
        self, *, run: CalibrationRun, settings_revision: int | None
    ) -> bool:
        if settings_revision is None or settings_revision <= 0:
            return False
        spa_id = _snapshot_uuid(run.dataset_snapshot.get("spa_id"), "SPA")
        try:
            current = RealtimeContextRepository(
                self._session
            ).read_calibration_serving_snapshot(spa_id=spa_id)
        except (
            CalibrationRecommendationConflictError,
            UnknownRealtimeContextSpaError,
        ) as error:
            raise CalibrationSelectionConflictError(str(error)) from error
        serving_values = run.dataset_snapshot.get("serving_values")
        if not isinstance(serving_values, Mapping):
            raise CalibrationSelectionConflictError(
                "stored Calibration serving snapshot is malformed"
            )
        try:
            expected_pipeline_revision_id = _snapshot_uuid(
                serving_values.get("pipeline_revision_id"),
                "serving pipeline revision",
            )
        except CalibrationRunError as error:
            raise CalibrationSelectionConflictError(str(error)) from error
        return (
            current.settings_revision == settings_revision
            and current.calibration_id == run.id
            and current.pipeline_revision_id == expected_pipeline_revision_id
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
            result_bundle=_result_bundle_for_run(
                run.dataset_snapshot, sface=sface, buffalo=buffalo
            ),
        )

    def has_requested(self) -> bool:
        return self._repository.next_requested_id() is not None

    def execute_next_requested(
        self,
        *,
        bind_selected_adapter: Callable[[object], CalibrationPhotoAdapter],
        object_store: CalibrationObjectStore,
    ) -> CalibrationRun | None:
        run_id = self.claim_next_requested()
        if run_id is None:
            return None
        return self.execute_claimed(
            run_id=run_id,
            bind_selected_adapter=bind_selected_adapter,
            object_store=object_store,
        )

    def claim_next_requested(self) -> uuid.UUID | None:
        run_id = self._repository.next_requested_id()
        if run_id is None:
            return None
        run = self._repository.start(run_id)
        # The worker must recover a selected run even before it occupies its
        # Calibration operation, so never leave this claim in a later callback
        # or evaluation transaction.
        self._session.commit()
        return run.id

    def execute_claimed(
        self,
        *,
        run_id: uuid.UUID,
        bind_selected_adapter: Callable[[object], CalibrationPhotoAdapter],
        object_store: CalibrationObjectStore,
    ) -> CalibrationRun:
        run = self._repository.require(run_id)
        if run.status != CalibrationRunStatus.RUNNING:
            raise CalibrationRunError("Calibration run is not running")
        snapshot = run.dataset_snapshot
        revisions = snapshot.get("pipeline_revisions")
        photos = snapshot.get("photos")
        attempts = snapshot.get("attempts")
        if not isinstance(revisions, Mapping) or not isinstance(photos, list) or not isinstance(attempts, list):
            raise CalibrationRunError("stored Calibration snapshot is malformed")
        sface_id = _snapshot_uuid(revisions.get("sface"), "sface revision")
        buffalo_id = _snapshot_uuid(revisions.get("buffalo_m"), "Buffalo M revision")
        attempt_ids = tuple(
            _snapshot_uuid(item.get("attempt_id"), "attempt")
            for item in attempts
            if isinstance(item, Mapping)
        )
        if len(attempt_ids) != len(attempts):
            raise CalibrationRunError("stored Calibration Attempt snapshot is malformed")
        try:
            sface, buffalo = evaluate_frozen_calibration_sequential(
                self._session,
                photo_snapshot=photos,
                attempt_ids=attempt_ids,
                sface_revision_id=sface_id,
                buffalo_revision_id=buffalo_id,
                bind_selected_adapter=bind_selected_adapter,
                object_store=object_store,
            )
        except CalibrationDatasetUnavailableError:
            return self._repository.fail_unavailable(run.id)
        except (CalibrationOfflineInputError, ModelAdmissionError, cv2.error):
            return self._repository.fail(run.id, error_code="model_unavailable")
        return self._repository.complete(
            run.id,
            result_bundle=_result_bundle_for_run(
                run.dataset_snapshot, sface=sface, buffalo=buffalo
            ),
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


def _comparison_dataset_sha256(snapshot: Mapping[str, object]) -> str:
    """Hash frozen data without changing the persisted full-input fingerprint."""
    data = dict(snapshot)
    for field in ("pipeline_revisions", "serving_values", "candidate_values"):
        data.pop(field, None)
    return _json_sha256(data)


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


def _frozen_attempt_selection(
    session: Session,
    annotation_provider: GroundTruthAnnotationProvider,
    selected_attempt_ids: Sequence[uuid.UUID],
) -> tuple[list[dict[str, object]], list[str], list[dict[str, str]]]:
    from face_moment.promo.attempt import PromoAttempt

    if not selected_attempt_ids:
        raise CalibrationRunError("Calibration requires selected Attempts")
    frozen: list[dict[str, object]] = []
    selected: list[str] = []
    exclusions: list[dict[str, str]] = []
    identifiers: set[uuid.UUID] = set()
    for attempt_id in selected_attempt_ids:
        attempt_id = _require_uuid(attempt_id, "Attempt")
        if attempt_id in identifiers:
            raise CalibrationRunError("selected Attempts must be unique")
        identifiers.add(attempt_id)
        selected.append(str(attempt_id))
        attempt = session.get(PromoAttempt, attempt_id)
        if attempt is None:
            raise CalibrationRunError("selected Attempt is missing")
        calculation = annotation_provider.calculation_snapshot(attempt_id=attempt_id)
        if not calculation.annotations:
            exclusions.append(
                {"attempt_id": str(attempt_id), "reason": "missing_ground_truth"}
            )
            continue
        threshold = _finite_snapshot_value(attempt.threshold, "Attempt threshold")
        frozen.append(
            {
                "attempt_id": str(calculation.attempt_id),
                "pipeline_revision_id": str(attempt.pipeline_revision_id),
                "pipeline_code": attempt.pipeline_code,
                "reference_threshold": threshold,
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
    return frozen, selected, exclusions


def _result_bundle_for_run(
    snapshot: Mapping[str, object],
    *,
    sface: OfflineCalibrationResult,
    buffalo: OfflineCalibrationResult,
) -> dict[str, object]:
    result = result_bundle_from_offline(sface=sface, buffalo=buffalo)
    composed = _compose_balance_recommendation(snapshot)
    if composed is None:
        return result
    profile, recommendation = composed
    result["threshold_profiles"] = [profile.to_dict()]
    if recommendation is not None:
        result["serving_recommendations"] = [recommendation]
    return result


def _compose_balance_recommendation(
    snapshot: Mapping[str, object],
) -> tuple[ThresholdProfileResult, dict[str, object] | None] | None:
    serving = snapshot.get("serving_values")
    revisions = snapshot.get("pipeline_revisions")
    attempts = snapshot.get("attempts")
    selected_attempt_ids = snapshot.get("selected_attempt_ids")
    if (
        not isinstance(serving, Mapping)
        or not isinstance(revisions, Mapping)
        or not isinstance(attempts, list)
        or not isinstance(selected_attempt_ids, list)
        or not selected_attempt_ids
        or any(not isinstance(attempt_id, str) for attempt_id in selected_attempt_ids)
    ):
        return None
    selected_attempt_count = len(selected_attempt_ids)

    pipeline_code_value = serving.get("pipeline_code")
    pipeline_revision_value = serving.get("pipeline_revision_id")
    if not isinstance(pipeline_code_value, str) or pipeline_revision_value is None:
        return None
    try:
        pipeline_code = PipelineCode(pipeline_code_value)
        pipeline_revision_id = _snapshot_uuid(
            pipeline_revision_value, "serving pipeline revision"
        )
    except ValueError as error:
        raise CalibrationRunError("stored serving pipeline code is malformed") from error

    revision_key = (
        "sface"
        if pipeline_code is PipelineCode.OPENCV_SFACE
        else "buffalo_m"
    )
    if _snapshot_uuid(revisions.get(revision_key), revision_key) != pipeline_revision_id:
        return None

    parsed_attempts: list[tuple[str, float, list[object]]] = []
    for value in attempts:
        if not isinstance(value, Mapping):
            raise CalibrationRunError("stored Calibration Attempt is malformed")
        if (
            value.get("pipeline_revision_id") != str(pipeline_revision_id)
            or value.get("pipeline_code") != pipeline_code.value
        ):
            return None
        attempt_id = value.get("attempt_id")
        annotations = value.get("annotations")
        if not isinstance(attempt_id, str) or not isinstance(annotations, list):
            raise CalibrationRunError("stored Calibration Attempt is malformed")
        threshold = _finite_snapshot_value(
            value.get("reference_threshold"), "Attempt threshold"
        )
        parsed_attempts.append((attempt_id, threshold, annotations))

    thresholds = {threshold for _attempt_id, threshold, _rows in parsed_attempts}
    if len(thresholds) > 1:
        return None
    if thresholds:
        threshold = next(iter(thresholds))
    else:
        try:
            threshold = _finite_snapshot_value(
                serving.get("reference_threshold"), "serving reference threshold"
            )
        except CalibrationRunError:
            return None
    counts = {"correct": 0, "false": 0, "missed": 0}
    contributing: list[str] = []
    for attempt_id, _threshold, annotations in parsed_attempts:
        contributed = False
        for annotation in annotations:
            if not isinstance(annotation, Mapping):
                raise CalibrationRunError("stored Calibration annotation is malformed")
            outcome = annotation.get("outcome")
            if outcome not in counts:
                raise CalibrationRunError("stored Calibration annotation is malformed")
            counts[outcome] += 1
            contributed = True
        if contributed:
            contributing.append(attempt_id)

    profile = calculate_threshold_profiles(
        pipeline_revision_id=str(pipeline_revision_id),
        candidates=(
            ThresholdCandidate(
                threshold=threshold,
                correct=counts["correct"],
                false=counts["false"],
                missed=counts["missed"],
                contributing_attempt_ids=tuple(contributing),
            ),
        ),
        selected_attempt_count=selected_attempt_count,
        applicable_attempt_count=len(parsed_attempts),
    )
    proposal = profile.profiles["balance"].proposal
    if proposal is None:
        return profile, None
    quality_settings = serving.get("quality_settings")
    if not isinstance(quality_settings, Mapping):
        raise CalibrationRunError("stored serving quality settings are malformed")
    key = (
        "sface-balance"
        if pipeline_code is PipelineCode.OPENCV_SFACE
        else "buffalo-m-balance"
    )
    return profile, {
        "key": key,
        "pipeline_revision_id": str(pipeline_revision_id),
        "pipeline_code": pipeline_code.value,
        "reference_threshold": proposal.threshold,
        "min_query_face_quality": _finite_snapshot_value(
            serving.get("min_query_face_quality"), "minimum query face quality"
        ),
        "quality_settings": dict(quality_settings),
    }


def _utc(value: datetime | None) -> datetime:
    timestamp = datetime.now(timezone.utc) if value is None else value
    if timestamp.tzinfo is None:
        raise CalibrationRunError("timestamps must be timezone-aware")
    return timestamp.astimezone(timezone.utc)


def authorize_calibration(principal: StaffPrincipal) -> None:
    if principal.role is not StaffRole.DEVELOPER:
        raise CalibrationAccessDeniedError


def _unique_uuid_selection(
    values: Sequence[uuid.UUID], name: str
) -> tuple[uuid.UUID, ...]:
    if not values or any(not isinstance(value, uuid.UUID) for value in values):
        raise CalibrationSelectionConflictError(
            f"{name} selection must contain UUIDs"
        )
    normalized = tuple(values)
    if len(set(normalized)) != len(normalized):
        raise CalibrationSelectionConflictError(
            f"{name} selection must be unique"
        )
    return normalized


def _finite_snapshot_value(value: object, field: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise CalibrationRunError(f"stored {field} must be finite")
    return float(value)


def _stored_finite(value: object, field: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise CalibrationSelectionConflictError(
            f"stored {field} must be finite"
        )
    return float(value)

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timezone
import json
import math
from typing import TYPE_CHECKING, Literal
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Double,
    Integer,
    JSON,
    String,
    Uuid,
    UniqueConstraint,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import func

from face_moment.infrastructure.database import Base
from face_moment.processing.revisions import PipelineCode
from face_moment.promo.result_assembly import ResultAssembly

if TYPE_CHECKING:
    from face_moment.promo.session import ResultSessionResponse

_MAX_TEXT_LENGTH = 255
_MAX_JSON_BYTES = 4096


class PromoAttempt(Base):
    """Promo-owned immutable admission snapshot and processing state."""

    __tablename__ = "promo_attempts"
    __table_args__ = (
        CheckConstraint(
            "trigger_source IN ('sensor', 'test')",
            name="ck_promo_attempts_trigger_source",
        ),
        CheckConstraint(
            "jpeg_quality BETWEEN 1 AND 100",
            name="ck_promo_attempts_jpeg_quality_range",
        ),
        CheckConstraint(
            "local_detection_completed_ms >= 0 AND request_started_ms >= 0",
            name="ck_promo_attempts_client_offsets_nonnegative",
        ),
        CheckConstraint(
            "proposal_count BETWEEN 0 AND 20",
            name="ck_promo_attempts_proposal_count_range",
        ),
        CheckConstraint(
            "settings_revision > 0",
            name="ck_promo_attempts_settings_revision_positive",
        ),
        CheckConstraint(
            "pipeline_code IN ('opencv_sface', 'insightface_buffalo_m')",
            name="ck_promo_attempts_pipeline_code",
        ),
        CheckConstraint(
            "query_source = 'reference'",
            name="ck_promo_attempts_query_source",
        ),
        CheckConstraint(
            "deadline_ms > 0",
            name="ck_promo_attempts_deadline_positive",
        ),
        CheckConstraint(
            "processing_status IN ('accepted', 'searching', 'result_issued', "
            "'no_success', 'interrupted', 'deadline', 'internal_failure')",
            name="ck_promo_attempts_processing_status",
        ),
        CheckConstraint(
            "domain_outcome IS NULL OR domain_outcome IN "
            "('result', 'no_proposals', 'busy', 'deadline', "
            "'unacceptable_query', 'insufficient_results', 'interrupted')",
            name="ck_promo_attempts_domain_outcome",
        ),
        CheckConstraint(
            "display_status IN ('not_applicable', 'pending', 'confirmed', 'failed')",
            name="ck_promo_attempts_display_status",
        ),
        CheckConstraint(
            "qr_fully_visible_elapsed_ms IS NULL OR qr_fully_visible_elapsed_ms >= 0",
            name="ck_promo_attempts_qr_elapsed_nonnegative",
        ),
        UniqueConstraint(
            "spa_id",
            "client_attempt_id",
            name="uq_promo_attempts_spa_client_attempt",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    spa_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    client_attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    trigger_source: Mapped[str] = mapped_column(String(16), nullable=False)
    client_release: Mapped[str] = mapped_column(String(_MAX_TEXT_LENGTH), nullable=False)
    detector_id: Mapped[str] = mapped_column(String(_MAX_TEXT_LENGTH), nullable=False)
    model_version: Mapped[str] = mapped_column(String(_MAX_TEXT_LENGTH), nullable=False)
    jpeg_quality: Mapped[int] = mapped_column(Integer, nullable=False)
    camera_device_id: Mapped[str] = mapped_column(String(_MAX_TEXT_LENGTH), nullable=False)
    reference_series_ready_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    local_detection_completed_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    request_started_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    proposal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    settings_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    visit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    pipeline_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    pipeline_code: Mapped[str] = mapped_column(String(32), nullable=False)
    query_source: Mapped[str] = mapped_column(String(32), nullable=False)
    release_id: Mapped[str] = mapped_column(String(_MAX_TEXT_LENGTH), nullable=False)
    threshold: Mapped[float] = mapped_column(Double, nullable=False)
    quality_settings: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    calibration_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    deadline_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    slot_decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    search_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    search_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="accepted", server_default="accepted"
    )
    domain_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    display_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_applicable", server_default="not_applicable"
    )
    display_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    display_reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    qr_fully_visible_elapsed_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PromoAttemptNotFoundError(LookupError):
    pass


class PromoAttemptRepository:
    """Only-writer repository for admitted promo Attempts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_or_get(
        self,
        *,
        spa_id: uuid.UUID,
        client_attempt_id: uuid.UUID,
        trigger_source: str,
        client_release: str,
        detector_id: str,
        model_version: str,
        jpeg_quality: int,
        camera_device_id: str,
        reference_series_ready_at: datetime,
        local_detection_completed_ms: int,
        request_started_ms: int,
        proposal_count: int,
        settings_revision: int,
        visit_date: date | None,
        pipeline_revision_id: uuid.UUID,
        pipeline_code: PipelineCode,
        query_source: str,
        threshold: float,
        quality_settings: Mapping[str, object],
        release_id: str,
        deadline_ms: int,
        calibration_id: uuid.UUID | None = None,
    ) -> PromoAttempt:
        existing = self._find(spa_id, client_attempt_id)
        if existing is not None:
            return existing
        values = self._validated_values(
            spa_id=spa_id,
            client_attempt_id=client_attempt_id,
            trigger_source=trigger_source,
            client_release=client_release,
            detector_id=detector_id,
            model_version=model_version,
            jpeg_quality=jpeg_quality,
            camera_device_id=camera_device_id,
            reference_series_ready_at=reference_series_ready_at,
            local_detection_completed_ms=local_detection_completed_ms,
            request_started_ms=request_started_ms,
            proposal_count=proposal_count,
            settings_revision=settings_revision,
            visit_date=visit_date,
            pipeline_revision_id=pipeline_revision_id,
            pipeline_code=pipeline_code,
            query_source=query_source,
            threshold=threshold,
            quality_settings=quality_settings,
            release_id=release_id,
            deadline_ms=deadline_ms,
            calibration_id=calibration_id,
        )
        attempt = PromoAttempt(**values)
        try:
            with self._session.begin_nested():
                self._session.add(attempt)
                self._session.flush()
        except IntegrityError:
            existing = self._find(spa_id, client_attempt_id)
            if existing is not None:
                return existing
            raise
        return attempt

    def get(self, attempt_id: uuid.UUID) -> PromoAttempt:
        attempt = self._session.get(PromoAttempt, attempt_id)
        if attempt is None:
            raise PromoAttemptNotFoundError(str(attempt_id))
        return attempt

    def get_by_admission_key(
        self,
        *,
        spa_id: uuid.UUID,
        client_attempt_id: uuid.UUID,
        for_update: bool = False,
    ) -> PromoAttempt:
        statement = select(PromoAttempt).where(
            PromoAttempt.spa_id == spa_id,
            PromoAttempt.client_attempt_id == client_attempt_id,
        )
        if for_update:
            statement = statement.with_for_update()
        attempt = self._session.scalar(statement)
        if attempt is None:
            raise PromoAttemptNotFoundError(f"{spa_id}/{client_attempt_id}")
        return attempt

    def mark_no_proposals(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt:
        """Close an admitted zero-proposal Attempt without invoking search."""

        return self._mark_accepted_terminal(
            attempt,
            processing_status="no_success",
            domain_outcome="no_proposals",
            now=now,
            error_message="only an accepted Attempt can be closed as no_proposals",
        )

    def mark_busy(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt:
        """Close an admitted Attempt that cannot acquire the process-local slot."""

        return self._mark_accepted_terminal(
            attempt,
            processing_status="no_success",
            domain_outcome="busy",
            now=now,
            error_message="only an accepted Attempt can be closed as busy",
        )

    def mark_unacceptable_query(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt:
        """Close an admitted Attempt when every selected query is unusable."""

        return self._mark_active_terminal(
            attempt,
            processing_status="no_success",
            domain_outcome="unacceptable_query",
            now=now,
            error_message="only an active Attempt can be closed as unacceptable_query",
        )

    def mark_insufficient_results(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt:
        """Close an admitted Attempt without publishing a partial result."""

        return self._mark_active_terminal(
            attempt,
            processing_status="no_success",
            domain_outcome="insufficient_results",
            now=now,
            error_message="only an active Attempt can be closed as insufficient_results",
        )

    def mark_search_started(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt:
        """Atomically move the slot owner from admission into processing."""

        timestamp = _utc(now)
        result = self._session.execute(
            update(PromoAttempt)
            .where(
                PromoAttempt.id == attempt.id,
                PromoAttempt.processing_status == "accepted",
            )
            .values(
                processing_status="searching",
                slot_decided_at=timestamp,
                search_started_at=timestamp,
                updated_at=timestamp,
            )
        )
        if result.rowcount != 1:
            self._session.refresh(attempt)
            raise ValueError("only an accepted Attempt can start searching")
        self._session.flush()
        return attempt

    def mark_deadline(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt:
        """Discard a late processing return without publishing a result."""

        return self._mark_active_terminal(
            attempt,
            processing_status="deadline",
            domain_outcome="deadline",
            now=now,
            error_message="only an admitted Attempt can be closed as deadline",
        )

    def mark_internal_failure(
        self, attempt: PromoAttempt, *, now: datetime | None = None
    ) -> PromoAttempt:
        """Record an admitted technical failure without changing foreign state."""

        return self._mark_active_terminal(
            attempt,
            processing_status="internal_failure",
            domain_outcome=None,
            now=now,
            error_message="only an accepted Attempt can be marked internal_failure",
        )

    def publish_result(
        self,
        attempt: PromoAttempt,
        assembly: ResultAssembly,
        *,
        qr_ticket_secret: bytes | str,
        display_expires_at: datetime,
        qr_issued_at: datetime | None = None,
        failure_hook: Callable[[str], None] | None = None,
    ) -> ResultSessionResponse:
        """Publish the promo-owned session and terminal Attempt atomically."""

        from face_moment.promo.session import PromoSessionRepository

        return PromoSessionRepository(
            self._session,
            qr_ticket_secret=qr_ticket_secret,
            failure_hook=failure_hook,
        ).publish_result(
            attempt,
            assembly,
            display_expires_at=display_expires_at,
            qr_issued_at=qr_issued_at,
        )

    def record_display_outcome(
        self,
        attempt: PromoAttempt,
        *,
        status: Literal["confirmed", "failed"],
        qr_fully_visible_elapsed_ms: int | None = None,
        now: datetime | None = None,
    ) -> PromoAttempt:
        """Atomically record the first timely terminal display report."""

        if status not in {"confirmed", "failed"}:
            raise ValueError("display status must be confirmed or failed")
        if status == "failed" and qr_fully_visible_elapsed_ms is not None:
            raise ValueError("failed display reports cannot contain QR elapsed time")
        if status == "confirmed" and (
            not isinstance(qr_fully_visible_elapsed_ms, int)
            or isinstance(qr_fully_visible_elapsed_ms, bool)
            or qr_fully_visible_elapsed_ms < 0
            or qr_fully_visible_elapsed_ms > 2_147_483_647
        ):
            raise ValueError("confirmed display reports require a valid QR elapsed time")
        timestamp = _utc(now)
        result = self._session.execute(
            update(PromoAttempt)
            .where(
                PromoAttempt.id == attempt.id,
                PromoAttempt.display_status == "pending",
                PromoAttempt.display_expires_at.is_not(None),
                PromoAttempt.display_expires_at > timestamp,
            )
            .values(
                display_status=status,
                display_reported_at=timestamp,
                qr_fully_visible_elapsed_ms=qr_fully_visible_elapsed_ms,
                updated_at=timestamp,
            )
        )
        if result.rowcount != 1:
            self._session.refresh(attempt)
            raise ValueError("display report is late or already terminal")
        self._session.flush()
        self._session.refresh(attempt)
        return attempt

    def interrupt_stale(
        self, *, now: datetime | None = None
    ) -> int:
        """Terminally interrupt unfinished realtime Attempts at startup."""

        timestamp = _utc(now)
        result = self._session.execute(
            update(PromoAttempt)
            .where(PromoAttempt.processing_status.in_(("accepted", "searching")))
            .values(
                processing_status="interrupted",
                domain_outcome="interrupted",
                search_finished_at=timestamp,
                updated_at=timestamp,
            )
        )
        self._session.flush()
        return result.rowcount

    def _mark_accepted_terminal(
        self,
        attempt: PromoAttempt,
        *,
        processing_status: str,
        domain_outcome: str | None,
        now: datetime | None,
        error_message: str,
    ) -> PromoAttempt:
        timestamp = _utc(now)
        result = self._session.execute(
            update(PromoAttempt)
            .where(
                PromoAttempt.id == attempt.id,
                PromoAttempt.processing_status == "accepted",
            )
            .values(
                processing_status=processing_status,
                domain_outcome=domain_outcome,
                slot_decided_at=timestamp,
                search_finished_at=timestamp,
                updated_at=timestamp,
            )
        )
        if result.rowcount != 1:
            self._session.refresh(attempt)
            raise ValueError(error_message)
        self._session.flush()
        return attempt

    def _mark_active_terminal(
        self,
        attempt: PromoAttempt,
        *,
        processing_status: str,
        domain_outcome: str | None,
        now: datetime | None,
        error_message: str,
    ) -> PromoAttempt:
        timestamp = _utc(now)
        result = self._session.execute(
            update(PromoAttempt)
            .where(
                PromoAttempt.id == attempt.id,
                PromoAttempt.processing_status.in_(
                    ("accepted", "searching")
                ),
            )
            .values(
                processing_status=processing_status,
                domain_outcome=domain_outcome,
                slot_decided_at=func.coalesce(
                    PromoAttempt.slot_decided_at, timestamp
                ),
                search_finished_at=timestamp,
                updated_at=timestamp,
            )
        )
        if result.rowcount != 1:
            self._session.refresh(attempt)
            raise ValueError(error_message)
        self._session.flush()
        return attempt

    def _find(
        self, spa_id: uuid.UUID, client_attempt_id: uuid.UUID
    ) -> PromoAttempt | None:
        return self._session.scalar(
            select(PromoAttempt).where(
                PromoAttempt.spa_id == spa_id,
                PromoAttempt.client_attempt_id == client_attempt_id,
            )
        )

    @classmethod
    def _validated_values(cls, **values: object) -> dict[str, object]:
        trigger_source = values["trigger_source"]
        if trigger_source not in {"sensor", "test"}:
            raise ValueError("trigger_source must be sensor or test")
        for field_name in (
            "client_release",
            "detector_id",
            "model_version",
            "camera_device_id",
            "release_id",
        ):
            value = values[field_name]
            if not isinstance(value, str) or not value or len(value) > _MAX_TEXT_LENGTH:
                raise ValueError(f"{field_name} must be a non-empty bounded string")
        for field_name in (
            "local_detection_completed_ms",
            "request_started_ms",
        ):
            value = values[field_name]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be non-negative")
        for field_name in ("proposal_count",):
            value = values[field_name]
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 20:
                raise ValueError("proposal_count must be between 0 and 20")
        settings_revision = values["settings_revision"]
        if (
            not isinstance(settings_revision, int)
            or isinstance(settings_revision, bool)
            or settings_revision <= 0
        ):
            raise ValueError("settings_revision must be positive")
        jpeg_quality = values["jpeg_quality"]
        if not isinstance(jpeg_quality, int) or isinstance(jpeg_quality, bool) or not 1 <= jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")
        deadline_ms = values["deadline_ms"]
        if not isinstance(deadline_ms, int) or isinstance(deadline_ms, bool) or deadline_ms <= 0:
            raise ValueError("deadline_ms must be positive")
        pipeline_code = values["pipeline_code"]
        if not isinstance(pipeline_code, PipelineCode):
            raise ValueError("pipeline_code must be a supported PipelineCode")
        if values["query_source"] != "reference":
            raise ValueError("query_source must be reference")
        reference_series_ready_at = values["reference_series_ready_at"]
        if not isinstance(reference_series_ready_at, datetime) or reference_series_ready_at.tzinfo is None:
            raise ValueError("reference_series_ready_at must be timezone-aware")
        visit_date = values["visit_date"]
        if isinstance(visit_date, datetime):
            raise ValueError("visit_date must be a date or None")
        threshold = values["threshold"]
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not math.isfinite(float(threshold)):
            raise ValueError("threshold must be finite")
        quality_settings = values["quality_settings"]
        if not isinstance(quality_settings, Mapping):
            raise ValueError("quality_settings must be a JSON object")
        try:
            encoded_quality = json.dumps(
                dict(quality_settings), ensure_ascii=True, allow_nan=False, separators=(",", ":")
            )
        except (TypeError, ValueError) as error:
            raise ValueError("quality_settings must be bounded JSON") from error
        if len(encoded_quality.encode("utf-8")) > _MAX_JSON_BYTES:
            raise ValueError("quality_settings is too large")
        now = datetime.now(timezone.utc)
        return {
            **values,
            "pipeline_code": pipeline_code.value,
            "reference_series_ready_at": reference_series_ready_at.astimezone(timezone.utc),
            "threshold": float(threshold),
            "quality_settings": json.loads(encoded_quality),
            "created_at": now,
            "updated_at": now,
        }


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("promo Attempt timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)

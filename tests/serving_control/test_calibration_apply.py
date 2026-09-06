"""TASK-104 serving-control owner proof for confirmed Calibration apply."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import math
import uuid

import pytest
from sqlalchemy.orm import Session

from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control.ingest_target import IngestTargetRepository, Spa
from face_moment.serving_control.realtime_context import (
    CalibrationRecommendationConflictError,
    CalibrationServingRecommendation,
    InvalidCalibrationRecommendationError,
    RealtimeContextRepository,
)
from tests.disposable_postgresql import disposable_postgresql_engine


def _revision(session: Session, code: PipelineCode, label: str):
    return PipelineRevisionRepository(session).publish_eligible(
        pipeline_code=code,
        validated_at=datetime(2026, 9, 6, tzinfo=UTC),
        detector_id=f"task104-{label}-detector",
        detector_version="v1",
        recognizer_id=f"task104-{label}-recognizer",
        recognizer_version="v1",
        weights_sha256=hashlib.sha256(label.encode()).hexdigest(),
        preprocessing_version="task104-preprocess-v1",
        alignment_version="task104-align-v1",
        normalization_version="task104-normalize-v1",
        embedding_dimension=3,
    )


def _recommendation(
    revision: int, pipeline_revision_id: uuid.UUID
) -> CalibrationServingRecommendation:
    return CalibrationServingRecommendation(
        expected_settings_revision=revision,
        pipeline_revision_id=pipeline_revision_id,
        pipeline_code=PipelineCode.OPENCV_SFACE,
        reference_threshold=0.73,
        min_query_face_quality=0.66,
        quality_settings={"blur_maximum": 5.0, "version": 2},
    )


def test_only_owner_command_applies_complete_stored_values_with_provenance() -> None:
    calibration_id = uuid.uuid4()
    applied_at = datetime(2026, 9, 6, 1, 2, tzinfo=UTC)
    with disposable_postgresql_engine("task104_apply") as engine:
        with Session(engine) as session:
            sface = _revision(session, PipelineCode.OPENCV_SFACE, "sface")
            spa_record = IngestTargetRepository(session).configure_spa(
                name="Task 104 Apply",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=sface.id,
            )
            repository = RealtimeContextRepository(session)
            repository.provision_reference_settings(
                spa_id=spa_record.spa_id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
                reference_threshold=0.61,
                min_query_face_quality=0.51,
                quality_settings={"blur_maximum": 7.0, "version": 1},
            )
            session.commit()

            before = repository.read_calibration_serving_snapshot(
                spa_id=spa_record.spa_id
            )
            persisted_spa = session.get(Spa, spa_record.spa_id)
            assert persisted_spa is not None
            committed_revision = persisted_spa.serving_pipeline_revision_id
            applied = repository.apply_calibration_recommendation(
                spa_id=spa_record.spa_id,
                calibration_id=calibration_id,
                recommendation=_recommendation(before.settings_revision, sface.id),
                now=applied_at,
            )
            session.commit()

            spa = session.get(Spa, spa_record.spa_id)
            assert spa is not None
            assert spa.serving_pipeline_revision_id == committed_revision
            assert spa.settings_revision == before.settings_revision + 1
            assert spa.settings_updated_at == applied_at
            assert applied.reference_threshold == 0.73
            assert applied.min_query_face_quality == 0.66
            assert applied.quality_settings == {"blur_maximum": 5.0, "version": 2}
            assert applied.calibration_id == calibration_id
            assert applied.updated_at == applied_at


def test_stale_wrong_pipeline_and_invalid_values_preserve_owner_state() -> None:
    with disposable_postgresql_engine("task104_apply_rejections") as engine:
        with Session(engine) as session:
            sface = _revision(session, PipelineCode.OPENCV_SFACE, "sface")
            buffalo = _revision(
                session, PipelineCode.INSIGHTFACE_BUFFALO_M, "buffalo"
            )
            spa_record = IngestTargetRepository(session).configure_spa(
                name="Task 104 Apply Rejections",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=sface.id,
            )
            repository = RealtimeContextRepository(session)
            repository.provision_reference_settings(
                spa_id=spa_record.spa_id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
                reference_threshold=0.61,
                min_query_face_quality=0.51,
                quality_settings={"version": 1},
            )
            session.commit()
            baseline = repository.read_calibration_serving_snapshot(
                spa_id=spa_record.spa_id
            )
            session.commit()

            stale = _recommendation(baseline.settings_revision - 1, sface.id)
            wrong_pipeline = CalibrationServingRecommendation(
                expected_settings_revision=baseline.settings_revision,
                pipeline_revision_id=buffalo.id,
                pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
                reference_threshold=0.73,
                min_query_face_quality=0.66,
                quality_settings={"version": 2},
            )
            invalid = CalibrationServingRecommendation(
                expected_settings_revision=baseline.settings_revision,
                pipeline_revision_id=sface.id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
                reference_threshold=math.nan,
                min_query_face_quality=0.66,
                quality_settings={"version": 2},
            )
            with pytest.raises(CalibrationRecommendationConflictError, match="stale"):
                repository.apply_calibration_recommendation(
                    spa_id=spa_record.spa_id,
                    calibration_id=uuid.uuid4(),
                    recommendation=stale,
                )
            session.rollback()
            with pytest.raises(CalibrationRecommendationConflictError, match="another pipeline"):
                repository.apply_calibration_recommendation(
                    spa_id=spa_record.spa_id,
                    calibration_id=uuid.uuid4(),
                    recommendation=wrong_pipeline,
                )
            session.rollback()
            with pytest.raises(InvalidCalibrationRecommendationError, match="finite"):
                repository.apply_calibration_recommendation(
                    spa_id=spa_record.spa_id,
                    calibration_id=uuid.uuid4(),
                    recommendation=invalid,
                )
            session.rollback()

            after = repository.read_calibration_serving_snapshot(
                spa_id=spa_record.spa_id
            )
            assert after == baseline
            settings = repository.get_reference_settings(
                spa_id=spa_record.spa_id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
            )
            assert settings.calibration_id is None


def test_same_pipeline_revision_switch_rejects_old_calibration() -> None:
    with disposable_postgresql_engine("task104_apply_revision_switch") as engine:
        with Session(engine) as session:
            sface_a = _revision(session, PipelineCode.OPENCV_SFACE, "sface-a")
            sface_b = _revision(session, PipelineCode.OPENCV_SFACE, "sface-b")
            spa_record = IngestTargetRepository(session).configure_spa(
                name="Task 104 Revision Switch",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=sface_a.id,
            )
            repository = RealtimeContextRepository(session)
            repository.provision_reference_settings(
                spa_id=spa_record.spa_id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
                reference_threshold=0.61,
                min_query_face_quality=0.51,
                quality_settings={"version": 1},
            )
            spa_id = spa_record.spa_id
            sface_a_id = sface_a.id
            sface_b_id = sface_b.id
            session.commit()
            before = repository.read_calibration_serving_snapshot(
                spa_id=spa_id
            )
            old_recommendation = _recommendation(
                before.settings_revision, sface_a_id
            )
            session.commit()

        with Session(engine) as session:
            switched = IngestTargetRepository(session).switch_serving_revision(
                spa_id=spa_id,
                target_pipeline_revision_id=sface_b_id,
            )
            assert switched.outcome == "committed"

        with Session(engine) as session:
            repository = RealtimeContextRepository(session)
            after_switch = repository.read_calibration_serving_snapshot(
                spa_id=spa_id
            )
            assert after_switch.settings_revision == before.settings_revision
            assert after_switch.pipeline_revision_id == sface_b_id
            with pytest.raises(
                CalibrationRecommendationConflictError,
                match="another pipeline revision",
            ):
                repository.apply_calibration_recommendation(
                    spa_id=spa_id,
                    calibration_id=uuid.uuid4(),
                    recommendation=old_recommendation,
                )
            session.rollback()
            assert (
                repository.read_calibration_serving_snapshot(
                    spa_id=spa_id
                )
                == after_switch
            )

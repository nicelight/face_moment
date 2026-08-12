from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.inventory.admission import AtomicPhotoAdmission, AdmissionCandidate
from face_moment.inventory.candidate_staging import StagedCandidate
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource, ValidatedJpegCandidate
from face_moment.processing import (
    PipelineCode,
    PipelineRevisionRepository,
)
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.serving_control import IngestTarget, IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


class _InjectedPreCommitFailure(AtomicPhotoAdmission):
    def _after_pending_before_commit(self) -> None:
        raise RuntimeError("task-012-injected-pre-commit-failure")


def _candidate(marker: str) -> AdmissionCandidate:
    original_bytes = f"task-012-{marker}".encode()
    return AdmissionCandidate(
        staged_candidate=StagedCandidate(key=f"private/task-012-{marker}"),
        validated_jpeg=ValidatedJpegCandidate(
            original_bytes=original_bytes,
            checksum_sha256=hashlib.sha256(original_bytes).digest(),
            byte_size=len(original_bytes),
            width=12,
            height=10,
            visit_date=date(2026, 8, 11),
            captured_at=datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc),
            captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
            warning=None,
        ),
    )


def _target(session: Session, marker: str) -> IngestTarget:
    revision = PipelineRevisionRepository(session).publish_eligible(
        pipeline_code=PipelineCode.OPENCV_SFACE,
        validated_at=datetime(2026, 8, 11, 13, 0, tzinfo=timezone.utc),
        **PIPELINE_COMPATIBILITY,
    )
    return IngestTargetRepository(session).configure_spa(
        name=f"task012-spa-{marker}",
        timezone="Asia/Dushanbe",
        serving_pipeline_revision_id=revision.id,
    )


def _remove_fixture_rows(
    engine: Engine,
    *,
    spa_id: uuid.UUID,
    pipeline_revision_id: uuid.UUID,
) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "DELETE FROM face_moment.photo_pipeline_states "
            "WHERE pipeline_revision_id = %s",
            (pipeline_revision_id,),
        )
        connection.exec_driver_sql(
            "DELETE FROM face_moment.photos WHERE spa_id = %s", (spa_id,)
        )
        connection.exec_driver_sql(
            "DELETE FROM face_moment.spas WHERE id = %s", (spa_id,)
        )
        connection.exec_driver_sql(
            "DELETE FROM face_moment.pipeline_revisions WHERE id = %s",
            (pipeline_revision_id,),
        )


def test_atomic_admission_commits_complete_pair_or_rolls_back_both_rows() -> None:
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    marker = uuid.uuid4().hex
    target: IngestTarget | None = None
    successful_photo_id: uuid.UUID | None = None

    try:
        with Session(engine) as session:
            target = _target(session, marker)
            session.commit()

        assert target is not None
        with Session(engine) as session:
            photo = AtomicPhotoAdmission(session).publish(
                ingest_target=target,
                uploader_id=uuid.uuid4(),
                candidate=_candidate(f"success-{marker}"),
            )
            successful_photo_id = photo.id

        with Session(engine) as session:
            photos = session.scalars(
                select(Photo).where(Photo.spa_id == target.spa_id)
            ).all()
            pending_rows = session.scalars(
                select(PhotoPipelineState).where(
                    PhotoPipelineState.pipeline_revision_id == target.pipeline_revision_id
                )
            ).all()
            assert [photo.id for photo in photos] == [successful_photo_id]
            assert photos[0].accepted_at is not None
            assert [(row.photo_id, row.status, row.attempt_count) for row in pending_rows] == [
                (successful_photo_id, "pending", 0)
            ]
            assert pending_rows[0].status_changed_at is not None

        with pytest.raises(RuntimeError, match="injected-pre-commit-failure"):
            with Session(engine) as session:
                _InjectedPreCommitFailure(session).publish(
                    ingest_target=target,
                    uploader_id=uuid.uuid4(),
                    candidate=_candidate(f"rollback-{marker}"),
                )

        with Session(engine) as session:
            photos_after_rollback = session.scalars(
                select(Photo).where(Photo.spa_id == target.spa_id)
            ).all()
            pending_after_rollback = session.scalars(
                select(PhotoPipelineState).where(
                    PhotoPipelineState.pipeline_revision_id == target.pipeline_revision_id
                )
            ).all()
            assert [photo.id for photo in photos_after_rollback] == [successful_photo_id]
            assert [row.photo_id for row in pending_after_rollback] == [successful_photo_id]
    finally:
        if target is not None:
            _remove_fixture_rows(
                engine,
                spa_id=target.spa_id,
                pipeline_revision_id=target.pipeline_revision_id,
            )
        engine.dispose()

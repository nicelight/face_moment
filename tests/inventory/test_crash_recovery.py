from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.admission import AdmissionCandidate, AtomicPhotoAdmission
from face_moment.inventory.candidate_staging import CandidateStager, StagedCandidate
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource, ValidatedJpegCandidate
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.serving_control import IngestTarget, IngestTargetRepository


class _InjectedPreCommitCrash(AtomicPhotoAdmission):
    def _after_pending_before_commit(self) -> None:
        raise RuntimeError("task-014-injected-pre-commit-crash")


def _target(session: Session, marker: str) -> IngestTarget:
    revision = PipelineRevisionRepository(session).publish_eligible(
        pipeline_code=PipelineCode.OPENCV_SFACE,
        validated_at=datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc),
    )
    return IngestTargetRepository(session).configure_spa(
        name=f"task014-spa-{marker}",
        timezone="Asia/Dushanbe",
        serving_pipeline_revision_id=revision.id,
    )


def _candidate(stager: CandidateStager, payload: bytes) -> AdmissionCandidate:
    staged_candidate = stager.stage(payload)
    return AdmissionCandidate(
        staged_candidate=staged_candidate,
        validated_jpeg=ValidatedJpegCandidate(
            original_bytes=payload,
            checksum_sha256=hashlib.sha256(payload).digest(),
            byte_size=len(payload),
            width=12,
            height=10,
            visit_date=date(2026, 8, 11),
            captured_at=datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc),
            captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
            warning=None,
        ),
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


def test_precommit_crash_keeps_orphan_private_and_reupload_admits_once() -> None:
    settings = Settings.from_env()
    ensure_bucket(settings)
    object_store = PrivateObjectStore(settings)
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    marker = uuid.uuid4().hex
    prefix = f"task014/{marker}"
    target: IngestTarget | None = None
    crash_stager: CandidateStager | None = None
    retry_stager: CandidateStager | None = None
    crash_candidate: StagedCandidate | None = None
    retry_candidate: StagedCandidate | None = None

    try:
        with Session(engine) as session:
            target = _target(session, marker)
            session.commit()

        payload = f"task014-reupload-{marker}".encode()
        crash_stager = CandidateStager(object_store, key_prefix=f"{prefix}/crash")
        crashed_admission = _candidate(crash_stager, payload)
        crash_candidate = crashed_admission.staged_candidate

        with pytest.raises(RuntimeError, match="task-014-injected-pre-commit-crash"):
            with Session(engine) as session:
                _InjectedPreCommitCrash(session).publish(
                    ingest_target=target,
                    uploader_id=uuid.uuid4(),
                    candidate=crashed_admission,
                )

        with Session(engine) as session:
            crashed_photos = session.scalars(
                select(Photo).where(Photo.spa_id == target.spa_id)
            ).all()
            crashed_pending = session.scalars(
                select(PhotoPipelineState).where(
                    PhotoPipelineState.pipeline_revision_id == target.pipeline_revision_id
                )
            ).all()
        assert crashed_photos == []
        assert crashed_pending == []
        assert object_store.list_keys(prefix=prefix) == {crash_candidate.key}

        retry_stager = CandidateStager(object_store, key_prefix=f"{prefix}/retry")
        retry_admission = _candidate(retry_stager, payload)
        retry_candidate = retry_admission.staged_candidate
        with Session(engine) as session:
            admitted = AtomicPhotoAdmission(session).publish(
                ingest_target=target,
                uploader_id=uuid.uuid4(),
                candidate=retry_admission,
            )
            admitted_id = admitted.id

        with Session(engine) as session:
            photos = session.scalars(
                select(Photo).where(Photo.spa_id == target.spa_id)
            ).all()
            pending = session.scalars(
                select(PhotoPipelineState).where(
                    PhotoPipelineState.pipeline_revision_id == target.pipeline_revision_id
                )
            ).all()
        assert [photo.id for photo in photos] == [admitted_id]
        assert [(row.photo_id, row.status, row.attempt_count) for row in pending] == [
            (admitted_id, "pending", 0)
        ]
        assert {photo.original_object_key for photo in photos} == {retry_candidate.key}
        assert object_store.list_keys(prefix=prefix) == {
            crash_candidate.key,
            retry_candidate.key,
        }
    finally:
        if crash_stager is not None and crash_candidate is not None:
            crash_stager.cleanup(crash_candidate)
        if retry_stager is not None and retry_candidate is not None:
            retry_stager.cleanup(retry_candidate)
        if target is not None:
            _remove_fixture_rows(
                engine,
                spa_id=target.spa_id,
                pipeline_revision_id=target.pipeline_revision_id,
            )
        engine.dispose()

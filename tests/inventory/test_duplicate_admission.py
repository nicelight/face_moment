from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
from threading import Barrier
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.admission import (
    AdmissionCandidate,
    AdmissionResult,
    AtomicPhotoAdmission,
)
from face_moment.inventory.candidate_staging import CandidateStager, StagedCandidate
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource, ValidatedJpegCandidate
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.serving_control import IngestTarget, IngestTargetRepository


@dataclass(frozen=True, slots=True)
class _RequestCandidate:
    stager: CandidateStager
    candidate: AdmissionCandidate


def _target(session: Session, marker: str) -> IngestTarget:
    revision = PipelineRevisionRepository(session).publish_eligible(
        pipeline_code=PipelineCode.OPENCV_SFACE,
        validated_at=datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc),
    )
    return IngestTargetRepository(session).configure_spa(
        name=f"task013-spa-{marker}",
        timezone="Asia/Dushanbe",
        serving_pipeline_revision_id=revision.id,
    )


def _request_candidate(
    *,
    object_store: PrivateObjectStore,
    marker: str,
    payload: bytes,
) -> _RequestCandidate:
    stager = CandidateStager(object_store, key_prefix=f"task013/{marker}")
    staged_candidate = stager.stage(payload)
    validated = ValidatedJpegCandidate(
        original_bytes=payload,
        checksum_sha256=hashlib.sha256(payload).digest(),
        byte_size=len(payload),
        width=12,
        height=10,
        visit_date=date(2026, 8, 11),
        captured_at=datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc),
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        warning=None,
    )
    return _RequestCandidate(
        stager=stager,
        candidate=AdmissionCandidate(
            staged_candidate=staged_candidate,
            validated_jpeg=validated,
        ),
    )


def _admit(
    *,
    engine: Engine,
    target: IngestTarget,
    request_candidate: _RequestCandidate,
) -> AdmissionResult:
    with Session(engine) as session:
        return AtomicPhotoAdmission(session).admit(
            ingest_target=target,
            uploader_id=uuid.uuid4(),
            candidate=request_candidate.candidate,
            cleanup_losing_candidate=request_candidate.stager.cleanup,
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


def test_duplicate_admission_uses_database_winner_and_cleans_only_loser() -> None:
    settings = Settings.from_env()
    ensure_bucket(settings)
    object_store = PrivateObjectStore(settings)
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    marker = uuid.uuid4().hex
    target: IngestTarget | None = None
    staged_requests: list[_RequestCandidate] = []

    try:
        with Session(engine) as session:
            target = _target(session, marker)
            session.commit()

        sequential_payload = f"task013-sequential-{marker}".encode()
        sequential_requests = [
            _request_candidate(
                object_store=object_store,
                marker=f"{marker}/sequential-{position}",
                payload=sequential_payload,
            )
            for position in range(2)
        ]
        staged_requests.extend(sequential_requests)
        sequential_results = [
            _admit(engine=engine, target=target, request_candidate=request_candidate)
            for request_candidate in sequential_requests
        ]

        concurrent_payload = f"task013-concurrent-{marker}".encode()
        concurrent_requests = [
            _request_candidate(
                object_store=object_store,
                marker=f"{marker}/concurrent-{position}",
                payload=concurrent_payload,
            )
            for position in range(2)
        ]
        staged_requests.extend(concurrent_requests)
        start = Barrier(2)

        def admit_after_start(request_candidate: _RequestCandidate) -> AdmissionResult:
            start.wait()
            return _admit(
                engine=engine,
                target=target,
                request_candidate=request_candidate,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent_results = list(executor.map(admit_after_start, concurrent_requests))

        for results in (sequential_results, concurrent_results):
            assert sorted(result.outcome for result in results) == ["accepted", "duplicate"]
            assert sum(result.photo is not None for result in results) == 1
            duplicate_request = next(
                request_candidate
                for request_candidate, result in zip(
                    sequential_requests if results is sequential_results else concurrent_requests,
                    results,
                    strict=True,
                )
                if result.outcome == "duplicate"
            )
            duplicate_key = duplicate_request.candidate.staged_candidate.key
            assert duplicate_key not in object_store.list_keys(prefix=f"task013/{marker}/")
            duplicate_request.stager.cleanup(duplicate_request.candidate.staged_candidate)
            assert duplicate_key not in object_store.list_keys(prefix=f"task013/{marker}/")

        with Session(engine) as session:
            photos = session.scalars(
                select(Photo).where(Photo.spa_id == target.spa_id)
            ).all()
            pending_rows = session.scalars(
                select(PhotoPipelineState).where(
                    PhotoPipelineState.pipeline_revision_id
                    == target.pipeline_revision_id
                )
            ).all()

        admitted_keys = {photo.original_object_key for photo in photos}
        staged_keys = {
            request_candidate.candidate.staged_candidate.key
            for request_candidate in staged_requests
        }
        assert len(photos) == 2
        assert len(pending_rows) == 2
        assert {row.photo_id for row in pending_rows} == {photo.id for photo in photos}
        assert admitted_keys <= staged_keys
        assert object_store.list_keys(prefix=f"task013/{marker}/") == admitted_keys
    finally:
        for request_candidate in staged_requests:
            request_candidate.stager.cleanup(request_candidate.candidate.staged_candidate)
        if target is not None:
            _remove_fixture_rows(
                engine,
                spa_id=target.spa_id,
                pipeline_revision_id=target.pipeline_revision_id,
            )
        engine.dispose()

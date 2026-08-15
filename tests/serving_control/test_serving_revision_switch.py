from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
from threading import Event, Thread, current_thread
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.inventory.admission import AdmissionCandidate, AtomicPhotoAdmission
from face_moment.inventory.candidate_staging import StagedCandidate
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource, ValidatedJpegCandidate
from face_moment.processing import (
    InitialPendingRepository,
    PipelineCode,
    PipelineRevisionRepository,
)
from face_moment.processing import serving_revision_guard as processing_guard_module
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import ProcessingRuntimeStatus
from face_moment.processing.revisions import PipelineRevision
from face_moment.serving_control import IngestTargetRepository
from face_moment.serving_control.ingest_target import IngestTarget, Spa
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY

_FIXTURE_TIME = datetime(2026, 8, 14, 17, 0, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class _Fixture:
    database_name: str
    spa_id: uuid.UUID
    revision_a_id: uuid.UUID
    revision_b_id: uuid.UUID
    ineligible_revision_id: uuid.UUID
    target_a: IngestTarget


def _candidate(marker: str) -> AdmissionCandidate:
    original_bytes = f"task040-{marker}".encode()
    return AdmissionCandidate(
        staged_candidate=StagedCandidate(key=f"private/task-040/{marker}/original.jpg"),
        validated_jpeg=ValidatedJpegCandidate(
            original_bytes=original_bytes,
            checksum_sha256=hashlib.sha256(original_bytes).digest(),
            byte_size=len(original_bytes),
            width=12,
            height=10,
            visit_date=date(2026, 8, 14),
            captured_at=_FIXTURE_TIME,
            captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
            warning=None,
        ),
    )


def _add_photo(
    session: Session,
    *,
    spa_id: uuid.UUID,
    revision_id: uuid.UUID,
    marker: str,
    status: str = "pending",
) -> uuid.UUID:
    payload = f"task040-photo-{marker}".encode()
    photo = Photo(
        spa_id=spa_id,
        visit_date=date(2026, 8, 14),
        captured_at=_FIXTURE_TIME,
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        accepted_at=_FIXTURE_TIME,
        admission_pipeline_revision_id=revision_id,
        uploader_id=uuid.uuid4(),
        checksum_sha256=hashlib.sha256(payload).digest(),
        original_object_key=f"private/task-040/{marker}/original.jpg",
        original_byte_size=len(payload),
        width=12,
        height=10,
        is_active=True,
    )
    session.add(photo)
    session.flush()
    state = InitialPendingRepository(session).create_initial_pending(
        photo_id=photo.id,
        pipeline_revision_id=revision_id,
    )
    state.status = status
    state.status_changed_at = _FIXTURE_TIME
    session.flush()
    return photo.id


def _fixture(engine: Engine, database_name: str) -> _Fixture:
    marker = uuid.uuid4().hex
    with Session(engine) as session:
        revision_a = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=_FIXTURE_TIME,
            **PIPELINE_COMPATIBILITY,
        )
        revision_b = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
            validated_at=_FIXTURE_TIME,
            **PIPELINE_COMPATIBILITY,
        )
        ineligible_revision = PipelineRevision(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=None,
            detector_id="task040-detector",
            detector_version="task040-detector-v1",
            recognizer_id="task040-recognizer",
            recognizer_version="task040-recognizer-v1",
            weights_sha256="0" * 64,
            preprocessing_version="task040-preprocessing-v1",
            alignment_version="task040-alignment-v1",
            normalization_version="task040-normalization-v1",
            embedding_dimension=128,
        )
        session.add(ineligible_revision)
        session.flush()
        ineligible_revision_id = ineligible_revision.id
        target = IngestTargetRepository(session).configure_spa(
            name=f"task040-spa-{marker}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=revision_a.id,
        )
        session.commit()

    return _Fixture(
        database_name=database_name,
        spa_id=target.spa_id,
        revision_a_id=revision_a.id,
        revision_b_id=revision_b.id,
        ineligible_revision_id=ineligible_revision_id,
        target_a=target,
    )


def _snapshot(
    session: Session,
    *,
    spa_id: uuid.UUID,
    revision_ids: tuple[uuid.UUID, ...],
) -> tuple[object, ...]:
    spa_rows = tuple(
        session.execute(
            select(Spa.id, Spa.active, Spa.serving_pipeline_revision_id).where(
                Spa.id == spa_id
            )
        )
    )
    photo_rows = tuple(
        session.execute(
            select(
                Photo.id,
                Photo.spa_id,
                Photo.admission_pipeline_revision_id,
                Photo.checksum_sha256,
                Photo.original_object_key,
                Photo.is_active,
            )
            .where(Photo.spa_id == spa_id)
            .order_by(Photo.id)
        )
    )
    photo_ids = [row[0] for row in photo_rows]
    state_rows = tuple(
        session.execute(
            select(
                PhotoPipelineState.photo_id,
                PhotoPipelineState.pipeline_revision_id,
                PhotoPipelineState.status,
                PhotoPipelineState.attempt_count,
                PhotoPipelineState.status_changed_at,
                PhotoPipelineState.searchable_at,
                PhotoPipelineState.last_error,
                PhotoPipelineState.preview_object_key,
                PhotoPipelineState.thumbnail_object_key,
            )
            .where(PhotoPipelineState.photo_id.in_(photo_ids or [uuid.uuid4()]))
            .order_by(
                PhotoPipelineState.photo_id,
                PhotoPipelineState.pipeline_revision_id,
            )
        )
    )
    revision_rows = tuple(
        session.execute(
            select(PipelineRevision.id, PipelineRevision.validated_at)
            .where(PipelineRevision.id.in_(revision_ids))
            .order_by(PipelineRevision.id)
        )
    )
    runtime_rows = tuple(
        session.execute(
            select(
                ProcessingRuntimeStatus.singleton_id,
                ProcessingRuntimeStatus.current_operation,
                ProcessingRuntimeStatus.operation_started_at,
            )
        )
    )
    return spa_rows, photo_rows, state_rows, revision_rows, runtime_rows


def _remove_fixture_rows(engine: Engine, fixture: _Fixture) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM face_moment.photo_pipeline_states "
                "WHERE photo_id IN (SELECT id FROM face_moment.photos WHERE spa_id = :spa_id)"
            ),
            {"spa_id": fixture.spa_id},
        )
        connection.execute(
            text("DELETE FROM face_moment.photos WHERE spa_id = :spa_id"),
            {"spa_id": fixture.spa_id},
        )
        connection.execute(
            text("DELETE FROM face_moment.spas WHERE id = :spa_id"),
            {"spa_id": fixture.spa_id},
        )
        connection.execute(
            text(
                "DELETE FROM face_moment.pipeline_revisions "
                "WHERE id IN (:revision_a, :revision_b, :revision_ineligible)"
            ),
            {
                "revision_a": fixture.revision_a_id,
                "revision_b": fixture.revision_b_id,
                "revision_ineligible": fixture.ineligible_revision_id,
            },
        )


def test_manual_switch_validates_guards_and_serializes_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_settings = Settings.from_env()
    database_name = f"task040_{uuid.uuid4().hex}"
    probe_url = make_url(base_settings.database_url).set(database=database_name)
    admin_engine = create_engine(
        base_settings.database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {database_name}"))
    monkeypatch.setenv("DATABASE_URL", probe_url.render_as_string(hide_password=False))
    engine = create_engine(probe_url, pool_pre_ping=True)
    fixture: _Fixture | None = None

    validation_events: list[tuple[str, uuid.UUID]] = []
    guard_events: list[tuple[str, uuid.UUID]] = []
    original_validate = PipelineRevisionRepository.resolve_eligible
    original_guard = processing_guard_module.read_serving_revision_guard

    def trace_validation(
        repository: PipelineRevisionRepository,
        revision_id: uuid.UUID,
    ) -> object:
        validation_events.append(("target_validation", revision_id))
        return original_validate(repository, revision_id)

    def trace_guard(
        session: Session,
        *,
        spa_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> object:
        guard_events.append(("exact_a_guard", pipeline_revision_id))
        return original_guard(
            session,
            spa_id=spa_id,
            pipeline_revision_id=pipeline_revision_id,
        )

    monkeypatch.setattr(PipelineRevisionRepository, "resolve_eligible", trace_validation)
    monkeypatch.setattr(processing_guard_module, "read_serving_revision_guard", trace_guard)

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        fixture = _fixture(engine, database_name)

        unknown_revision_id = uuid.uuid4()
        for requested_revision_id, expected_events in (
            (unknown_revision_id, [("target_validation", unknown_revision_id)]),
            (
                fixture.ineligible_revision_id,
                [("target_validation", fixture.ineligible_revision_id)],
            ),
        ):
            validation_events.clear()
            guard_events.clear()
            with Session(engine) as session:
                before = _snapshot(
                    session,
                    spa_id=fixture.spa_id,
                    revision_ids=(
                        fixture.revision_a_id,
                        fixture.revision_b_id,
                        fixture.ineligible_revision_id,
                    ),
                )
            with Session(engine) as session:
                result = IngestTargetRepository(session).switch_serving_revision(
                    spa_id=fixture.spa_id,
                    target_pipeline_revision_id=requested_revision_id,
                )
            with Session(engine) as session:
                after = _snapshot(
                    session,
                    spa_id=fixture.spa_id,
                    revision_ids=(
                        fixture.revision_a_id,
                        fixture.revision_b_id,
                        fixture.ineligible_revision_id,
                    ),
                )
            assert result.outcome == "rejected"
            assert result.reason == "target_invalid"
            assert result.requested_pipeline_revision_id == requested_revision_id
            assert result.committed_pipeline_revision_id == fixture.revision_a_id
            assert before == after
            assert validation_events == expected_events
            assert guard_events == []

        with Session(engine) as session:
            blocked_photo_id = _add_photo(
                session,
                spa_id=fixture.spa_id,
                revision_id=fixture.revision_a_id,
                marker="blocked",
            )
            session.commit()

        validation_events.clear()
        guard_events.clear()
        with Session(engine) as session:
            before = _snapshot(
                session,
                spa_id=fixture.spa_id,
                revision_ids=(
                    fixture.revision_a_id,
                    fixture.revision_b_id,
                    fixture.ineligible_revision_id,
                ),
            )
        with Session(engine) as session:
            result = IngestTargetRepository(session).switch_serving_revision(
                spa_id=fixture.spa_id,
                target_pipeline_revision_id=fixture.revision_b_id,
            )
        with Session(engine) as session:
            after = _snapshot(
                session,
                spa_id=fixture.spa_id,
                revision_ids=(
                    fixture.revision_a_id,
                    fixture.revision_b_id,
                    fixture.ineligible_revision_id,
                ),
            )
        assert result.outcome == "rejected"
        assert result.reason == "current_revision_has_active_processing"
        assert result.requested_pipeline_revision_id == fixture.revision_b_id
        assert result.committed_pipeline_revision_id == fixture.revision_a_id
        assert before == after
        assert validation_events == [("target_validation", fixture.revision_b_id)]
        assert guard_events == [("exact_a_guard", fixture.revision_a_id)]

        with Session(engine) as session:
            blocked_state = session.get(
                PhotoPipelineState,
                (blocked_photo_id, fixture.revision_a_id),
            )
            assert blocked_state is not None
            blocked_state.status = "ready"
            blocked_state.status_changed_at = _FIXTURE_TIME
            session.commit()

        validation_events.clear()
        guard_events.clear()
        with Session(engine) as session:
            result = IngestTargetRepository(session).switch_serving_revision(
                spa_id=fixture.spa_id,
                target_pipeline_revision_id=fixture.revision_b_id,
            )
        assert result.outcome == "committed"
        assert result.reason == "committed"
        assert result.requested_pipeline_revision_id == fixture.revision_b_id
        assert result.committed_pipeline_revision_id == fixture.revision_b_id
        assert validation_events == [("target_validation", fixture.revision_b_id)]
        assert guard_events == [("exact_a_guard", fixture.revision_a_id)]

        with Session(engine) as session:
            revert = IngestTargetRepository(session).switch_serving_revision(
                spa_id=fixture.spa_id,
                target_pipeline_revision_id=fixture.revision_a_id,
            )
        assert revert.outcome == "committed"

        admission_locked = Event()
        release_admission = Event()
        switch_started = Event()
        admission_photo_ids: list[uuid.UUID] = []
        switch_results: list[object] = []
        thread_errors: list[BaseException] = []
        original_lock = IngestTargetRepository.lock_ingest_target

        def hold_admission_lock(
            repository: IngestTargetRepository,
            locked_spa_id: uuid.UUID,
        ) -> IngestTarget:
            target = original_lock(repository, locked_spa_id)
            if current_thread().name == "task040-admission":
                admission_locked.set()
                if not release_admission.wait(timeout=5):
                    raise AssertionError("admission lock release timed out")
            return target

        monkeypatch.setattr(
            IngestTargetRepository,
            "lock_ingest_target",
            hold_admission_lock,
        )

        with Session(engine) as session:
            admission_target = IngestTargetRepository(session).resolve_ingest_target(
                fixture.spa_id
            )

        def admit_under_lock() -> None:
            try:
                with Session(engine) as session:
                    photo = AtomicPhotoAdmission(session).publish(
                        ingest_target=admission_target,
                        uploader_id=uuid.uuid4(),
                        candidate=_candidate("interleaved"),
                    )
                    admission_photo_ids.append(photo.id)
            except BaseException as error:
                thread_errors.append(error)

        def switch_while_admission_holds_lock() -> None:
            switch_started.set()
            try:
                with Session(engine) as session:
                    switch_results.append(
                        IngestTargetRepository(session).switch_serving_revision(
                            spa_id=fixture.spa_id,
                            target_pipeline_revision_id=fixture.revision_b_id,
                        )
                    )
            except BaseException as error:
                thread_errors.append(error)

        admission_thread = Thread(
            target=admit_under_lock,
            name="task040-admission",
        )
        switch_thread = Thread(
            target=switch_while_admission_holds_lock,
            name="task040-switch",
        )
        admission_thread.start()
        assert admission_locked.wait(timeout=5)
        switch_thread.start()
        assert switch_started.wait(timeout=5)
        release_admission.set()
        admission_thread.join(timeout=10)
        switch_thread.join(timeout=10)
        assert not admission_thread.is_alive()
        assert not switch_thread.is_alive()
        assert thread_errors == []
        assert len(admission_photo_ids) == 1
        assert len(switch_results) == 1
        interleaved_result = switch_results[0]
        assert interleaved_result.outcome == "rejected"
        assert interleaved_result.reason == "current_revision_has_active_processing"
        assert interleaved_result.committed_pipeline_revision_id == fixture.revision_a_id

        with Session(engine) as session:
            admitted_photo = session.get(Photo, admission_photo_ids[0])
            assert admitted_photo is not None
            assert admitted_photo.admission_pipeline_revision_id == fixture.revision_a_id
            admitted_state = session.get(
                PhotoPipelineState,
                (admission_photo_ids[0], fixture.revision_a_id),
            )
            assert admitted_state is not None
            assert admitted_state.status == "pending"
            committed_spa = session.get(Spa, fixture.spa_id)
            assert committed_spa is not None
            assert committed_spa.serving_pipeline_revision_id == fixture.revision_a_id
    finally:
        if fixture is not None:
            _remove_fixture_rows(engine, fixture)
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE {database_name}"))
        admin_engine.dispose()

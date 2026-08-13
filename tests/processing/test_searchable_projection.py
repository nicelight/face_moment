from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import uuid

from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource
from face_moment.processing import (
    InitialPendingRepository,
    PipelineCode,
    PipelineRevisionRepository,
)
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace, ProcessingRuntimeStatus
from face_moment.processing.searchable_projection import SearchableProjectionRepository
from face_moment.serving_control import IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


@dataclass(frozen=True, slots=True)
class _Fixture:
    cases: tuple[tuple[str, uuid.UUID, uuid.UUID], ...]
    pipeline_revision_ids: tuple[uuid.UUID, ...]
    spa_id: uuid.UUID


def _runtime_snapshot(engine: Engine) -> tuple[object, ...]:
    with Session(engine) as session:
        runtime = session.get(ProcessingRuntimeStatus, 1)
        assert runtime is not None
        return (
            runtime.worker_started_at,
            runtime.last_recovery_at,
            runtime.last_recovered_count,
            runtime.current_operation,
            runtime.operation_started_at,
        )


def _add_state(
    session: Session,
    *,
    marker: str,
    spa_id: uuid.UUID,
    pipeline_revision_id: uuid.UUID,
    status: str,
    is_active: bool = True,
    has_preview: bool = True,
    has_thumbnail: bool = True,
    has_face: bool = True,
) -> PhotoPipelineState:
    photo = Photo(
        spa_id=spa_id,
        visit_date=date(2026, 8, 13),
        captured_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
        captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
        uploader_id=uuid.uuid4(),
        checksum_sha256=hashlib.sha256(marker.encode()).digest(),
        original_object_key=f"private/task-027/{marker}/original.jpg",
        original_byte_size=123,
        width=12,
        height=10,
        is_active=is_active,
    )
    session.add(photo)
    session.flush()
    state = InitialPendingRepository(session).create_initial_pending(
        photo_id=photo.id,
        pipeline_revision_id=pipeline_revision_id,
    )
    state.status = status
    state.preview_object_key = (
        f"private/task-027/{marker}/preview.jpg" if has_preview else None
    )
    state.thumbnail_object_key = (
        f"private/task-027/{marker}/thumbnail.jpg" if has_thumbnail else None
    )
    if has_face:
        session.add(
            PhotoFace(
                photo_id=photo.id,
                pipeline_revision_id=pipeline_revision_id,
                face_index=0,
                bbox_x=1.0,
                bbox_y=1.0,
                bbox_w=4.0,
                bbox_h=4.0,
                landmarks_json=[[1.0, 1.0]] * 5,
                detection_confidence=0.9,
                embedding=[1.0] + [0.0] * 127,
            )
        )
    session.flush()
    return state


def _fixture(engine: Engine) -> _Fixture:
    marker = uuid.uuid4().hex
    with Session(engine) as session:
        current_revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
            **PIPELINE_COMPATIBILITY,
        )
        other_revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
            validated_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
            **PIPELINE_COMPATIBILITY,
        )
        target = IngestTargetRepository(session).configure_spa(
            name=f"task-027-{marker}",
            timezone="Asia/Dushanbe",
            serving_pipeline_revision_id=current_revision.id,
        )
        cases = (
            ("eligible", current_revision.id, "ready", True, True, True, True),
            ("inactive", current_revision.id, "ready", False, True, True, True),
            ("incompatible", other_revision.id, "ready", True, True, True, True),
            ("missing-preview", current_revision.id, "ready", True, False, True, True),
            ("missing-thumbnail", current_revision.id, "ready", True, True, False, True),
            ("missing-face", current_revision.id, "ready", True, True, True, False),
            ("pending", current_revision.id, "pending", True, True, True, True),
            ("processing", current_revision.id, "processing", True, True, True, True),
            ("no-faces", current_revision.id, "no_faces", True, True, True, False),
            ("failed", current_revision.id, "failed", True, True, True, True),
        )
        states = tuple(
            _add_state(
                session,
                marker=f"{case}-{marker}",
                spa_id=target.spa_id,
                pipeline_revision_id=revision_id,
                status=status,
                is_active=is_active,
                has_preview=has_preview,
                has_thumbnail=has_thumbnail,
                has_face=has_face,
            )
            for (
                case,
                revision_id,
                status,
                is_active,
                has_preview,
                has_thumbnail,
                has_face,
            ) in cases
        )
        session.commit()
        return _Fixture(
            cases=tuple(
                (case[0], state.photo_id, state.pipeline_revision_id)
                for case, state in zip(cases, states, strict=True)
            ),
            pipeline_revision_ids=(current_revision.id, other_revision.id),
            spa_id=target.spa_id,
        )


def _cleanup(engine: Engine, fixture: _Fixture) -> None:
    with engine.begin() as connection:
        for _case, photo_id, _pipeline_revision_id in fixture.cases:
            connection.exec_driver_sql(
                "DELETE FROM face_moment.photo_faces WHERE photo_id = %s",
                (photo_id,),
            )
            connection.exec_driver_sql(
                "DELETE FROM face_moment.photo_pipeline_states WHERE photo_id = %s",
                (photo_id,),
            )
            connection.exec_driver_sql(
                "DELETE FROM face_moment.photos WHERE id = %s", (photo_id,)
            )
        connection.exec_driver_sql(
            "DELETE FROM face_moment.spas WHERE id = %s", (fixture.spa_id,)
        )
        for pipeline_revision_id in fixture.pipeline_revision_ids:
            connection.exec_driver_sql(
                "DELETE FROM face_moment.pipeline_revisions WHERE id = %s",
                (pipeline_revision_id,),
            )


def test_searchable_projection_requires_complete_current_active_ready_state() -> None:
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    fixture: _Fixture | None = None
    runtime_baseline = _runtime_snapshot(engine)

    try:
        alembic_command.upgrade(Config("alembic.ini"), "head")
        fixture = _fixture(engine)
        with Session(engine) as session:
            repository = SearchableProjectionRepository(session)
            projections = {
                case: repository.resolve(
                    photo_id=photo_id,
                    pipeline_revision_id=pipeline_revision_id,
                )
                for case, photo_id, pipeline_revision_id in fixture.cases
            }

        assert len(projections) == 10
        assert all(projection is not None for projection in projections.values())
        eligible = projections["eligible"]
        assert eligible is not None
        assert eligible.searchable is True
        assert eligible.processing_status == "ready"
        assert eligible.photo_is_active is True
        assert eligible.is_current_serving_revision is True
        assert eligible.has_complete_derivatives is True
        assert eligible.has_valid_face is True
        negative = tuple(
            projection
            for case, projection in projections.items()
            if case != "eligible"
        )
        assert all(projection is not None for projection in negative)
        resolved_negative = tuple(
            projection for projection in negative if projection is not None
        )
        assert all(not projection.searchable for projection in resolved_negative)
        assert {projection.processing_status for projection in resolved_negative} == {
            "ready",
            "pending",
            "processing",
            "no_faces",
            "failed",
        }
        inactive = projections["inactive"]
        incompatible = projections["incompatible"]
        assert inactive is not None
        assert inactive.photo_is_active is False
        assert inactive.is_current_serving_revision is True
        assert incompatible is not None
        assert incompatible.photo_is_active is True
        assert incompatible.is_current_serving_revision is False
        assert projections["missing-preview"] is not None
        assert projections["missing-preview"].has_complete_derivatives is False
        assert projections["missing-thumbnail"] is not None
        assert projections["missing-thumbnail"].has_complete_derivatives is False
        assert projections["missing-face"] is not None
        assert projections["missing-face"].has_valid_face is False
    finally:
        if fixture is not None:
            _cleanup(engine, fixture)
        assert _runtime_snapshot(engine) == runtime_baseline
        engine.dispose()

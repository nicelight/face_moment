from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.admission import AdmissionCandidate, AtomicPhotoAdmission
from face_moment.inventory.candidate_staging import StagedCandidate
from face_moment.inventory.photo_persistence import Photo
from face_moment.inventory.validation import CapturedAtSource, ValidatedJpegCandidate
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.serving_control import IngestTarget, IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY

_PRE_LINEAGE_REVISION = "0008_processing_persistence"
_LINEAGE_REVISION = "0009_photo_admission_lineage"


class _InjectedPreCommitFailure(AtomicPhotoAdmission):
    def _after_pending_before_commit(self) -> None:
        raise RuntimeError("task-037-injected-pre-commit-failure")


def _config() -> Config:
    return Config("alembic.ini")


def _reset_to_pre_lineage() -> None:
    alembic_command.downgrade(_config(), "base")
    alembic_command.upgrade(_config(), _PRE_LINEAGE_REVISION)


def _photo_snapshot(engine: Engine) -> tuple[object, ...]:
    inspector = inspect(engine)
    columns = tuple(
        (column["name"], str(column["type"]), column["nullable"], column["default"])
        for column in inspector.get_columns("photos", schema=APP_SCHEMA)
    )
    with engine.connect() as connection:
        photos = tuple(
            connection.execute(
                text(
                    "SELECT id, spa_id, visit_date, original_object_key "
                    "FROM face_moment.photos ORDER BY id"
                )
            ).all()
        )
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
    return columns, photos, version


def _insert_pre_lineage_photo(engine: Engine) -> None:
    revision_id = uuid.uuid4()
    spa_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO face_moment.pipeline_revisions
                    (id, pipeline_code, detector_id, detector_version,
                     recognizer_id, recognizer_version, weights_sha256,
                     preprocessing_version, alignment_version,
                     normalization_version, embedding_dimension, validated_at)
                VALUES (:id, 'opencv_sface', 'detector', 'detector-v1',
                        'recognizer', 'recognizer-v1', :weights_sha256,
                        'preprocessing-v1', 'alignment-v1',
                        'normalization-v1', 128, CURRENT_TIMESTAMP)
                """
            ),
            {"id": revision_id, "weights_sha256": "0" * 64},
        )
        connection.execute(
            text(
                """
                INSERT INTO face_moment.spas
                    (id, name, timezone, serving_pipeline_revision_id)
                VALUES (:id, :name, 'Asia/Dushanbe', :revision_id)
                """
            ),
            {
                "id": spa_id,
                "name": f"task037-pre-lineage-{spa_id.hex}",
                "revision_id": revision_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO face_moment.photos
                    (id, spa_id, visit_date, captured_at, captured_at_source,
                     uploader_id, checksum_sha256, original_object_key,
                     original_byte_size, width, height)
                VALUES (:id, :spa_id, DATE '2026-08-14', CURRENT_TIMESTAMP,
                        'upload_started_at', :uploader_id,
                        decode('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'hex'),
                        :object_key, 1, 1, 1)
                """
            ),
            {
                "id": photo_id,
                "spa_id": spa_id,
                "uploader_id": uuid.uuid4(),
                "object_key": f"private/task037-pre-lineage-{photo_id.hex}",
            },
        )


def _candidate(marker: str) -> AdmissionCandidate:
    original_bytes = f"task-037-{marker}".encode()
    return AdmissionCandidate(
        staged_candidate=StagedCandidate(key=f"private/task-037-{marker}"),
        validated_jpeg=ValidatedJpegCandidate(
            original_bytes=original_bytes,
            checksum_sha256=hashlib.sha256(original_bytes).digest(),
            byte_size=len(original_bytes),
            width=12,
            height=10,
            visit_date=date(2026, 8, 14),
            captured_at=datetime(2026, 8, 14, 4, 0, tzinfo=timezone.utc),
            captured_at_source=CapturedAtSource.UPLOAD_STARTED_AT,
            warning=None,
        ),
    )


def _target(session: Session, marker: str) -> IngestTarget:
    revision = PipelineRevisionRepository(session).publish_eligible(
        pipeline_code=PipelineCode.OPENCV_SFACE,
        validated_at=datetime(2026, 8, 14, 4, 0, tzinfo=timezone.utc),
        **PIPELINE_COMPATIBILITY,
    )
    return IngestTargetRepository(session).configure_spa(
        name=f"task037-spa-{marker}",
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
        connection.execute(
            text(
                "DELETE FROM face_moment.photo_pipeline_states "
                "WHERE pipeline_revision_id = :pipeline_revision_id"
            ),
            {"pipeline_revision_id": pipeline_revision_id},
        )
        connection.execute(
            text("DELETE FROM face_moment.photos WHERE spa_id = :spa_id"),
            {"spa_id": spa_id},
        )
        connection.execute(
            text("DELETE FROM face_moment.spas WHERE id = :spa_id"),
            {"spa_id": spa_id},
        )
        connection.execute(
            text("DELETE FROM face_moment.pipeline_revisions WHERE id = :revision_id"),
            {"revision_id": pipeline_revision_id},
        )


def test_nonempty_photo_cutover_aborts_before_schema_or_data_mutation() -> None:
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)

    try:
        _reset_to_pre_lineage()
        _insert_pre_lineage_photo(engine)
        before = _photo_snapshot(engine)

        with pytest.raises(RuntimeError, match="photos must be empty"):
            alembic_command.upgrade(_config(), "head")

        assert _photo_snapshot(engine) == before
    finally:
        alembic_command.downgrade(_config(), "base")
        alembic_command.upgrade(_config(), "head")
        engine.dispose()


def test_empty_cutover_round_trip_adds_exact_nonnull_restrict_lineage_shape() -> None:
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)

    try:
        _reset_to_pre_lineage()
        alembic_command.upgrade(_config(), "head")

        script = ScriptDirectory.from_config(_config())
        head = script.get_revision("head")
        assert head is not None
        assert head.revision == _LINEAGE_REVISION
        assert head.down_revision == _PRE_LINEAGE_REVISION
        assert tuple(script.get_heads()) == (_LINEAGE_REVISION,)

        inspector = inspect(engine)
        lineage_column = next(
            column
            for column in inspector.get_columns("photos", schema=APP_SCHEMA)
            if column["name"] == "admission_pipeline_revision_id"
        )
        assert lineage_column["nullable"] is False
        assert any(
            foreign_key["constrained_columns"] == ["admission_pipeline_revision_id"]
            and foreign_key["referred_schema"] == APP_SCHEMA
            and foreign_key["referred_table"] == "pipeline_revisions"
            and foreign_key["referred_columns"] == ["id"]
            and foreign_key["options"].get("ondelete") == "RESTRICT"
            for foreign_key in inspector.get_foreign_keys("photos", schema=APP_SCHEMA)
        )

        alembic_command.downgrade(_config(), _PRE_LINEAGE_REVISION)
        downgraded_columns = {
            column["name"]
            for column in inspect(engine).get_columns("photos", schema=APP_SCHEMA)
        }
        assert "admission_pipeline_revision_id" not in downgraded_columns

        alembic_command.upgrade(_config(), "head")
        reupgraded_columns = {
            column["name"]
            for column in inspect(engine).get_columns("photos", schema=APP_SCHEMA)
        }
        assert "admission_pipeline_revision_id" in reupgraded_columns
    finally:
        alembic_command.downgrade(_config(), "base")
        alembic_command.upgrade(_config(), "head")
        engine.dispose()


def test_atomic_admission_persists_exact_lineage_pair_or_rolls_back_both() -> None:
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    marker = uuid.uuid4().hex
    target: IngestTarget | None = None
    successful_photo_id: uuid.UUID | None = None

    try:
        alembic_command.upgrade(_config(), "head")
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
            assert photo.admission_pipeline_revision_id == target.pipeline_revision_id

        with Session(engine) as session:
            photos = session.scalars(
                select(Photo).where(Photo.spa_id == target.spa_id)
            ).all()
            pending_rows = session.scalars(
                select(PhotoPipelineState).where(
                    PhotoPipelineState.photo_id == successful_photo_id
                )
            ).all()
            assert [photo.id for photo in photos] == [successful_photo_id]
            assert [
                (photo.id, photo.admission_pipeline_revision_id) for photo in photos
            ] == [(successful_photo_id, target.pipeline_revision_id)]
            assert [
                (state.photo_id, state.pipeline_revision_id, state.status, state.attempt_count)
                for state in pending_rows
            ] == [(successful_photo_id, target.pipeline_revision_id, "pending", 0)]

        with pytest.raises(RuntimeError, match="task-037-injected-pre-commit-failure"):
            with Session(engine) as session:
                _InjectedPreCommitFailure(session).publish(
                    ingest_target=target,
                    uploader_id=uuid.uuid4(),
                    candidate=_candidate(f"rollback-{marker}"),
                )

        with Session(engine) as session:
            assert session.scalars(
                select(Photo).where(Photo.spa_id == target.spa_id)
            ).all() == [
                session.get(Photo, successful_photo_id)
            ]
            assert session.scalars(
                select(PhotoPipelineState).where(
                    PhotoPipelineState.photo_id == successful_photo_id
                )
            ).all()[0].pipeline_revision_id == target.pipeline_revision_id
    finally:
        if target is not None:
            _remove_fixture_rows(
                engine,
                spa_id=target.spa_id,
                pipeline_revision_id=target.pipeline_revision_id,
            )
        engine.dispose()

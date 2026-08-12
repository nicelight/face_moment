from __future__ import annotations

import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings

_PRE_CUTOVER_REVISION = "0007_photo_pipeline_pending"


def _config() -> Config:
    return Config("alembic.ini")


def _reset_to_pre_cutover() -> None:
    alembic_command.downgrade(_config(), "base")
    alembic_command.upgrade(_config(), _PRE_CUTOVER_REVISION)


def _snapshot(engine: Engine) -> tuple[object, ...]:
    inspector = inspect(engine)
    tables = tuple(sorted(inspector.get_table_names(schema=APP_SCHEMA)))
    columns = tuple(
        (column["name"], str(column["type"]), column["nullable"], column["default"])
        for column in inspector.get_columns("pipeline_revisions", schema=APP_SCHEMA)
    )
    with engine.connect() as connection:
        revisions = tuple(
            connection.execute(
                text(
                    "SELECT id, pipeline_code, created_at, validated_at "
                    "FROM face_moment.pipeline_revisions ORDER BY id"
                )
            ).all()
        )
        spa_references = tuple(
            connection.execute(
                text(
                    "SELECT id, serving_pipeline_revision_id "
                    "FROM face_moment.spas ORDER BY id"
                )
            ).all()
        )
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
    return tables, columns, revisions, spa_references, version


def test_legacy_pipeline_revision_aborts_before_compatibility_mutation() -> None:
    """No legacy revision, including a serving-referenced one, is backfilled."""

    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    revision_id = uuid.uuid4()
    spa_id = uuid.uuid4()

    try:
        _reset_to_pre_cutover()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO face_moment.pipeline_revisions (id, pipeline_code) "
                    "VALUES (:id, 'opencv_sface')"
                ),
                {"id": revision_id},
            )
            connection.execute(
                text(
                    "INSERT INTO face_moment.spas "
                    "(id, name, timezone, serving_pipeline_revision_id) "
                    "VALUES (:id, :name, 'Asia/Dushanbe', :revision_id)"
                ),
                {
                    "id": spa_id,
                    "name": f"task018-legacy-{spa_id.hex}",
                    "revision_id": revision_id,
                },
            )

        before = _snapshot(engine)
        with pytest.raises(RuntimeError, match="pipeline_revisions must be empty"):
            alembic_command.upgrade(_config(), "head")
        assert _snapshot(engine) == before
    finally:
        alembic_command.downgrade(_config(), "base")
        alembic_command.upgrade(_config(), "head")
        engine.dispose()


def test_empty_cutover_round_trip_preserves_prerequisite_rows_and_shape() -> None:
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    staff_id = uuid.uuid4()
    expected_pipeline_columns = {
        "id",
        "pipeline_code",
        "created_at",
        "validated_at",
        "detector_id",
        "detector_version",
        "recognizer_id",
        "recognizer_version",
        "weights_sha256",
        "preprocessing_version",
        "alignment_version",
        "normalization_version",
        "embedding_dimension",
    }
    expected_state_columns = {
        "photo_id",
        "pipeline_revision_id",
        "status",
        "attempt_count",
        "status_changed_at",
        "searchable_at",
        "last_error",
        "preview_object_key",
        "thumbnail_object_key",
    }

    try:
        _reset_to_pre_cutover()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO face_moment.staff_users "
                    "(id, username, password_hash, role) "
                    "VALUES (:id, :username, 'hash', 'developer')"
                ),
                {"id": staff_id, "username": f"task018-{staff_id.hex}"},
            )

        alembic_command.upgrade(_config(), "head")
        script = ScriptDirectory.from_config(_config())
        head = script.get_revision("head")
        assert head is not None
        assert head.down_revision == _PRE_CUTOVER_REVISION
        assert tuple(script.get_heads()) == (head.revision,)

        inspector = inspect(engine)
        assert {
            column["name"]
            for column in inspector.get_columns("pipeline_revisions", schema=APP_SCHEMA)
        } == expected_pipeline_columns
        assert {
            column["name"]
            for column in inspector.get_columns("photo_pipeline_states", schema=APP_SCHEMA)
        } == expected_state_columns
        with engine.connect() as connection:
            photo_face_columns = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'face_moment' AND table_name = 'photo_faces'"
                    )
                )
            }
        assert photo_face_columns == {
            "id",
            "photo_id",
            "pipeline_revision_id",
            "face_index",
            "bbox_x",
            "bbox_y",
            "bbox_w",
            "bbox_h",
            "landmarks_json",
            "detection_confidence",
            "quality_score",
            "blur_score",
            "brightness_score",
            "pose_yaw",
            "pose_pitch",
            "pose_roll",
            "embedding",
            "created_at",
        }
        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    "SELECT udt_name FROM information_schema.columns "
                    "WHERE table_schema = 'face_moment' AND table_name = 'photo_faces' "
                    "AND column_name = 'embedding'"
                )
            ) == "vector"
        assert {
            column["name"]
            for column in inspector.get_columns(
                "processing_runtime_status", schema=APP_SCHEMA
            )
        } == {
            "singleton_id",
            "worker_started_at",
            "last_recovery_at",
            "last_recovered_count",
            "current_operation",
            "operation_started_at",
        }
        assert {
            check["name"]
            for check in inspector.get_check_constraints(
                "pipeline_revisions", schema=APP_SCHEMA
            )
        } >= {
            "ck_pipeline_revisions_detector_id_present",
            "ck_pipeline_revisions_detector_version_present",
            "ck_pipeline_revisions_recognizer_id_present",
            "ck_pipeline_revisions_recognizer_version_present",
            "ck_pipeline_revisions_weights_sha256",
            "ck_pipeline_revisions_preprocessing_version_present",
            "ck_pipeline_revisions_alignment_version_present",
            "ck_pipeline_revisions_normalization_version_present",
            "ck_pipeline_revisions_embedding_dimension_positive",
        }
        assert {
            check["name"]
            for check in inspector.get_check_constraints(
                "photo_faces", schema=APP_SCHEMA
            )
        } >= {
            "ck_photo_faces_bbox_w_positive",
            "ck_photo_faces_bbox_h_positive",
            "ck_photo_faces_required_values_finite",
        }
        assert {
            check["name"]
            for check in inspector.get_check_constraints(
                "processing_runtime_status", schema=APP_SCHEMA
            )
        } >= {
            "ck_processing_runtime_status_singleton",
            "ck_processing_runtime_status_recovered_count_nonnegative",
            "ck_processing_runtime_status_operation",
            "ck_processing_runtime_status_operation_started_at",
        }
        assert inspector.get_pk_constraint(
            "photo_pipeline_states", schema=APP_SCHEMA
        )["constrained_columns"] == ["photo_id", "pipeline_revision_id"]
        assert any(
            constraint["column_names"]
            == ["photo_id", "pipeline_revision_id", "face_index"]
            for constraint in inspector.get_unique_constraints(
                "photo_faces", schema=APP_SCHEMA
            )
        )
        for table_name in ("photo_pipeline_states", "photo_faces"):
            assert all(
                foreign_key["options"].get("ondelete") == "RESTRICT"
                for foreign_key in inspector.get_foreign_keys(
                    table_name, schema=APP_SCHEMA
                )
            )
        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT username FROM face_moment.staff_users WHERE id = :id"),
                {"id": staff_id},
            ) == f"task018-{staff_id.hex}"
            assert connection.execute(
                text(
                    "SELECT singleton_id, current_operation, last_recovered_count "
                    "FROM face_moment.processing_runtime_status"
                )
            ).one() == (1, "idle", 0)

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
                    "name": f"task018-compatible-{spa_id.hex}",
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
                    VALUES (:id, :spa_id, DATE '2026-08-12', CURRENT_TIMESTAMP,
                            'upload_started_at', :uploader_id,
                            decode('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'hex'),
                            :object_key, 1, 1, 1)
                    """
                ),
                {
                    "id": photo_id,
                    "spa_id": spa_id,
                    "uploader_id": uuid.uuid4(),
                    "object_key": f"private/task018-{photo_id.hex}",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO face_moment.photo_pipeline_states
                        (photo_id, pipeline_revision_id)
                    VALUES (:photo_id, :revision_id)
                    """
                ),
                {"photo_id": photo_id, "revision_id": revision_id},
            )

        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with pytest.raises(DBAPIError, match="compatibility identity"):
                    connection.execute(
                        text(
                            "UPDATE face_moment.pipeline_revisions "
                            "SET detector_id = 'replacement' WHERE id = :id"
                        ),
                        {"id": revision_id},
                    )
            finally:
                transaction.rollback()

        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with pytest.raises(DBAPIError, match="embedding dimension"):
                    connection.execute(
                        text(
                            """
                            INSERT INTO face_moment.photo_faces
                                (id, photo_id, pipeline_revision_id, face_index,
                                 bbox_x, bbox_y, bbox_w, bbox_h, landmarks_json,
                                 detection_confidence, embedding)
                            VALUES (:id, :photo_id, :revision_id, 0,
                                    0, 0, 1, 1, '[]'::json, 0.9,
                                    '[1,2]'::vector)
                            """
                        ),
                        {
                            "id": uuid.uuid4(),
                            "photo_id": photo_id,
                            "revision_id": revision_id,
                        },
                    )
            finally:
                transaction.rollback()

        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM face_moment.photo_pipeline_states "
                    "WHERE photo_id = :photo_id"
                ),
                {"photo_id": photo_id},
            )
            connection.execute(
                text("DELETE FROM face_moment.photos WHERE id = :photo_id"),
                {"photo_id": photo_id},
            )
            connection.execute(
                text("DELETE FROM face_moment.spas WHERE id = :spa_id"),
                {"spa_id": spa_id},
            )
            connection.execute(
                text(
                    "DELETE FROM face_moment.pipeline_revisions WHERE id = :revision_id"
                ),
                {"revision_id": revision_id},
            )

        alembic_command.downgrade(_config(), _PRE_CUTOVER_REVISION)
        assert "photo_faces" not in inspect(engine).get_table_names(schema=APP_SCHEMA)
        alembic_command.upgrade(_config(), "head")
        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT username FROM face_moment.staff_users WHERE id = :id"),
                {"id": staff_id},
            ) == f"task018-{staff_id.hex}"
    finally:
        alembic_command.downgrade(_config(), "base")
        alembic_command.upgrade(_config(), "head")
        engine.dispose()

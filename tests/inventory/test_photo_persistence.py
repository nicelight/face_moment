from __future__ import annotations

from datetime import date, datetime, timezone
import importlib
import uuid

from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


def _migration_round_trip(engine: object) -> None:
    alembic_config = Config("alembic.ini")
    alembic_command.downgrade(alembic_config, "0005_serving_ingest_targets")
    assert "photos" not in inspect(engine).get_table_names(schema=APP_SCHEMA)
    alembic_command.upgrade(alembic_config, "head")
    assert "photos" in inspect(engine).get_table_names(schema=APP_SCHEMA)


def test_inventory_exposes_only_photo_identity_persistence() -> None:
    try:
        photo_persistence = importlib.import_module(
            "face_moment.inventory.photo_persistence"
        )
    except ModuleNotFoundError as error:
        raise AssertionError(
            "inventory has no Photo identity persistence boundary"
        ) from error

    assert hasattr(photo_persistence, "Photo"), (
        "inventory has no Photo identity persistence model"
    )
    assert hasattr(photo_persistence, "PhotoIdentityRepository"), (
        "inventory has no Photo identity lookup repository"
    )

    Photo = photo_persistence.Photo
    PhotoIdentityRepository = photo_persistence.PhotoIdentityRepository
    from face_moment.processing import PipelineCode, PipelineRevisionRepository
    from face_moment.serving_control import IngestTargetRepository

    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    photo_id: uuid.UUID | None = None
    pipeline_revision_id: uuid.UUID | None = None
    marker = uuid.uuid4().hex
    spa_id = uuid.uuid4()
    uploader_id = uuid.uuid4()
    checksum = bytes.fromhex("ab" * 32)
    visit_date = date(2026, 8, 11)

    try:
        _migration_round_trip(engine)

        table = Photo.__table__
        assert set(table.columns.keys()) == {
            "id",
            "spa_id",
            "visit_date",
            "captured_at",
            "captured_at_source",
            "accepted_at",
            "uploader_id",
            "checksum_sha256",
            "original_object_key",
            "original_byte_size",
            "width",
            "height",
            "is_active",
        }
        assert not any(
            name in table.columns
            for name in ("batch_id", "manifest_id", "confirmed_at", "purge_state")
        )
        assert not hasattr(PhotoIdentityRepository, "admit")
        assert not hasattr(PhotoIdentityRepository, "create")

        schema = inspect(engine)
        columns = {column["name"]: column for column in schema.get_columns("photos", schema=APP_SCHEMA)}
        assert set(columns) == set(table.columns.keys())
        assert any(
            "octet_length(checksum_sha256) = 32" in constraint["sqltext"]
            for constraint in schema.get_check_constraints("photos", schema=APP_SCHEMA)
        )
        assert columns["original_object_key"]["nullable"] is False
        assert columns["original_byte_size"]["nullable"] is False
        assert columns["width"]["nullable"] is False
        assert columns["height"]["nullable"] is False
        assert columns["captured_at"]["type"].timezone is True
        assert columns["accepted_at"]["type"].timezone is True
        assert any(
            set(constraint["column_names"]) == {"spa_id", "visit_date", "checksum_sha256"}
            for constraint in schema.get_unique_constraints("photos", schema=APP_SCHEMA)
        )
        foreign_keys = schema.get_foreign_keys("photos", schema=APP_SCHEMA)
        assert all(foreign_key["constrained_columns"] != ["uploader_id"] for foreign_key in foreign_keys)
        assert any(
            foreign_key["constrained_columns"] == ["spa_id"]
            and foreign_key["referred_table"] == "spas"
            and foreign_key["options"].get("ondelete") == "RESTRICT"
            for foreign_key in foreign_keys
        )

        with Session(engine) as session:
            pipeline_revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc),
                **PIPELINE_COMPATIBILITY,
            )
            pipeline_revision_id = pipeline_revision.id
            ingest_target = IngestTargetRepository(session).configure_spa(
                name=f"task008-spa-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=pipeline_revision.id,
            )
            spa_id = ingest_target.spa_id
            photo = Photo(
                spa_id=spa_id,
                visit_date=visit_date,
                captured_at=datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc),
                captured_at_source="upload_started_at",
                accepted_at=datetime(2026, 8, 11, 9, 1, tzinfo=timezone.utc),
                uploader_id=uploader_id,
                checksum_sha256=checksum,
                original_object_key=f"private/task-008-{marker}",
                original_byte_size=123,
                width=12,
                height=10,
                is_active=True,
            )
            session.add(photo)
            session.flush()
            photo_id = photo.id

            resolved = PhotoIdentityRepository(session).find_by_identity(
                spa_id=spa_id,
                visit_date=visit_date,
                checksum_sha256=checksum,
            )
            assert resolved is photo
            assert resolved.id == photo_id
            assert PhotoIdentityRepository(session).find_by_identity(
                spa_id=spa_id,
                visit_date=date(2026, 8, 10),
                checksum_sha256=checksum,
            ) is None
            session.commit()

        with engine.begin() as connection:
            connection.exec_driver_sql(
                "DELETE FROM face_moment.photos WHERE id = %s", (photo_id,)
            )
            connection.exec_driver_sql(
                "DELETE FROM face_moment.spas WHERE id = %s", (spa_id,)
            )
            connection.exec_driver_sql(
                "DELETE FROM face_moment.pipeline_revisions WHERE id = %s",
                (pipeline_revision_id,),
            )
        _migration_round_trip(engine)
    finally:
        engine.dispose()

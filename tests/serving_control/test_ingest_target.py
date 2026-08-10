from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import importlib
import uuid

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from face_moment.infrastructure.database import APP_SCHEMA
from face_moment.infrastructure.settings import Settings


def _migration_round_trip(engine: object) -> None:
    alembic_config = Config("alembic.ini")
    alembic_command.downgrade(alembic_config, "0004_staff_sessions")
    assert "spas" not in inspect(engine).get_table_names(schema=APP_SCHEMA)
    alembic_command.upgrade(alembic_config, "head")
    assert "spas" in inspect(engine).get_table_names(schema=APP_SCHEMA)


def test_serving_control_publishes_only_valid_immutable_ingest_targets() -> None:
    try:
        serving_control = importlib.import_module("face_moment.serving_control")
    except ModuleNotFoundError as error:
        raise AssertionError(
            "serving_control cannot publish an immutable ingest target through "
            "its owner-backed boundary"
        ) from error

    assert hasattr(serving_control, "IngestTargetRepository"), (
        "serving_control cannot publish an immutable ingest target through "
        "its owner-backed boundary"
    )

    from face_moment.processing import PipelineCode, PipelineRevisionRepository
    from face_moment.serving_control import (
        InactiveIngestTargetError,
        IneligibleIngestTargetError,
        IngestTargetRepository,
        InvalidIngestTargetTimezoneError,
        UnknownIngestTargetError,
    )
    from face_moment.serving_control.ingest_target import Spa

    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    eligible_revision_id: uuid.UUID | None = None
    ineligible_revision_id = uuid.uuid4()
    inactive_spa_id = uuid.uuid4()
    invalid_timezone_spa_id = uuid.uuid4()
    ineligible_spa_id = uuid.uuid4()
    configured_spa_id: uuid.UUID | None = None
    validated_at = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    marker = uuid.uuid4().hex

    try:
        _migration_round_trip(engine)

        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=validated_at,
            )
            eligible_revision_id = revision.id
            repository = IngestTargetRepository(session)
            target = repository.configure_spa(
                name=f"task007-spa-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            configured_spa_id = target.spa_id
            session.commit()

        assert target.spa_id == configured_spa_id
        assert target.name == f"task007-spa-{marker}"
        assert target.timezone == "Asia/Dushanbe"
        assert target.pipeline_revision_id == eligible_revision_id
        with pytest.raises(FrozenInstanceError):
            setattr(target, "timezone", "Europe/Paris")

        with Session(engine) as session:
            repository = IngestTargetRepository(session)
            resolved = repository.resolve_ingest_target(configured_spa_id)
            assert resolved == target
            with pytest.raises(UnknownIngestTargetError):
                repository.resolve_ingest_target(uuid.uuid4())

        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO face_moment.pipeline_revisions
                        (id, pipeline_code, validated_at)
                    VALUES (:id, 'opencv_sface', NULL)
                    """
                ),
                {"id": ineligible_revision_id},
            )

        with Session(engine) as session:
            session.add_all(
                [
                    Spa(
                        id=inactive_spa_id,
                        name=f"task007-inactive-{marker}",
                        timezone="Asia/Dushanbe",
                        active=False,
                        serving_pipeline_revision_id=eligible_revision_id,
                    ),
                    Spa(
                        id=invalid_timezone_spa_id,
                        name=f"task007-invalid-timezone-{marker}",
                        timezone="Not/A_Timezone",
                        active=True,
                        serving_pipeline_revision_id=eligible_revision_id,
                    ),
                    Spa(
                        id=ineligible_spa_id,
                        name=f"task007-ineligible-{marker}",
                        timezone="Asia/Dushanbe",
                        active=True,
                        serving_pipeline_revision_id=ineligible_revision_id,
                    ),
                ]
            )
            session.commit()

        with Session(engine) as session:
            repository = IngestTargetRepository(session)
            with pytest.raises(InactiveIngestTargetError):
                repository.resolve_ingest_target(inactive_spa_id)
            with pytest.raises(InvalidIngestTargetTimezoneError):
                repository.resolve_ingest_target(invalid_timezone_spa_id)
            with pytest.raises(IneligibleIngestTargetError):
                repository.resolve_ingest_target(ineligible_spa_id)

        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with pytest.raises(DBAPIError):
                    connection.execute(
                        text(
                            "DELETE FROM face_moment.pipeline_revisions "
                            "WHERE id = :id"
                        ),
                        {"id": eligible_revision_id},
                    )
            finally:
                transaction.rollback()

        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM face_moment.spas WHERE id = ANY(:ids)"),
                {
                    "ids": [
                        configured_spa_id,
                        inactive_spa_id,
                        invalid_timezone_spa_id,
                        ineligible_spa_id,
                    ]
                },
            )
            connection.execute(
                text(
                    "DELETE FROM face_moment.pipeline_revisions "
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": [eligible_revision_id, ineligible_revision_id]},
            )

        _migration_round_trip(engine)
    finally:
        engine.dispose()

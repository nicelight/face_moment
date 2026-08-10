from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
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
    alembic_command.downgrade(alembic_config, "0002_staff_users")
    assert "pipeline_revisions" not in inspect(engine).get_table_names(
        schema=APP_SCHEMA
    )
    alembic_command.upgrade(alembic_config, "head")
    assert "pipeline_revisions" in inspect(engine).get_table_names(
        schema=APP_SCHEMA
    )


def test_processing_publishes_only_immutable_eligible_revisions() -> None:
    from face_moment import processing

    assert hasattr(processing, "PipelineRevisionRepository"), (
        "processing cannot publish an immutable eligible revision without the "
        "task-owned repository boundary"
    )

    from face_moment.processing import (
        IneligiblePipelineRevisionError,
        PipelineCode,
        PipelineRevisionRepository,
        UnsupportedPipelineCodeError,
    )

    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    eligible_ids: list[uuid.UUID] = []
    ineligible_id = uuid.uuid4()
    validated_at = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)

    try:
        _migration_round_trip(engine)

        with Session(engine) as session:
            repository = PipelineRevisionRepository(session)
            for pipeline_code in PipelineCode:
                revision = repository.publish_eligible(
                    pipeline_code=pipeline_code,
                    validated_at=validated_at,
                )
                eligible_ids.append(revision.id)
                assert revision.pipeline_code is pipeline_code
                assert revision.validated_at == validated_at
                assert revision.created_at is not None
            session.commit()

        with Session(engine) as session:
            repository = PipelineRevisionRepository(session)
            for revision_id in eligible_ids:
                resolved = repository.resolve_eligible(revision_id)
                assert resolved.id == revision_id
                assert resolved.validated_at == validated_at
            with pytest.raises(UnsupportedPipelineCodeError):
                repository.publish_eligible(
                    pipeline_code=cast(PipelineCode, "unsupported"),
                    validated_at=validated_at,
                )

        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO face_moment.pipeline_revisions
                        (id, pipeline_code, validated_at)
                    VALUES (:id, 'opencv_sface', NULL)
                    """
                ),
                {"id": ineligible_id},
            )

        with Session(engine) as session:
            repository = PipelineRevisionRepository(session)
            with pytest.raises(IneligiblePipelineRevisionError):
                repository.resolve_eligible(ineligible_id)

        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with pytest.raises(DBAPIError, match="immutable"):
                    connection.execute(
                        text(
                            """
                            UPDATE face_moment.pipeline_revisions
                            SET validated_at = :changed_at
                            WHERE id = :id
                            """
                        ),
                        {
                            "changed_at": datetime(
                                2026, 8, 11, 10, 0, tzinfo=timezone.utc
                            ),
                            "id": eligible_ids[0],
                        },
                    )
            finally:
                transaction.rollback()

        _migration_round_trip(engine)
    finally:
        engine.dispose()

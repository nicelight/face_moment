"""Regression coverage for the shared disposable PostgreSQL lifecycle."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from face_moment.infrastructure.settings import Settings
from tests.disposable_postgresql import disposable_postgresql_engine


def test_disposable_database_is_removed_and_environment_restored_after_failure() -> None:
    base_url = Settings.from_env().database_url
    database_prefix = f"shared_fixture_{uuid.uuid4().hex}"
    previous_url = os.environ.get("DATABASE_URL")

    with pytest.raises(RuntimeError, match="synthetic test failure"):
        with disposable_postgresql_engine(database_prefix) as engine:
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT 1")) == 1
            assert os.environ.get("DATABASE_URL") != previous_url
            raise RuntimeError("synthetic test failure")

    assert os.environ.get("DATABASE_URL") == previous_url
    admin_engine = create_engine(
        base_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    try:
        with admin_engine.connect() as connection:
            remaining = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_database "
                    "WHERE datname LIKE :database_pattern"
                ),
                {"database_pattern": f"{database_prefix}_%"},
            )
        assert remaining == 0
    finally:
        admin_engine.dispose()

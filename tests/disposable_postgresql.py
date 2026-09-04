"""Shared lifecycle for isolated PostgreSQL-backed tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
import uuid

from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url

from face_moment.infrastructure.settings import Settings


@contextmanager
def disposable_postgresql_engine(database_prefix: str) -> Iterator[Engine]:
    """Create, migrate, and forcibly remove one isolated test database."""

    base_url = Settings.from_env().database_url
    database_name = f"{database_prefix}_{uuid.uuid4().hex}"
    probe_url = make_url(base_url).set(database=database_name)
    admin_engine = create_engine(
        base_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    engine: Engine | None = None
    database_created = False
    previous_url = os.environ.get("DATABASE_URL")

    try:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"CREATE DATABASE {database_name}")
        database_created = True
        os.environ["DATABASE_URL"] = probe_url.render_as_string(hide_password=False)
        engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
        alembic_command.upgrade(Config("alembic.ini"), "head")
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        try:
            if database_created:
                with admin_engine.connect() as connection:
                    connection.exec_driver_sql(
                        f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)"
                    )
        finally:
            admin_engine.dispose()

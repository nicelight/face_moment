from __future__ import annotations

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.engine import Engine

APP_SCHEMA = "face_moment"


class Base(DeclarativeBase):
    metadata = MetaData(schema=APP_SCHEMA)


def create_realtime_database_engine(database_url: str, *, deadline_ms: int) -> Engine:
    """Bound realtime I/O only; background jobs keep their existing policy."""
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_timeout=3,
        connect_args={
            "connect_timeout": 3,
            "tcp_user_timeout": deadline_ms,
            "options": f"-c statement_timeout={deadline_ms} -c lock_timeout=3000",
        },
    )


def assert_database_ready(database_url: str) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()

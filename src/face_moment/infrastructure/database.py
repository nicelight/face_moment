from __future__ import annotations

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase

APP_SCHEMA = "face_moment"


class Base(DeclarativeBase):
    metadata = MetaData(schema=APP_SCHEMA)


def assert_database_ready(database_url: str) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()


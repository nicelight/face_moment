"""Thin HTTP transport for inventory-owned staff reads."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Cookie, FastAPI, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.inventory.ingest_targets import (
    InvalidSessionError,
    IngestTargetContext,
    PhotographerAccessDeniedError,
    read_ingest_target_context,
)


def register_ingest_target_routes(app: FastAPI) -> None:
    @app.get("/api/inventory/ingest-targets", response_model=None)
    def ingest_targets(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> IngestTargetContext:
        with _database_session(Settings.from_env()) as database_session:
            try:
                return read_ingest_target_context(
                    database_session,
                    session_token=fm_staff_session,
                )
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
            except PhotographerAccessDeniedError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error


@contextmanager
def _database_session(settings: Settings) -> Iterator[Session]:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as database_session:
            yield database_session
    finally:
        engine.dispose()

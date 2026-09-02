from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.diagnostics.http import (
    register_attempt_investigation_routes,
    register_server_event_search_routes,
)
from face_moment.entrypoints.common import create_role_app, run, server_event_lifecycle
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.http import register_ingest_target_routes
from face_moment.platform.auth.http import register_staff_session_routes
from face_moment.promo.http import (
    register_diagnostic_retention_routes,
    register_phone_continuation_routes,
    register_promo_display_routes,
)
from face_moment.serving_control.http import (
    register_active_search_date_routes,
    register_display_client_admin_routes,
)




def _client_root() -> Path:
    configured = os.environ.get("FACE_MOMENT_CLIENT_ROOT")
    if configured:
        return Path(configured)

    package_adjacent = Path(__file__).resolve().parents[3] / "client"
    if package_adjacent.is_dir():
        return package_adjacent

    return Path.cwd() / "client"


CLIENT_ROOT = _client_root()


@asynccontextmanager
async def _backend_lifecycle(
    settings: Settings, state: dict[str, Any]
) -> AsyncIterator[None]:
    database_engine = create_engine(settings.database_url, pool_pre_ping=True)
    state["session_factory"] = lambda: Session(database_engine)
    try:
        async with server_event_lifecycle(settings, state):
            yield
    finally:
        state.pop("session_factory", None)
        database_engine.dispose()


def create_app() -> FastAPI:
    app = create_role_app("backend", lifecycle=_backend_lifecycle)

    def session_factory() -> Session:
        factory = cast(
            Callable[[], Session], app.state.role_state["session_factory"]
        )
        return factory()

    register_staff_session_routes(app, session_factory=session_factory)
    register_attempt_investigation_routes(app, session_factory=session_factory)
    register_server_event_search_routes(app, session_factory=session_factory)
    register_ingest_target_routes(app, session_factory=session_factory)
    register_display_client_admin_routes(app, session_factory=session_factory)
    register_active_search_date_routes(app, session_factory=session_factory)
    register_promo_display_routes(app, session_factory=session_factory)
    register_diagnostic_retention_routes(app, session_factory=session_factory)
    register_phone_continuation_routes(
        app, client_root=CLIENT_ROOT, session_factory=session_factory
    )
    app.mount("/client", StaticFiles(directory=CLIENT_ROOT), name="promo-client-assets")

    @app.get("/", include_in_schema=False)
    def promo_client_shell() -> FileResponse:
        return FileResponse(CLIENT_ROOT / "index.html", media_type="text/html")

    return app


app = create_app()


def main() -> None:
    run(app, 8000)


if __name__ == "__main__":
    main()

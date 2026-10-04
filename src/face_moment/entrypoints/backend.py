from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import asyncio
import threading
import os
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.diagnostics.http import (
    register_attempt_investigation_routes,
    register_server_event_search_routes,
)
from face_moment.diagnostics.ground_truth_annotation_http import (
    register_ground_truth_annotation_routes,
)
from face_moment.diagnostics.capture_identity_http import register_capture_identity_routes
from face_moment.entrypoints.common import create_role_app, run, server_event_lifecycle
from face_moment.infrastructure.settings import Settings
from face_moment.infrastructure.archive_failure_mail import ArchiveFailureMail
from face_moment.promo.photo_archive_executor import PhotoArchiveExecutor
from face_moment.promo.photo_archive_http import register_photo_archive_route
from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.inventory.http import register_ingest_target_routes
from face_moment.inventory.staff_media_http import register_staff_media_routes
from face_moment.promo.advertising_http import register_advertising_routes
from face_moment.promo.public_search_http import register_public_result_routes
from face_moment.promo.photo_purchase_http import register_public_quote_route
from face_moment.promo.photo_order_http import register_public_order_routes
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from face_moment.platform.auth.http import register_staff_session_routes
from face_moment.platform.auth.environment import sync_staff_users_from_environment
from face_moment.promo.http import (
    register_diagnostic_retention_routes,
    register_phone_continuation_routes,
    register_promo_display_routes,
)
from face_moment.serving_control.http import (
    register_active_search_date_routes,
    register_public_search_settings_routes,
    register_photo_tariff_routes,
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
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="public-preview")
    state['public_quote_rate_limiter'] = DisplayClientRateLimiter(
        limit=int(os.environ.get("PUBLIC_SEARCH_RATE_LIMIT", "10")),
        window_seconds=int(os.environ.get("PUBLIC_SEARCH_RATE_WINDOW_SECONDS", "60")),
    )
    state['public_order_rate_limiter'] = DisplayClientRateLimiter(
        limit=int(os.environ.get("PUBLIC_SEARCH_RATE_LIMIT", "10")),
        window_seconds=int(os.environ.get("PUBLIC_SEARCH_RATE_WINDOW_SECONDS", "60")),
    )
    state.update(public_preview_executor=executor, public_preview_slot=threading.Lock(),
                 public_preview_store=PrivateObjectStore(settings))
    state["photo_archive_signing_secret"] = settings.photo_archive_signing_secret
    archive_executor = PhotoArchiveExecutor(
        lambda: Session(database_engine), PrivateObjectStore(settings), ArchiveFailureMail(settings),
    )
    try:
        with Session(database_engine) as database_session:
            sync_staff_users_from_environment(database_session)
        async with server_event_lifecycle(settings, state):
            await asyncio.to_thread(archive_executor.start)
            state["photo_archive_executor"] = archive_executor
            try:
                yield
            finally:
                await asyncio.to_thread(archive_executor.stop)
                state.pop("photo_archive_executor", None)
    finally:
        executor.shutdown(wait=True)
        for key in ("public_preview_executor", "public_preview_slot", "public_preview_store", "public_quote_rate_limiter", "public_order_rate_limiter"):
            state.pop(key, None)
        state.pop("photo_archive_signing_secret", None)
        state.pop("session_factory", None)
        database_engine.dispose()


def create_app() -> FastAPI:
    app = create_role_app("backend", lifecycle=_backend_lifecycle)

    def session_factory() -> Session:
        factory = cast(
            Callable[[], Session], app.state.role_state["session_factory"]
        )
        return factory()

    register_public_result_routes(app, session_factory=session_factory)
    register_public_quote_route(app, session_factory=session_factory)
    register_public_order_routes(app, session_factory=session_factory)
    register_photo_archive_route(app, session_factory=session_factory)
    register_staff_session_routes(app, session_factory=session_factory)
    register_attempt_investigation_routes(app, session_factory=session_factory)
    register_ground_truth_annotation_routes(app, session_factory=session_factory)
    @app.api_route("/staff/calibrations", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    @app.api_route("/staff/calibrations/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def disabled_calibration() -> JSONResponse:
        return JSONResponse({"detail": "Калибровка отключена. Порог сходства доступен в настройках площадки."},
                            status_code=410, headers={"Cache-Control": "no-store"})

    register_server_event_search_routes(app, session_factory=session_factory)
    register_ingest_target_routes(app, session_factory=session_factory)
    register_staff_media_routes(app, session_factory=session_factory)
    register_advertising_routes(app, session_factory=session_factory)
    register_capture_identity_routes(app, session_factory=session_factory)
    register_display_client_admin_routes(app, session_factory=session_factory)
    register_active_search_date_routes(app, session_factory=session_factory)
    register_public_search_settings_routes(app, session_factory=session_factory)
    register_photo_tariff_routes(app, session_factory=session_factory)
    register_promo_display_routes(app, session_factory=session_factory)
    register_diagnostic_retention_routes(app, session_factory=session_factory)
    register_phone_continuation_routes(
        app, client_root=CLIENT_ROOT, session_factory=session_factory
    )
    app.mount("/client", StaticFiles(directory=CLIENT_ROOT), name="promo-client-assets")

    @app.get("/client1", include_in_schema=False)
    @app.get("/display", include_in_schema=False)
    def promo_client_shell() -> FileResponse:
        return FileResponse(CLIENT_ROOT / "index.html", media_type="text/html")

    @app.get("/", include_in_schema=False)
    @app.get("/site", include_in_schema=False)
    def public_site() -> FileResponse:
        return FileResponse(CLIENT_ROOT / "site.html", media_type="text/html")

    return app


app = create_app()


def main() -> None:
    run(app, 8000)


if __name__ == "__main__":
    main()

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from face_moment.entrypoints.common import create_role_app, run
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


def create_app() -> FastAPI:
    app = create_role_app("backend")
    register_staff_session_routes(app)
    register_ingest_target_routes(app)
    register_display_client_admin_routes(app)
    register_active_search_date_routes(app)
    register_promo_display_routes(app)
    register_diagnostic_retention_routes(app)
    register_phone_continuation_routes(app, client_root=CLIENT_ROOT)
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

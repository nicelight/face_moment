from __future__ import annotations

from fastapi import FastAPI

from face_moment.entrypoints.common import create_role_app, run
from face_moment.inventory.http import register_ingest_target_routes
from face_moment.platform.auth.http import register_staff_session_routes


def create_app() -> FastAPI:
    app = create_role_app("backend")
    register_staff_session_routes(app)
    register_ingest_target_routes(app)
    return app


app = create_app()


def main() -> None:
    run(app, 8000)


if __name__ == "__main__":
    main()

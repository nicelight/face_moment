from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from face_moment.infrastructure.readiness import wait_for_dependencies
from face_moment.infrastructure.settings import Settings
from face_moment.processing.face_engine import FaceEngine


def create_role_app(
    role: str,
    *,
    engine: FaceEngine | None = None,
) -> FastAPI:
    state: dict[str, Any] = {"ready": False}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        settings = Settings.from_env()
        wait_for_dependencies(settings, require_bucket=True)
        if engine is not None:
            engine.warmup()
            if not engine.ready:
                raise RuntimeError("FaceEngine warmup did not reach readiness")
        state["ready"] = True
        try:
            yield
        finally:
            state["ready"] = False

    app = FastAPI(title=f"Face Moment {role}", lifespan=lifespan)

    @app.get("/healthz")
    def health() -> dict[str, object]:
        ready = bool(state["ready"])
        response: dict[str, object] = {"role": role, "ready": ready}
        if engine is not None:
            response.update(
                {
                    "engine": "fake",
                    "engine_ready": engine.ready,
                    "production_model_loaded": False,
                }
            )
        return response

    return app


def run(app: FastAPI, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port)


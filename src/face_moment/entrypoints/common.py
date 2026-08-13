from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager

from fastapi import FastAPI

from face_moment.infrastructure.readiness import wait_for_dependencies
from face_moment.infrastructure.settings import Settings
RoleLifecycle = Callable[[Settings, dict[str, Any]], AsyncContextManager[None]]


def create_role_app(
    role: str,
    *,
    lifecycle: RoleLifecycle | None = None,
) -> FastAPI:
    state: dict[str, Any] = {"ready": False}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        settings = Settings.from_env()
        wait_for_dependencies(settings, require_bucket=True)
        if lifecycle is None:
            state["ready"] = True
            try:
                yield
            finally:
                state["ready"] = False
            return

        async with lifecycle(settings, state):
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
        response.update(state.get("health", {}))
        return response

    return app


def run(app: FastAPI, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port)

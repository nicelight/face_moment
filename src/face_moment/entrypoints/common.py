from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from ipaddress import ip_address
import os
from typing import Any, AsyncContextManager

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.diagnostics import ServerEventEmitter
from face_moment.infrastructure.readiness import wait_for_dependencies
from face_moment.infrastructure.settings import Settings
RoleLifecycle = Callable[[Settings, dict[str, Any]], AsyncContextManager[None]]


@dataclass(slots=True)
class ServerEventBinding:
    database_engine: Engine
    emitter: ServerEventEmitter

    def close(self) -> None:
        self.emitter.stop()
        self.database_engine.dispose()


def bind_server_events(settings: Settings) -> ServerEventBinding:
    """Bind one process-local diagnostics writer to its isolated Sessions."""

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    emitter = ServerEventEmitter(
        lambda: Session(engine),
        release_id=os.environ.get("FACE_MOMENT_RELEASE_ID", "face-moment-runtime"),
    )
    emitter.start()
    return ServerEventBinding(database_engine=engine, emitter=emitter)


@asynccontextmanager
async def server_event_lifecycle(
    settings: Settings, state: dict[str, Any]
) -> AsyncIterator[None]:
    """Composition-only lifecycle adapter shared by backend and realtime."""

    binding = bind_server_events(settings)
    state["server_event_emitter"] = binding.emitter
    try:
        yield
    finally:
        state.pop("server_event_emitter", None)
        binding.close()


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
    app.state.role_state = state

    @app.get("/healthz")
    def health() -> dict[str, object]:
        ready = bool(state["ready"])
        response: dict[str, object] = {"role": role, "ready": ready}
        response.update(state.get("health", {}))
        return response

    return app


def run(app: FastAPI, port: int) -> None:
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips=_trusted_proxy_ip(),
    )


def _trusted_proxy_ip() -> str:
    raw_value = os.environ.get("FACE_MOMENT_TRUSTED_PROXY_IP", "127.0.0.1")
    try:
        return str(ip_address(raw_value.strip()))
    except ValueError as error:
        raise RuntimeError(
            "FACE_MOMENT_TRUSTED_PROXY_IP must be one exact IP address"
        ) from error

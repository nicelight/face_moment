from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from face_moment.entrypoints.common import create_role_app, run
from face_moment.entrypoints.model_consumers import bind_model_consumer
from face_moment.infrastructure.settings import Settings


@asynccontextmanager
async def _realtime_lifecycle(
    settings: Settings, state: dict[str, Any]
) -> AsyncIterator[None]:
    binding = bind_model_consumer(settings)
    state["health"] = {"production_model_loaded": True}
    try:
        yield
    finally:
        binding.close()


def create_app() -> FastAPI:
    return create_role_app("RealtimeFaceService", lifecycle=_realtime_lifecycle)


app = create_app()


def main() -> None:
    run(app, 8002)


if __name__ == "__main__":
    main()

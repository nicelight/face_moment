from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

from fastapi import FastAPI

from face_moment.entrypoints.common import create_role_app, run
from face_moment.entrypoints.model_consumers import bind_model_consumer
from face_moment.infrastructure.settings import Settings

if TYPE_CHECKING:
    from face_moment.processing.photo_orchestration import TerminalPhotoAdapter


async def _supervise_worker(
    *,
    worker: Any,
    stop_event: asyncio.Event,
    idle_seconds: float,
    state: dict[str, Any],
) -> None:
    try:
        await worker.run_until_stopped(
            stop_event=stop_event,
            idle_seconds=idle_seconds,
        )
        if not stop_event.is_set():
            raise RuntimeError("BackgroundPhotoWorker stopped unexpectedly")
    except BaseException:
        if not stop_event.is_set():
            state["ready"] = False
            health = state.setdefault("health", {})
            health["worker_loop_failed"] = True
        raise


@asynccontextmanager
async def _worker_lifecycle(
    settings: Settings, state: dict[str, Any]
) -> AsyncIterator[None]:
    binding = bind_model_consumer(settings)
    stop_event = asyncio.Event()
    try:
        from face_moment.infrastructure.object_store import PrivateObjectStore
        from face_moment.processing.derivatives import (
            DerivativeEncoding,
            DerivativeEncodingConfig,
            PrivatePhotoDerivativeCreator,
        )
        from face_moment.processing.photo_orchestration import PhotoProcessingOrchestrator
        from face_moment.processing.worker_runtime import BackgroundPhotoWorker

        adapter = cast("TerminalPhotoAdapter", binding.adapter)
        object_store = PrivateObjectStore(settings)
        orchestrator = PhotoProcessingOrchestrator(
            session_factory=binding.session_factory,
            object_store=object_store,
            sface_adapter=adapter,
            buffalo_adapter=adapter,
            derivative_creator=PrivatePhotoDerivativeCreator(
                object_store,
                encoding=DerivativeEncodingConfig(
                    preview=DerivativeEncoding(
                        maximum_edge=settings.photo_preview_maximum_edge,
                        jpeg_quality=settings.photo_preview_jpeg_quality,
                    ),
                    thumbnail=DerivativeEncoding(
                        maximum_edge=settings.photo_thumbnail_maximum_edge,
                        jpeg_quality=settings.photo_thumbnail_jpeg_quality,
                    ),
                ),
            ),
        )
        worker = BackgroundPhotoWorker(
            session_factory=binding.session_factory,
            orchestrator=orchestrator,
            bound_pipeline_revision_id=adapter.pipeline_revision_id,
        )
        recovered_count = await asyncio.to_thread(worker.recover_startup)
        state["health"] = {
            "production_model_loaded": True,
            "recovery_completed": True,
            "last_recovered_count": recovered_count,
        }
        async with asyncio.TaskGroup() as task_group:
            task_group.create_task(
                _supervise_worker(
                    worker=worker,
                    stop_event=stop_event,
                    idle_seconds=settings.background_worker_idle_seconds,
                    state=state,
                )
            )
            try:
                yield
            finally:
                stop_event.set()
    finally:
        stop_event.set()
        binding.close()


def create_app() -> FastAPI:
    return create_role_app("BackgroundPhotoWorker", lifecycle=_worker_lifecycle)


app = create_app()


def main() -> None:
    run(app, 8001)


if __name__ == "__main__":
    main()

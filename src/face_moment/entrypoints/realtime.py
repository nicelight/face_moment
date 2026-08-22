from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from ipaddress import ip_address
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from face_moment.entrypoints.common import create_role_app, run
from face_moment.entrypoints.model_consumers import bind_model_consumer
from face_moment.infrastructure.settings import (
    DEFAULT_REALTIME_DEADLINE_MS,
    Settings,
)
from face_moment.promo import PromoAttemptRepository, PromoAttemptNotFoundError
from face_moment.promo.realtime_admission import (
    RealtimeBodyTooLargeError,
    RealtimePayloadError,
    admission_values,
    parse_realtime_multipart,
)
from face_moment.promo.startup_recovery import RealtimeStartupRecoveryRepository
from face_moment.serving_control.display_client_auth import (
    DisplayClientRateLimiter,
    DisplayClientRateLimitError,
    InvalidDisplayClientCredentials,
    authenticate_display_client,
)
from face_moment.serving_control.realtime_context import (
    RealtimeContextRepository,
    RealtimeReadinessClosedError,
    UnknownRealtimeContextSpaError,
)


@asynccontextmanager
async def _realtime_lifecycle(
    settings: Settings, state: dict[str, Any]
) -> AsyncIterator[None]:
    binding = bind_model_consumer(settings)
    state["session_factory"] = binding.session_factory
    state["admitted_pipeline_revision_id"] = binding.adapter.pipeline_revision_id
    state["realtime_deadline_ms"] = getattr(
        settings, "realtime_deadline_ms", DEFAULT_REALTIME_DEADLINE_MS
    )
    state["display_client_rate_limiter"] = DisplayClientRateLimiter(
        limit=60, window_seconds=60
    )
    state["health"] = {"production_model_loaded": True}
    try:
        with binding.session_factory() as database_session:
            recovered_count = RealtimeStartupRecoveryRepository(
                database_session
            ).recover()
            database_session.commit()
        state["health"].update(
            {
                "recovery_completed": True,
                "last_recovered_count": recovered_count,
            }
        )
        yield
    finally:
        state.pop("session_factory", None)
        state.pop("admitted_pipeline_revision_id", None)
        state.pop("realtime_deadline_ms", None)
        state.pop("display_client_rate_limiter", None)
        binding.close()


def create_app() -> FastAPI:
    app = create_role_app("RealtimeFaceService", lifecycle=_realtime_lifecycle)

    @app.post("/api/realtime/attempts")
    async def admit_realtime_attempt(request: Request) -> Response:
        state = request.app.state.role_state
        if not state.get("ready") or "session_factory" not in state:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        body = await _read_limited_body(request)
        try:
            payload = parse_realtime_multipart(
                body, request.headers.get("content-type")
            )
        except RealtimeBodyTooLargeError as error:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            ) from error
        except RealtimePayloadError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
            ) from error

        session_factory = state["session_factory"]
        limiter = state["display_client_rate_limiter"]
        with session_factory() as database_session:
            try:
                principal = authenticate_display_client(
                    database_session,
                    authorization=request.headers.get("authorization"),
                    ip_address=_client_ip(request),
                    rate_limiter=limiter,
                )
            except DisplayClientRateLimitError as error:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS) from error
            except InvalidDisplayClientCredentials as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
            try:
                context = RealtimeContextRepository(database_session).resolve_realtime_context(
                    spa_id=principal.spa_id,
                    admitted_pipeline_revision_id=state["admitted_pipeline_revision_id"],
                    release_id=os.environ.get("FACE_MOMENT_RELEASE_ID", "face-moment-runtime"),
                )
            except (RealtimeReadinessClosedError, UnknownRealtimeContextSpaError) as error:
                database_session.rollback()
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE) from error

            repository = PromoAttemptRepository(database_session)
            try:
                existing = repository.get_by_admission_key(
                    spa_id=principal.spa_id, client_attempt_id=payload.attempt_id
                )
            except PromoAttemptNotFoundError:
                existing = None
            if existing is not None:
                database_session.commit()
                return _response_for_attempt(existing)

            attempt = repository.create_or_get(
                **admission_values(
                    payload,
                    context,
                    deadline_ms=state.get(
                        "realtime_deadline_ms", DEFAULT_REALTIME_DEADLINE_MS
                    ),
                ),
            )
            if attempt.processing_status == "accepted":
                if payload.proposal_count == 0:
                    repository.mark_no_proposals(attempt)
                else:
                    repository.mark_internal_failure(attempt)
            database_session.commit()
            return _response_for_attempt(attempt)

    return app


async def _read_limited_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > 20_971_520:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        except ValueError:
            pass
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > 20_971_520:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        chunks.append(chunk)
    return b"".join(chunks)


def _response_for_attempt(attempt: Any) -> Response:
    if attempt.processing_status == "internal_failure":
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "realtime processing is not available"},
        )
    outcome = attempt.domain_outcome
    if outcome is None:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "schema_version": 1,
                "attempt_id": str(attempt.id),
                "outcome": "in_progress",
            },
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "schema_version": 1,
            "attempt_id": str(attempt.id),
            "outcome": outcome,
        },
    )


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        candidate = forwarded_for.split(",", maxsplit=1)[0].strip()
        try:
            return str(ip_address(candidate))
        except ValueError:
            pass
    return "unknown" if request.client is None else request.client.host


app = create_app()


def main() -> None:
    run(app, 8002)


if __name__ == "__main__":
    main()

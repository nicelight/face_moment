"""Thin HTTP adapter for Promo-owned authenticated teaser delivery."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from ipaddress import ip_address
import uuid

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import (
    DEFAULT_PROMO_QR_TICKET_SECRET,
    DEFAULT_REALTIME_RATE_LIMIT,
    DEFAULT_REALTIME_RATE_WINDOW_SECONDS,
    Settings,
)
from face_moment.promo.display_config import (
    InvalidDisplayConfigurationError,
    read_display_configuration,
)
from face_moment.promo.display_media import (
    PromoMediaNotFoundError,
    resolve_teaser_media,
)
from face_moment.promo.display_outcome import (
    DisplayOutcomeRepository,
    DisplayReport,
    DisplayReportConflictError,
    InvalidDisplayReportError,
    PromoDisplaySessionNotFoundError,
    parse_display_report,
)
from face_moment.serving_control.display_client_auth import (
    DisplayClientRateLimiter,
    DisplayClientRateLimitError,
    InvalidDisplayClientCredentials,
    authenticate_display_client,
)


_NO_STORE_HEADERS = {"Cache-Control": "no-store"}


def register_promo_display_routes(app: FastAPI) -> None:
    """Register transport adapters for Promo-owned display boundaries."""

    @app.get("/api/promo/display/config")
    def promo_display_config(request: Request) -> Response:
        try:
            settings = Settings.from_env()
        except (RuntimeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers=_NO_STORE_HEADERS,
            ) from error

        with _database_session(settings) as database_session:
            try:
                authenticate_display_client(
                    database_session,
                    authorization=request.headers.get("authorization"),
                    ip_address=_client_ip(request),
                    rate_limiter=_display_rate_limiter(app, settings),
                )
            except DisplayClientRateLimitError as error:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except InvalidDisplayClientCredentials as error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers=_NO_STORE_HEADERS,
                ) from error

            try:
                configuration = read_display_configuration(settings)
            except InvalidDisplayConfigurationError as error:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    headers=_NO_STORE_HEADERS,
                ) from error

        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content=configuration.as_response(),
        )
        response.headers.update(_NO_STORE_HEADERS)
        return response

    @app.get("/api/promo/media/{media_ref}")
    def promo_media(request: Request, media_ref: str) -> Response:
        settings = Settings.from_env()
        with _database_session(settings) as database_session:
            try:
                principal = authenticate_display_client(
                    database_session,
                    authorization=request.headers.get("authorization"),
                    ip_address=_client_ip(request),
                    rate_limiter=_display_rate_limiter(app, settings),
                )
            except DisplayClientRateLimitError as error:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except InvalidDisplayClientCredentials as error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers=_NO_STORE_HEADERS,
                ) from error

            try:
                body = resolve_teaser_media(
                    database_session,
                    spa_id=principal.spa_id,
                    media_ref=media_ref,
                    qr_ticket_secret=getattr(
                        settings, "promo_qr_ticket_secret", DEFAULT_PROMO_QR_TICKET_SECRET
                    ),
                    object_store=getattr(
                        app.state,
                        "promo_display_object_store",
                        PrivateObjectStore(settings),
                    ),
                )
            except PromoMediaNotFoundError as error:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except Exception as error:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    headers=_NO_STORE_HEADERS,
                ) from error

        response = Response(content=body, media_type="image/jpeg")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.put("/api/promo/sessions/{session_id}/display")
    async def promo_display_acknowledgement(
        request: Request, session_id: uuid.UUID
    ) -> Response:
        settings = Settings.from_env()
        with _database_session(settings) as database_session:
            try:
                principal = authenticate_display_client(
                    database_session,
                    authorization=request.headers.get("authorization"),
                    ip_address=_client_ip(request),
                    rate_limiter=_display_rate_limiter(app, settings),
                )
            except DisplayClientRateLimitError as error:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except InvalidDisplayClientCredentials as error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers=_NO_STORE_HEADERS,
                ) from error

            report = await _display_report(request)
            try:
                outcome = DisplayOutcomeRepository(database_session).record(
                    spa_id=principal.spa_id,
                    session_id=session_id,
                    report=report,
                )
                database_session.commit()
            except PromoDisplaySessionNotFoundError as error:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except DisplayReportConflictError as error:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except Exception as error:
                database_session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    headers=_NO_STORE_HEADERS,
                ) from error

        content: dict[str, object] = {
            "schema_version": 1,
            "session_id": str(outcome.session_id),
            "status": outcome.status,
            "display_expires_at": _utc_iso(outcome.display_expires_at),
        }
        if outcome.status == "confirmed":
            content["qr_fully_visible_elapsed_ms"] = outcome.qr_fully_visible_elapsed_ms
        response = JSONResponse(status_code=status.HTTP_200_OK, content=content)
        response.headers.update(_NO_STORE_HEADERS)
        return response


@contextmanager
def _database_session(settings: Settings) -> Iterator[Session]:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as database_session:
            yield database_session
    finally:
        engine.dispose()


def _display_rate_limiter(app: FastAPI, settings: Settings) -> DisplayClientRateLimiter:
    limiter = getattr(app.state, "promo_display_rate_limiter", None)
    if limiter is None:
        limiter = DisplayClientRateLimiter(
            limit=getattr(settings, "realtime_rate_limit", DEFAULT_REALTIME_RATE_LIMIT),
            window_seconds=getattr(
                settings,
                "realtime_rate_window_seconds",
                DEFAULT_REALTIME_RATE_WINDOW_SECONDS,
            ),
        )
        app.state.promo_display_rate_limiter = limiter
    return limiter


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        candidate = forwarded_for.split(",", maxsplit=1)[0].strip()
        try:
            return str(ip_address(candidate))
        except ValueError:
            pass
    return "unknown" if request.client is None else request.client.host


async def _display_report(request: Request) -> DisplayReport:
    content_type = request.headers.get("content-type", "")
    if content_type.split(";", maxsplit=1)[0].strip().casefold() != "application/json":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            headers=_NO_STORE_HEADERS,
        )
    try:
        payload = await request.json()
        return parse_display_report(payload)
    except InvalidDisplayReportError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            headers=_NO_STORE_HEADERS,
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            headers=_NO_STORE_HEADERS,
        ) from error


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = ["register_promo_display_routes"]

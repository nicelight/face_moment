"""Thin HTTP adapter for Promo-owned authenticated teaser delivery."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from ipaddress import ip_address

from fastapi import FastAPI, HTTPException, Request, Response, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import (
    DEFAULT_PROMO_QR_TICKET_SECRET,
    DEFAULT_REALTIME_RATE_LIMIT,
    DEFAULT_REALTIME_RATE_WINDOW_SECONDS,
    Settings,
)
from face_moment.promo.display_media import (
    PromoMediaNotFoundError,
    resolve_teaser_media,
)
from face_moment.serving_control.display_client_auth import (
    DisplayClientRateLimiter,
    DisplayClientRateLimitError,
    InvalidDisplayClientCredentials,
    authenticate_display_client,
)


def register_promo_display_routes(app: FastAPI) -> None:
    """Register only transport concerns; promo owns media resolution."""

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
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS) from error
            except InvalidDisplayClientCredentials as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error

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
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
            except Exception as error:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from error

        response = Response(content=body, media_type="image/jpeg")
        response.headers["Cache-Control"] = "no-store"
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


__all__ = ["register_promo_display_routes"]

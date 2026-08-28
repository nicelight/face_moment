"""Thin HTTP adapter for Promo-owned authenticated teaser delivery."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import uuid

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import (
    DEFAULT_PHONE_PUBLIC_RATE_LIMIT,
    DEFAULT_PHONE_PUBLIC_RATE_WINDOW_SECONDS,
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
from face_moment.promo.qr_continuation import (
    PHONE_COOKIE_NAME,
    PhoneContinuationConfigurationError,
    PhoneContinuationService,
    PhoneMediaNotFoundError,
    PhonePublicRateLimiter,
    validate_phone_purchase_url,
)
from face_moment.promo.session import PromoSessionNotFoundError
from face_moment.serving_control.display_client_auth import (
    DisplayClientRateLimiter,
    DisplayClientRateLimitError,
    InvalidDisplayClientCredentials,
    authenticate_display_client,
)


_NO_STORE_HEADERS = {"Cache-Control": "no-store"}
_PHONE_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}
_PHONE_TICKET_LENGTH = 43


class _PhoneRateLimitExceeded(Exception):
    pass


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

    _register_promo_media_and_outcome_routes(app)


def register_phone_continuation_routes(app: FastAPI, *, client_root: Path) -> None:
    """Register the exact public Promo phone-continuation adapter."""

    @app.get("/q")
    def phone_ticket_exchange(request: Request) -> Response:
        try:
            settings, purchase_url, timestamp = _phone_request_context(app, request)
        except PhoneContinuationConfigurationError:
            return _phone_empty(status.HTTP_503_SERVICE_UNAVAILABLE)
        except _PhoneRateLimitExceeded:
            return _phone_empty(status.HTTP_429_TOO_MANY_REQUESTS)

        ticket = _query_ticket(request)
        if ticket is None:
            return _phone_redirect(purchase_url)

        with _database_session(settings) as database_session:
            service = _phone_service(
                app,
                database_session,
                settings=settings,
                purchase_url=purchase_url,
            )
            try:
                service.exchange_ticket(ticket, now=timestamp)
                database_session.commit()
            except PromoSessionNotFoundError:
                return _phone_redirect(purchase_url)
            except Exception:
                database_session.rollback()
                return _phone_empty(status.HTTP_500_INTERNAL_SERVER_ERROR)

        response = _phone_redirect("/phone")
        response.set_cookie(
            PHONE_COOKIE_NAME,
            ticket,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    @app.get("/phone")
    def phone_shell(request: Request) -> Response:
        try:
            settings, purchase_url, timestamp = _phone_request_context(app, request)
        except PhoneContinuationConfigurationError:
            return _phone_empty(status.HTTP_503_SERVICE_UNAVAILABLE)
        except _PhoneRateLimitExceeded:
            return _phone_empty(status.HTTP_429_TOO_MANY_REQUESTS)

        ticket = _cookie_ticket(request)
        if ticket is None:
            return _phone_redirect(purchase_url, delete_cookie=True)
        with _database_session(settings) as database_session:
            try:
                _phone_service(
                    app,
                    database_session,
                    settings=settings,
                    purchase_url=purchase_url,
                ).validate_access(ticket, now=timestamp)
            except PromoSessionNotFoundError:
                return _phone_redirect(purchase_url, delete_cookie=True)
            except Exception:
                return _phone_empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return FileResponse(
            client_root / "phone.html",
            media_type="text/html",
            headers=_PHONE_HEADERS,
        )

    @app.get("/api/phone/session")
    def phone_session(request: Request) -> Response:
        context = _protected_phone_context(app, request)
        if isinstance(context, Response):
            return context
        settings, purchase_url, timestamp, ticket = context
        with _database_session(settings) as database_session:
            try:
                view = _phone_service(
                    app,
                    database_session,
                    settings=settings,
                    purchase_url=purchase_url,
                ).read_session(ticket, now=timestamp)
            except PromoSessionNotFoundError:
                return _phone_empty(status.HTTP_401_UNAUTHORIZED, delete_cookie=True)
            except Exception:
                return _phone_empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=view.as_response(),
            headers=_PHONE_HEADERS,
        )

    @app.post("/api/phone/activity")
    async def phone_activity(request: Request) -> Response:
        context = _protected_phone_context(app, request)
        if isinstance(context, Response):
            return context
        settings, purchase_url, timestamp, ticket = context
        origin = request.headers.get("origin")
        if origin is not None and origin != f"{request.url.scheme}://{request.url.netloc}":
            return _phone_empty(status.HTTP_403_FORBIDDEN)
        if not await _valid_activity_request(request):
            return _phone_empty(status.HTTP_422_UNPROCESSABLE_ENTITY)

        with _database_session(settings) as database_session:
            try:
                view = _phone_service(
                    app,
                    database_session,
                    settings=settings,
                    purchase_url=purchase_url,
                ).record_activity(ticket, now=timestamp)
                database_session.commit()
            except PromoSessionNotFoundError:
                return _phone_empty(status.HTTP_401_UNAUTHORIZED, delete_cookie=True)
            except Exception:
                database_session.rollback()
                return _phone_empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=view.as_response(),
            headers=_PHONE_HEADERS,
        )

    @app.get("/api/phone/media/{media_ref}")
    def phone_media(request: Request, media_ref: str) -> Response:
        context = _protected_phone_context(app, request)
        if isinstance(context, Response):
            return context
        settings, purchase_url, timestamp, ticket = context
        with _database_session(settings) as database_session:
            try:
                body = _phone_service(
                    app,
                    database_session,
                    settings=settings,
                    purchase_url=purchase_url,
                ).read_media(ticket, media_ref, now=timestamp)
            except PromoSessionNotFoundError:
                return _phone_empty(status.HTTP_401_UNAUTHORIZED, delete_cookie=True)
            except PhoneMediaNotFoundError:
                return _phone_empty(status.HTTP_404_NOT_FOUND)
            except Exception:
                return _phone_empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(
            content=body,
            media_type="image/jpeg",
            headers=_PHONE_HEADERS,
        )


def _register_promo_media_and_outcome_routes(app: FastAPI) -> None:
    """Keep the existing authenticated display routes grouped together."""

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
    return "unknown" if request.client is None else request.client.host


def _phone_request_context(
    app: FastAPI, request: Request
) -> tuple[Settings, str, datetime]:
    try:
        settings = Settings.from_env()
        purchase_url = validate_phone_purchase_url(settings.phone_purchase_url)
    except (RuntimeError, ValueError) as error:
        raise PhoneContinuationConfigurationError(
            "phone continuation configuration is unavailable"
        ) from error
    timestamp = _phone_now(app)
    if not _phone_rate_limiter(app, settings).allow(
        ip_address=_client_ip(request),
        now=timestamp,
    ):
        raise _PhoneRateLimitExceeded
    return settings, purchase_url, timestamp


def _protected_phone_context(
    app: FastAPI, request: Request
) -> tuple[Settings, str, datetime, str] | Response:
    try:
        settings, purchase_url, timestamp = _phone_request_context(app, request)
    except PhoneContinuationConfigurationError:
        return _phone_empty(status.HTTP_503_SERVICE_UNAVAILABLE)
    except _PhoneRateLimitExceeded:
        return _phone_empty(status.HTTP_429_TOO_MANY_REQUESTS)
    ticket = _cookie_ticket(request)
    if ticket is None:
        return _phone_empty(status.HTTP_401_UNAUTHORIZED, delete_cookie=True)
    return settings, purchase_url, timestamp, ticket


def _phone_rate_limiter(app: FastAPI, settings: Settings) -> PhonePublicRateLimiter:
    limiter = getattr(app.state, "promo_phone_rate_limiter", None)
    if limiter is None:
        limiter = PhonePublicRateLimiter(
            limit=getattr(
                settings,
                "phone_public_rate_limit",
                DEFAULT_PHONE_PUBLIC_RATE_LIMIT,
            ),
            window_seconds=getattr(
                settings,
                "phone_public_rate_window_seconds",
                DEFAULT_PHONE_PUBLIC_RATE_WINDOW_SECONDS,
            ),
        )
        app.state.promo_phone_rate_limiter = limiter
    return limiter


def _phone_service(
    app: FastAPI,
    database_session: Session,
    *,
    settings: Settings,
    purchase_url: str,
) -> PhoneContinuationService:
    return PhoneContinuationService(
        database_session,
        qr_ticket_secret=getattr(
            settings,
            "promo_qr_ticket_secret",
            DEFAULT_PROMO_QR_TICKET_SECRET,
        ),
        purchase_url=purchase_url,
        object_store=getattr(
            app.state,
            "promo_phone_object_store",
            PrivateObjectStore(settings),
        ),
    )


def _phone_now(app: FastAPI) -> datetime:
    clock = getattr(app.state, "promo_phone_clock", None)
    value = clock() if callable(clock) else datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("promo phone clock must return an aware datetime")
    return value.astimezone(timezone.utc)


def _query_ticket(request: Request) -> str | None:
    items = list(request.query_params.multi_items())
    if len(items) != 1 or items[0][0] != "ticket":
        return None
    return items[0][1] if _valid_ticket(items[0][1]) else None


def _cookie_ticket(request: Request) -> str | None:
    value = request.cookies.get(PHONE_COOKIE_NAME)
    return value if value is not None and _valid_ticket(value) else None


def _valid_ticket(value: str) -> bool:
    return (
        len(value) == _PHONE_TICKET_LENGTH
        and value.isascii()
        and all(character.isalnum() or character in "-_" for character in value)
    )


def _phone_empty(status_code: int, *, delete_cookie: bool = False) -> Response:
    response = Response(status_code=status_code, headers=_PHONE_HEADERS)
    if delete_cookie:
        response.delete_cookie(
            PHONE_COOKIE_NAME,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
    return response


def _phone_redirect(target: str, *, delete_cookie: bool = False) -> RedirectResponse:
    response = RedirectResponse(
        target,
        status_code=status.HTTP_303_SEE_OTHER,
        headers=_PHONE_HEADERS,
    )
    if delete_cookie:
        response.delete_cookie(
            PHONE_COOKIE_NAME,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
    return response


async def _valid_activity_request(request: Request) -> bool:
    content_type = request.headers.get("content-type", "")
    if content_type.split(";", maxsplit=1)[0].strip().casefold() != "application/json":
        return False
    try:
        payload = await request.json()
    except Exception:
        return False
    return (
        isinstance(payload, dict)
        and set(payload) == {"schema_version"}
        and isinstance(payload["schema_version"], int)
        and not isinstance(payload["schema_version"], bool)
        and payload["schema_version"] == 1
    )


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


__all__ = ["register_phone_continuation_routes", "register_promo_display_routes"]

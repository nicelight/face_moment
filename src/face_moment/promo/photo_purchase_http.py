"""Public purchase transport; quote rules and orchestration belong to promo."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
from typing import Any, cast
import uuid

from fastapi import FastAPI, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.promo.browser_search_profile import COOKIE_NAME, set_browser_profile_cookie
from face_moment.promo.photo_quote import quote_selected_photos
from face_moment.promo.public_photo_search import PublicProfileRequiredError, PublicResultNotFoundError
from face_moment.promo.public_search_http import PUBLIC_HEADERS, _failure
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from face_moment.serving_control.photo_tariff import PhotoTariffUnavailableError


def register_public_quote_route(app: FastAPI, *, session_factory: Callable[[], Session]) -> None:
    @app.post('/api/public/quote')
    async def quote(request: Request) -> Response:
        if request.url.scheme != 'https' or request.headers.get('origin') != str(request.base_url).rstrip('/'):
            raise _failure(403)
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise _failure(401)
        state = request.app.state.role_state
        if 'public_preview_store' not in state or 'public_quote_rate_limiter' not in state:
            raise _failure(503)
        limiter = cast(DisplayClientRateLimiter, state['public_quote_rate_limiter'])
        if not limiter.allow(token_digest=hashlib.sha256(token.encode()).digest(),
            ip_address='unknown' if request.client is None else request.client.host, now=datetime.now(timezone.utc)):
            raise _failure(429)
        try:
            payload = await request.json()
            if not isinstance(payload, dict) or set(payload) != {'result_id', 'photo_ids'}:
                raise ValueError('strict quote fields required')
            if not isinstance(payload['result_id'], str) or not isinstance(payload['photo_ids'], list):
                raise ValueError('result UUID and photo ID list required')
            if any(not isinstance(identity, str) for identity in payload['photo_ids']):
                raise ValueError('photo UUID strings required')
            result_id = uuid.UUID(payload['result_id'])
            photo_ids = tuple(uuid.UUID(identity) for identity in payload['photo_ids'])
            if len(set(photo_ids)) != len(photo_ids):
                raise ValueError('distinct photo IDs required')
        except (ValueError, TypeError) as error:
            raise _failure(422) from error
        def calculate() -> dict[str, Any]:
            with session_factory() as session:
                content = quote_selected_photos(session, cookie_token=token, result_id=result_id,
                    photo_ids=photo_ids, object_store=cast(PrivateObjectStore, state['public_preview_store']))
                session.commit()
                return content
        try:
            content = await run_in_threadpool(calculate)
        except PublicProfileRequiredError as error:
            raise _failure(401) from error
        except PublicResultNotFoundError as error:
            raise _failure(404) from error
        except PhotoTariffUnavailableError as error:
            raise _failure(503) from error
        except Exception as error:
            raise _failure(500) from error
        response = JSONResponse(content, headers=PUBLIC_HEADERS)
        set_browser_profile_cookie(response, token)
        return response

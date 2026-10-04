"""Public order transport consumes promo's frozen core and entitled signer."""
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
from face_moment.promo.browser_search_profile import BrowserSearchProfileRepository, COOKIE_NAME, set_browser_profile_cookie
from face_moment.promo.photo_archive_delivery import archive_download_url
from face_moment.promo.photo_orders import PhotoOrderConflictError, PhotoOrderRepository
from face_moment.promo.public_photo_search import PublicProfileRequiredError, PublicResultNotFoundError
from face_moment.promo.public_search_http import PUBLIC_HEADERS, _failure
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from face_moment.serving_control.photo_tariff import PhotoTariffUnavailableError


def _admit(request: Request, *, mutation: bool) -> str:
    if request.url.scheme != 'https' or (mutation and request.headers.get('origin') != str(request.base_url).rstrip('/')):
        raise _failure(403)
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise _failure(401)
    state = request.app.state.role_state
    if 'public_order_rate_limiter' not in state:
        raise _failure(503)
    limiter = cast(DisplayClientRateLimiter, state['public_order_rate_limiter'])
    if not limiter.allow(token_digest=hashlib.sha256(token.encode()).digest(),
        ip_address='unknown' if request.client is None else request.client.host, now=datetime.now(timezone.utc)):
        raise _failure(429)
    return token


def register_public_order_routes(app: FastAPI, *, session_factory: Callable[[], Session]) -> None:
    @app.post('/api/public/orders')
    async def create_order(request: Request) -> Response:
        token = _admit(request, mutation=True)
        state = request.app.state.role_state
        if 'public_preview_store' not in state:
            raise _failure(503)
        try:
            payload = await request.json()
            required = {'result_id', 'photo_ids', 'client_request_id'}
            if not isinstance(payload, dict) or not required <= payload.keys() or payload.keys() - required - {'email', 'payment_method'}:
                raise ValueError('strict order fields required')
            if not isinstance(payload['result_id'], str) or not isinstance(payload['photo_ids'], list):
                raise ValueError('result UUID and photo ID list required')
            if any(not isinstance(identity, str) for identity in payload['photo_ids']):
                raise ValueError('photo UUID strings required')
            if not isinstance(payload['client_request_id'], str) or not payload['client_request_id'].strip():
                raise ValueError('client_request_id required')
            email, method = payload.get('email'), payload.get('payment_method')
            if email is not None and not isinstance(email, str):
                raise ValueError('email must be a string')
            if method is not None and (not isinstance(method, str) or method not in ('bank_card', 'sbp')):
                raise ValueError('payment_method must be bank_card or sbp')
            result_id = uuid.UUID(payload['result_id'])
            photo_ids = tuple(uuid.UUID(identity) for identity in payload['photo_ids'])
            if len(set(photo_ids)) != len(photo_ids):
                raise ValueError('distinct photo IDs required')
        except (ValueError, TypeError) as error:
            raise _failure(422) from error

        def create() -> dict[str, Any]:
            with session_factory() as session:
                order = PhotoOrderRepository(session).create(cookie_token=token, result_id=result_id,
                    photo_ids=photo_ids, client_request_id=payload['client_request_id'],
                    object_store=cast(PrivateObjectStore, state['public_preview_store']),
                    email=email, payment_method=method)
                content = {'schema_version':1, 'id':str(order.id), 'archive_status':order.archive_status,
                           'total_kopecks':int(order.total_kopecks)}
                session.commit()
                return content
        try:
            content = await run_in_threadpool(create)
        except PhotoOrderConflictError as error:
            raise _failure(409) from error
        except PublicProfileRequiredError as error:
            raise _failure(401) from error
        except PublicResultNotFoundError as error:
            raise _failure(404) from error
        except PhotoTariffUnavailableError as error:
            raise _failure(503) from error
        except ValueError as error:
            raise _failure(422) from error
        except Exception as error:
            raise _failure(500) from error
        response = JSONResponse(content, headers=PUBLIC_HEADERS)
        set_browser_profile_cookie(response, token)
        return response

    @app.get('/api/public/orders/{order_id}')
    async def read_order(request: Request, order_id: str) -> Response:
        token = _admit(request, mutation=False)
        try:
            identity = uuid.UUID(order_id)
        except ValueError as error:
            raise _failure(404) from error
        state = request.app.state.role_state

        def read() -> dict[str, Any]:
            with session_factory() as session:
                if BrowserSearchProfileRepository(session).find(token) is None:
                    raise PublicProfileRequiredError
                order = PhotoOrderRepository(session).find(cookie_token=token, order_id=identity)
                if order is None:
                    raise PublicResultNotFoundError
                content: dict[str, Any] = {'schema_version':1, 'id':str(order.id),
                    'archive_status':order.archive_status, 'payment_status':order.payment_status,
                    'total_kopecks':int(order.total_kopecks)}
                if order.archive_status == 'preparing':
                    content['retry_after_seconds'] = 30
                elif order.archive_status == 'failed':
                    content['error'] = 'Не удалось подготовить архив. Обратитесь в поддержку.'
                secret = state.get('photo_archive_signing_secret')
                if secret:
                    link = archive_download_url(order, secret=secret, now=datetime.now(timezone.utc))
                    if link is not None:
                        content['download_url'] = link
                return content
        try:
            content = await run_in_threadpool(read)
        except PublicProfileRequiredError as error:
            raise _failure(401) from error
        except PublicResultNotFoundError as error:
            raise _failure(404) from error
        except Exception as error:
            raise _failure(500) from error
        return JSONResponse(content, headers=PUBLIC_HEADERS)

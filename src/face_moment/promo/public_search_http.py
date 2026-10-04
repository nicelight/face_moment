"""Public transport validation and adapters; business flow stays in promo."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from typing import Any, cast
import uuid

import cv2
from fastapi import FastAPI, HTTPException, Request
from multipart.multipart import parse_options_header
import numpy as np
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

from face_moment.processing.face_engine import FaceEngine
from face_moment.promo.browser_search_profile import COOKIE_NAME, IncompatibleBrowserProfileRevisionError, set_browser_profile_cookie
from face_moment.promo.public_photo_search import PublicSearchResultRepository, PublicResultNotFoundError, PublicProfileRequiredError, execute_public_photo_search, read_public_gallery_preview
from face_moment.promo.realtime_admission import _parse_parts, RealtimePayloadError
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from face_moment.serving_control.public_search_context import read_public_venues
from face_moment.serving_control.realtime_context import RealtimeReadinessClosedError

PUBLIC_HEADERS = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'}
MAX_PUBLIC_BODY_BYTES = 2 * 1024 * 1024 + 65536


def _failure(code: int) -> HTTPException:
    return HTTPException(status_code=code, headers=PUBLIC_HEADERS)


def parse_public_search(body: bytes, content_type: str | None) -> tuple[np.ndarray[Any, Any], tuple[uuid.UUID, ...], bool]:
    kind, options = parse_options_header(content_type or '')
    if kind != b'multipart/form-data' or not options.get(b'boundary'):
        raise ValueError('multipart required')
    parts = _parse_parts(body, options[b'boundary'])
    fields = {p.name: p for p in parts}
    if len(fields) != len(parts) or not {'selfie', 'venue_ids'} <= fields.keys() or fields.keys() - {'selfie', 'venue_ids', 'confirm_reset'}:
        raise ValueError('strict public fields required')
    for name in ('venue_ids', 'confirm_reset'):
        if name in fields and fields[name].filename is not None:
            raise ValueError('field cannot be a file')
    ids = json.loads(fields['venue_ids'].body)
    if not isinstance(ids, list) or not 1 <= len(ids) <= 3 or any(not isinstance(i, str) for i in ids):
        raise ValueError('select 1–3 venues')
    venue_ids = tuple(uuid.UUID(i) for i in ids)
    if len(set(venue_ids)) != len(venue_ids):
        raise ValueError('distinct venues required')
    confirm = False
    if 'confirm_reset' in fields:
        raw = fields['confirm_reset'].body
        if raw not in (b'true', b'false'):
            raise ValueError('strict bool required')
        confirm = raw == b'true'
    jpeg = fields['selfie']
    if jpeg.content_type != 'image/jpeg' or not jpeg.body.startswith(b'\xff\xd8'):
        raise ValueError('JPEG required')
    if len(jpeg.body) > 2 * 1024 * 1024:
        raise _failure(413)
    with Image.open(BytesIO(jpeg.body), formats=['JPEG']) as image:
        width, height = image.size
        if width > 4096 or height > 4096 or width * height > 4096**2:
            raise ValueError('decoded JPEG bounds exceeded')
        image.verify()
    selfie = cv2.imdecode(np.frombuffer(jpeg.body, dtype=np.uint8), cv2.IMREAD_COLOR)
    if selfie is None:
        raise ValueError('invalid JPEG')
    return selfie, venue_ids, confirm


def register_public_result_routes(app: FastAPI, *, session_factory: Callable[[], Session]) -> None:
    @app.get('/api/public/results/{result_id}/previews/{photo_id}')
    async def preview(request: Request, result_id: str, photo_id: str) -> Response:
        if request.url.scheme != 'https':
            raise _failure(403)
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise _failure(401)
        try:
            result, photo = uuid.UUID(result_id), uuid.UUID(photo_id)
        except ValueError as error:
            raise _failure(404) from error
        state = request.app.state.role_state
        if 'public_preview_executor' not in state:
            raise _failure(503)
        slot = state['public_preview_slot']
        if not slot.acquire(blocking=False):
            raise _failure(429)

        def deliver() -> bytes:
            try:
                return read_public_gallery_preview(session_factory=session_factory, cookie_token=token,
                    result_id=result, photo_id=photo, object_store=state['public_preview_store'])
            finally:
                slot.release()
        try:
            executor = cast(ThreadPoolExecutor, state['public_preview_executor'])
            # Shield prevents request cancellation from cancelling admitted work;
            # only the worker releases the slot after IO/render actually ends.
            body = await asyncio.shield(asyncio.get_running_loop().run_in_executor(executor, deliver))
        except PublicProfileRequiredError as error:
            raise _failure(401) from error
        except PublicResultNotFoundError as error:
            raise _failure(404) from error
        except Exception as error:
            raise _failure(500) from error
        response = Response(body, media_type='image/jpeg', headers={**PUBLIC_HEADERS, 'X-Content-Type-Options':'nosniff'})
        set_browser_profile_cookie(response, token)
        return response

    @app.get('/api/public/venues')
    def venues() -> Response:
        with session_factory() as session:
            content = {'schema_version': 1, 'venues': [{'id': str(v.id), 'name': v.name} for v in read_public_venues(session)]}
        return JSONResponse(content, headers=PUBLIC_HEADERS)

    @app.get('/api/public/results/{result_id}')
    def current(request: Request, result_id: str) -> Response:
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise _failure(401)
        try:
            identity = uuid.UUID(result_id)
        except ValueError as error:
            raise _failure(404) from error
        with session_factory() as session:
            try:
                content = PublicSearchResultRepository(session).current(cookie_token=token, result_id=identity)
                session.commit()
            except PublicProfileRequiredError as error:
                raise _failure(401) from error
            except PublicResultNotFoundError as error:
                raise _failure(404) from error
        response = JSONResponse(content, headers=PUBLIC_HEADERS)
        set_browser_profile_cookie(response, token)
        return response


def register_public_search_route(app: FastAPI) -> None:
    @app.post('/api/public/search')
    async def search(request: Request) -> Response:
        if request.url.scheme != 'https' or request.headers.get('origin') != str(request.base_url).rstrip('/'):
            raise _failure(403)
        state = request.app.state.role_state
        if not state.get('ready') or 'model_adapter' not in state:
            raise _failure(503)
        total = 0
        chunks = []
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_PUBLIC_BODY_BYTES:
                raise _failure(413)
            chunks.append(chunk)
        return await run_in_threadpool(_search_response, body=b''.join(chunks),
            content_type=request.headers.get('content-type'), cookie_token=request.cookies.get(COOKIE_NAME),
            client_ip='unknown' if request.client is None else request.client.host, state=dict(state))


def _search_response(*, body: bytes, content_type: str | None, cookie_token: str | None, client_ip: str, state: dict[str, Any]) -> Response:
    limiter = cast(DisplayClientRateLimiter, state['public_search_rate_limiter'])
    digest = None if cookie_token is None else hashlib.sha256(cookie_token.encode()).digest()
    if not limiter.allow(token_digest=digest, ip_address=client_ip, now=datetime.now(timezone.utc)):
        raise _failure(429)
    try:
        selfie, venue_ids, confirm_reset = parse_public_search(body, content_type)
        # Unknown/inactive scope is transport validation, even if Promo slot busy.
        with state['session_factory']() as session:
            active = {v.id for v in read_public_venues(session)}
            if not set(venue_ids) <= active:
                raise ValueError('unknown or inactive venue')
        content, token = execute_public_photo_search(session_factory=state['session_factory'],
            engine=cast(FaceEngine, state['model_adapter']), pipeline_revision_id=state['admitted_pipeline_revision_id'],
            selfie=selfie, venue_ids=venue_ids, cookie_token=cookie_token, confirm_reset=confirm_reset,
            deadline_ms=state['realtime_deadline_ms'])
    except (ValueError, RealtimePayloadError, UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise _failure(422) from error
    except (RealtimeReadinessClosedError, IncompatibleBrowserProfileRevisionError) as error:
        raise _failure(503) from error
    except HTTPException:
        raise
    except Exception as error:
        raise _failure(500) from error
    response = JSONResponse(content, headers=PUBLIC_HEADERS)
    if token is not None:
        set_browser_profile_cookie(response, token)
    return response

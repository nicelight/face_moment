"""Archive HTTP adapter; promo owns signature, entitlement and lifetime."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import cast
import uuid

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, Request
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, Response, StreamingResponse

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.promo.photo_archive_delivery import (
    ArchiveExpiredError, ArchiveUnavailableError, authorized_archive_key,
)
from face_moment.promo.public_search_http import PUBLIC_HEADERS


_SAFE_ERROR = 'Архив недоступен. Обратитесь в поддержку.'


def register_photo_archive_route(app: FastAPI, *, session_factory: Callable[[], Session]) -> None:
    @app.get('/api/public/archives/{order_id}')
    def download(order_id: str, request: Request) -> Response:
        def failure(code: int) -> JSONResponse:
            return JSONResponse({'schema_version':1, 'detail':_SAFE_ERROR},
                                status_code=code, headers=PUBLIC_HEADERS)
        if request.url.scheme != 'https':
            return failure(403)
        token = request.query_params.get('token')
        try:
            identity = uuid.UUID(order_id)
        except ValueError:
            return failure(404)
        if token is None:
            return failure(404)
        state = request.app.state.role_state
        secret = state.get('photo_archive_signing_secret')
        store = state.get('public_preview_store')
        if not secret or store is None:
            return failure(503)
        clock = cast(Callable[[], datetime], state.get('photo_archive_clock', lambda: datetime.now(timezone.utc)))
        try:
            with session_factory() as session:
                key = authorized_archive_key(session, order_id=identity, token=token,
                                             secret=secret, now=clock())
            chunks = cast(PrivateObjectStore, store).stream(key=key)
        except ArchiveExpiredError:
            return failure(410)
        except (ArchiveUnavailableError, ClientError, BotoCoreError):
            return failure(404)
        return StreamingResponse(chunks, media_type='application/zip', headers={
            **PUBLIC_HEADERS, 'Content-Disposition':f'attachment; filename="photos-{identity}.zip"',
            'X-Content-Type-Options':'nosniff',
        })

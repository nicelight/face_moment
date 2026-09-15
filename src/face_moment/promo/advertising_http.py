"""Staff advertising administration and display-token-scoped media delivery."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from html import escape
import math
from pathlib import PurePath
from typing import Any
import uuid

from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore, s3_client
from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import (InvalidSessionError, CsrfValidationError,
    get_current_principal, authenticate_unsafe_staff_request)
from face_moment.platform.staff_presentation import staff_document
from face_moment.promo.advertising import AdvertisingMedia, locked_playlist, playlist_projection
from face_moment.serving_control.display_client_auth import (authenticate_display_client,
    DisplayClientRateLimiter, DisplayClientRateLimitError, InvalidDisplayClientCredentials)
from face_moment.serving_control.ingest_target import Spa

HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".webm": "video/webm"}


class PlaylistSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    item_ids: list[uuid.UUID]
    image_seconds: float = Field(gt=0, le=86400, allow_inf_nan=False)
    crossfade_seconds: float = Field(ge=0, le=86400, allow_inf_nan=False)
    random_start: bool


def register_advertising_routes(app: FastAPI, *, session_factory: Callable[[], Session]) -> None:
    limiter = DisplayClientRateLimiter(limit=600, window_seconds=60)

    def staff(session: Session, request: Request, *, unsafe: bool = False) -> None:
        try:
            principal = authenticate_unsafe_staff_request(session,
                session_token=request.cookies.get("fm_staff_session"),
                csrf_cookie_token=request.cookies.get("fm_staff_csrf"),
                csrf_header_token=request.headers.get("x-csrf-token")) if unsafe else get_current_principal(
                    session, session_token=request.cookies.get("fm_staff_session"))
        except InvalidSessionError as error:
            raise HTTPException(401) from error
        except CsrfValidationError as error:
            raise HTTPException(403) from error
        if principal.role not in {StaffRole.OPERATOR, StaffRole.DEVELOPER}:
            raise HTTPException(403)

    def display_spa(session: Session, request: Request) -> uuid.UUID:
        try:
            return authenticate_display_client(session, authorization=request.headers.get("authorization"),
                ip_address=request.client.host if request.client else "unknown", rate_limiter=limiter).spa_id
        except InvalidDisplayClientCredentials as error:
            raise HTTPException(401) from error
        except DisplayClientRateLimitError as error:
            raise HTTPException(429) from error

    @app.get("/staff/advertising")
    def page(request: Request, spa_id: uuid.UUID | None = None) -> HTMLResponse:
        with session_factory() as session:
            staff(session, request)
            if spa_id is None:
                venues = ''.join(f'<a class="ad-venue" href="/staff/advertising?spa_id={spa.id}">{escape(spa.name)} <span>→</span></a>'
                    for spa in session.scalars(select(Spa).order_by(Spa.name)))
                body = f'<main><section class="ad-admin"><h2>Выберите площадку</h2><div class="ad-venues">{venues or "Площадок пока нет."}</div></section></main>'
            else:
                venue = session.get(Spa, spa_id)
                if venue is None:
                    raise HTTPException(404)
                body = f'''<main><section class="ad-admin" data-ad-spa="{spa_id}">
<a href="/staff/display-clients">← Экраны</a><h2>{escape(venue.name)}</h2>
<p>Один плейлист для всех экранов площадки. Видео проигрываются целиком.</p>
<form id="ad-upload"><label>Добавить материалы<input name="files" type="file" multiple accept=".jpg,.jpeg,.png,.webp,.webm" required></label>
<button type="submit">Загрузить</button></form><p id="ad-status" role="status"></p>
<form id="ad-settings"><div class="ad-table-wrap"><table><thead><tr><th>Превью</th><th>Файл</th><th>Длительность</th><th>Позиция</th><th></th></tr></thead><tbody id="ad-items"></tbody></table></div>
<p id="ad-total"></p><div class="ad-settings">
<label>Время каждой фотографии, секунд<input name="image_seconds" type="number" min="0.1" max="86400" step="0.1" value="5" required></label>
<label>Crossfade, секунд<input name="crossfade_seconds" type="number" min="0" max="86400" step="0.1" value="1" required></label>
<label class="ad-checkbox"><input name="random_start" type="checkbox">Начинать со случайного номера в списке</label></div>
<button type="submit">Сохранить порядок и настройки</button></form><p id="ad-error" role="alert"></p>
</section></main>'''
            html = '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Реклама</title><link rel="stylesheet" href="/client/advertising.css"><script type="module" src="/client/advertising-admin.js"></script></head><body>' + body + '</body></html>'
            return HTMLResponse(staff_document(html, "advertising"), headers=HEADERS)

    @app.get("/api/advertising/{spa_id}/playlist")
    def read(request: Request, spa_id: uuid.UUID) -> JSONResponse:
        with session_factory() as session:
            staff(session, request)
            if session.get(Spa, spa_id) is None:
                raise HTTPException(404)
            return JSONResponse(playlist_projection(session, spa_id), headers=HEADERS)

    @app.put("/api/advertising/{spa_id}/playlist")
    def save(request: Request, spa_id: uuid.UUID, payload: PlaylistSave) -> JSONResponse:
        with session_factory() as session:
            staff(session, request, unsafe=True)
            if session.get(Spa, spa_id) is None:
                raise HTTPException(404)
            playlist = locked_playlist(session, spa_id)
            if playlist.revision != payload.revision:
                raise HTTPException(409, "Список изменён в другой вкладке. Обновите страницу.")
            ids = [str(item) for item in payload.item_ids]
            if len(ids) != len(set(ids)) or set(ids) != set(playlist.item_ids):
                raise HTTPException(409, "Состав плейлиста изменился. Обновите страницу.")
            playlist.item_ids = ids
            playlist.image_seconds = payload.image_seconds
            playlist.crossfade_seconds = payload.crossfade_seconds
            playlist.random_start = payload.random_start
            playlist.revision += 1
            session.commit()
            return JSONResponse(playlist_projection(session, spa_id), headers=HEADERS)

    @app.post("/api/advertising/{spa_id}/media")
    def upload(request: Request, spa_id: uuid.UUID, file: UploadFile = File(),
               duration_seconds: float | None = Form(default=None)) -> JSONResponse:
        with session_factory() as session:
            staff(session, request, unsafe=True)
            if session.get(Spa, spa_id) is None:
                raise HTTPException(404)
            filename = (file.filename or "").replace("\\", "/").split("/")[-1][:255]
            content_type = TYPES.get(PurePath(filename).suffix.lower())
            if content_type is None:
                raise HTTPException(422, "Нужны JPEG, PNG, WebP или WebM.")
            if duration_seconds is not None and (not math.isfinite(duration_seconds) or duration_seconds <= 0):
                raise HTTPException(422, "Некорректная длительность.")
            # UploadFile is disk-spooled; S3 receives the file stream without a full RAM copy.
            file.file.seek(0, 2)
            size = file.file.tell()
            file.file.seek(0)
            if size == 0 or size > 2_147_483_647:
                raise HTTPException(413, "Файл пустой или больше 2 GiB.")
            item = AdvertisingMedia(id=uuid.uuid4(), spa_id=spa_id, filename=filename,
                content_type=content_type, byte_size=size,
                duration_seconds=duration_seconds if content_type == "video/webm" else None)
            settings = Settings.from_env()
            s3_client(settings).upload_fileobj(file.file, settings.s3_bucket, item.object_key)
            try:
                playlist = locked_playlist(session, spa_id)
                session.add(item)
                playlist.item_ids = [*playlist.item_ids, str(item.id)]
                playlist.revision += 1
                session.commit()
            except Exception:
                PrivateObjectStore(settings).delete(key=item.object_key)
                raise
            return JSONResponse(playlist_projection(session, spa_id), status_code=201, headers=HEADERS)

    @app.delete("/api/advertising/{spa_id}/media/{media_id}")
    def delete(request: Request, spa_id: uuid.UUID, media_id: uuid.UUID) -> JSONResponse:
        with session_factory() as session:
            staff(session, request, unsafe=True)
            item = session.get(AdvertisingMedia, media_id)
            if item is None or item.spa_id != spa_id:
                raise HTTPException(404)
            key = item.object_key
            playlist = locked_playlist(session, spa_id)
            playlist.item_ids = [value for value in playlist.item_ids if value != str(media_id)]
            playlist.revision += 1
            session.delete(item)
            session.commit()
            PrivateObjectStore(Settings.from_env()).delete(key=key)
            return JSONResponse(playlist_projection(session, spa_id), headers=HEADERS)

    @app.get("/api/promo/advertising/playlist")
    def display_read(request: Request) -> JSONResponse:
        with session_factory() as session:
            spa_id = display_spa(session, request)
            return JSONResponse(playlist_projection(session, spa_id, display=True), headers=HEADERS)

    def deliver(request: Request, media_id: uuid.UUID, *, display: bool) -> StreamingResponse:
        with session_factory() as session:
            spa_id = display_spa(session, request) if display else None
            if not display:
                staff(session, request)
            item = session.get(AdvertisingMedia, media_id)
            if item is None or (display and item.spa_id != spa_id):
                raise HTTPException(404)
            settings = Settings.from_env()
            args: dict[str, Any] = {"Bucket": settings.s3_bucket, "Key": item.object_key}
            if request.headers.get("range"):
                args["Range"] = request.headers["range"]
            try:
                result = s3_client(settings).get_object(**args)
            except ClientError as error:
                code = error.response.get("Error", {}).get("Code")
                raise HTTPException(416 if code == "InvalidRange" else 404) from error
            body = result["Body"]
            def chunks() -> Iterator[bytes]:
                try:
                    while chunk := body.read(256 * 1024):
                        yield chunk
                finally:
                    body.close()
            headers = {**HEADERS, "Accept-Ranges": "bytes", "Content-Length": str(result["ContentLength"])}
            if "ContentRange" in result:
                headers["Content-Range"] = result["ContentRange"]
            return StreamingResponse(chunks(), media_type=item.content_type, headers=headers,
                status_code=206 if "ContentRange" in result else 200)

    @app.get("/api/advertising/media/{media_id}")
    def staff_media(request: Request, media_id: uuid.UUID) -> StreamingResponse:
        return deliver(request, media_id, display=False)

    @app.get("/api/promo/advertising/media/{media_id}")
    def display_media(request: Request, media_id: uuid.UUID) -> StreamingResponse:
        return deliver(request, media_id, display=True)

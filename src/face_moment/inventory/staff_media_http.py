"""Thin authenticated staff media routes and venue-table HTML."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date
from html import escape
from uuid import UUID

from fastapi import Cookie, FastAPI, Header, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_inventory import PhotoInventoryAccessDeniedError, PhotoInventoryNotFoundError, InvalidPhotoInventorySelectionError
from face_moment.inventory.orphan_original_cleanup import OriginalCleanupRunningError, cleanup_orphan_originals
from face_moment.inventory.staff_media import read_staff_media_venue_name, read_staff_venue_media, read_staff_photo_bytes
from face_moment.platform.auth.sessions import CsrfValidationError, InvalidSessionError, authenticate_unsafe_staff_request
from face_moment.platform.auth.sessions import get_current_principal
from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.staff_datetime import date_picker, staff_today
from face_moment.platform.staff_presentation import staff_document

_HEADERS = {'Cache-Control': 'no-store'}


def register_staff_media_routes(app: FastAPI, *, session_factory: Callable[[], Session]) -> None:
    def respond(operation: Callable[[Session], Response]) -> Response:
        try:
            with session_factory() as session:
                return operation(session)
        except InvalidSessionError as error:
            raise HTTPException(401, headers=_HEADERS) from error
        except PhotoInventoryAccessDeniedError as error:
            raise HTTPException(403, headers=_HEADERS) from error
        except PhotoInventoryNotFoundError as error:
            raise HTTPException(404, headers=_HEADERS) from error
        except InvalidPhotoInventorySelectionError as error:
            raise HTTPException(422, headers=_HEADERS) from error
        except Exception as error:
            raise HTTPException(500, headers=_HEADERS) from error

    @app.get('/staff/venue-media')
    def venue_media_page(spa_id: str | None = None, fm_staff_session: str | None = Cookie(default=None)) -> Response:
        def operation(session: Session) -> Response:
            venue_id = _uuid(spa_id)
            name = read_staff_media_venue_name(session, session_token=fm_staff_session, spa_id=venue_id)
            can_diagnose = get_current_principal(session, session_token=fm_staff_session).role in {StaffRole.OPERATOR, StaffRole.DEVELOPER}
            return HTMLResponse(staff_document(staff_media_page_html(venue_id, name, can_diagnose=can_diagnose), 'venue-media'), headers=_HEADERS)
        return respond(operation)

    @app.get('/api/inventory/venue-media')
    def venue_media_list(spa_id: str | None = None, date_from: str | None = None,
                         date_to: str | None = None, fm_staff_session: str | None = Cookie(default=None)) -> Response:
        return respond(lambda session: JSONResponse(read_staff_venue_media(session,
            session_token=fm_staff_session, spa_id=_uuid(spa_id), date_from=_date(date_from),
            date_to=_date(date_to)), headers=_HEADERS))

    @app.post('/api/inventory/orphan-originals/cleanup')
    def clean_orphan_originals(
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> Response:
        try:
            with session_factory() as session:
                principal = authenticate_unsafe_staff_request(
                    session,
                    session_token=fm_staff_session,
                    csrf_cookie_token=fm_staff_csrf,
                    csrf_header_token=x_csrf_token,
                )
                if principal.role not in {StaffRole.OPERATOR, StaffRole.DEVELOPER}:
                    raise PhotoInventoryAccessDeniedError
            with session_factory() as session:
                result = cleanup_orphan_originals(session, PrivateObjectStore(Settings.from_env()))
            return JSONResponse(
                {'schema_version': 1, 'scanned': result.scanned, 'deleted': result.deleted},
                headers=_HEADERS,
            )
        except InvalidSessionError as error:
            raise HTTPException(401, headers=_HEADERS) from error
        except (CsrfValidationError, PhotoInventoryAccessDeniedError) as error:
            raise HTTPException(403, headers=_HEADERS) from error
        except OriginalCleanupRunningError as error:
            raise HTTPException(409, headers=_HEADERS) from error
        except Exception as error:
            raise HTTPException(500, headers=_HEADERS) from error

    @app.get('/api/inventory/venue-media/{photo_id}/thumbnail')
    def thumbnail(photo_id: str, fm_staff_session: str | None = Cookie(default=None)) -> Response:
        return deliver(photo_id, fm_staff_session, thumbnail=True)

    @app.get('/api/inventory/venue-media/{photo_id}/original')
    def original(photo_id: str, fm_staff_session: str | None = Cookie(default=None)) -> Response:
        return deliver(photo_id, fm_staff_session, thumbnail=False)

    def deliver(photo_id: str, token: str | None, *, thumbnail: bool) -> Response:
        return respond(lambda session: Response(read_staff_photo_bytes(session,
            session_token=token, photo_id=_uuid(photo_id), thumbnail=thumbnail,
            object_store=PrivateObjectStore(Settings.from_env())), media_type='image/jpeg',
            headers={**_HEADERS, 'X-Content-Type-Options': 'nosniff'}))


def _uuid(value: str | None) -> UUID:
    if value is None:
        raise InvalidPhotoInventorySelectionError('missing UUID')
    try:
        return UUID(value)
    except ValueError as error:
        raise InvalidPhotoInventorySelectionError from error


def _date(value: str | None) -> date:
    if value is None or len(value) != 10:
        raise InvalidPhotoInventorySelectionError('missing or invalid date')
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise InvalidPhotoInventorySelectionError from error


def staff_media_page_html(spa_id: UUID, name: str, *, can_diagnose: bool = False) -> str:
    today = staff_today()
    diagnostics = '''<section id="capture-identity" aria-label="Диагностика лиц">
<h2>Люди и разметка</h2>
<p>Общий реестр для всех площадок. Разметьте лица кнопкой «Разметить лица» у фотографии.
Одинаковые имена могут принадлежать разным людям. Это ручные примеры для отдельной диагностики, не обучение поиска.</p>
<form id="identity-person-create"><label>Новый человек <input name="name" maxlength="200" required></label>
<button type="submit">Добавить человека</button></form>
<div id="identity-people"></div><p id="identity-error" role="alert"></p>
<h2 id="captures-heading">Захваты</h2>
<p>За выбранный выше период. JPEG лиц хранятся вместе с диагностикой 90 дней; полные кадры не сохраняются.</p>
<p>Оценки «верно/неверно» и «Кого не нашли» временные: сбрасываются при перезагрузке страницы и не меняют распознавание.</p>
<p id="captures-status" role="status"></p><div id="capture-attempts"></div>
</section>''' if can_diagnose else ''
    cleanup = '''<section class="fm-media-cleanup" aria-label="Очистка файлов">
<h2>Очистка файлов</h2>
<p>Проверяет оригиналы без записи о фотографии во всех площадках. Во время проверки новые загрузки будут временно недоступны.</p>
<button id="orphan-cleanup-open" type="button">Запустить очистку битых файлов</button>
<p id="orphan-cleanup-status" role="status" aria-live="polite"></p>
<dialog id="orphan-cleanup-dialog" aria-labelledby="orphan-cleanup-warning">
<p id="orphan-cleanup-warning">Это может занять до 30 минут, сервер в это время будет практически неработоспособен</p>
<div class="fm-media-cleanup-actions"><button id="orphan-cleanup-confirm" type="button">ДА!</button>
<button id="orphan-cleanup-cancel" type="button">Отмена</button></div>
</dialog></section>''' if can_diagnose else ''
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Медиа площадки</title>
<link rel="stylesheet" href="/client/staff-media.css">
<link rel="stylesheet" href="/client/capture-identity.css">
<script type="module" src="/client/staff-media.js"></script></head><body><main>
<section data-staff-media data-spa-id="{spa_id}" data-capture-diagnostics="{str(can_diagnose).lower()}">
<a class="fm-media-back" href="/staff/photo-inventory?spa_id={spa_id}">← Библиотека</a>
<h2 class="fm-media-venue">{escape(name)}</h2>
<form id="media-filter" class="fm-media-filter">
<label for="media-date-from">Загружены с{date_picker('media-date-from', today)}</label>
<label for="media-date-to">По{date_picker('media-date-to', today)}</label>
<button type="submit">Показать фотографии</button>
</form>
<p class="fm-media-hint">Оба дня включены · UTC+7 · Фото без найденных лиц не отображаются</p>
<p id="media-error" role="alert"></p><p id="media-status" role="status" aria-live="polite">Загружаем фотографии…</p>
<table class="fm-media-table"><caption>Нажмите на превью, чтобы открыть оригинал в новой вкладке.</caption>
<thead><tr><th scope="col">Фото</th><th scope="col">Добавлено</th><th scope="col">Снято</th>
<th scope="col">Размер</th><th scope="col">Обработка</th><th scope="col">Действие</th></tr></thead>
<tbody id="media-rows"></tbody></table>
<p class="fm-media-hint">Удалённые фотографии скрываются из поиска. Их можно восстановить в библиотеке.</p>
{diagnostics}
{cleanup}
</section></main></body></html>'''

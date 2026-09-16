from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, timezone
from html import escape
import uuid
from zoneinfo import ZoneInfo

from fastapi import Cookie, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from face_moment.platform.staff_presentation import staff_document
from face_moment.platform.staff_datetime import date_picker
from sqlalchemy.orm import Session

from face_moment.platform.auth.sessions import (
    CsrfValidationError,
    InvalidSessionError,
)
from face_moment.processing.model_admission import ModelAdmissionError
from face_moment.serving_control.active_search_date import (
    ActiveSearchDateAccessDeniedError,
    ActiveSearchDateRecord,
    ActiveSearchDateSpa,
    ActiveSearchDateSpaNotFoundError,
    list_active_search_date_spas,
    read_active_search_date,
    rename_spa,
    create_spa,
    update_active_search_date,
    SearchDatesRecord,
    read_search_dates,
    update_search_dates,
)
from face_moment.serving_control.display_client_admin import (
    DisplayClientAdminAccessDeniedError,
    DisplayClientAdminRecord,
    read_display_client_admin,
    rename_display_client,
    create_display_client,
)
from face_moment.serving_control.display_client_access import DisplayClientNotFoundError, UnknownDisplayClientSpaError
from face_moment.serving_control.ingest_target import InactiveIngestTargetError
from face_moment.serving_control.detector_thresholds import DetectorKind, update_detector_threshold
from face_moment.serving_control.similarity_threshold import read_similarity_threshold, save_similarity_threshold
from face_moment.serving_control.realtime_context import CalibrationRecommendationConflictError, CalibrationServingSnapshot
from face_moment.serving_control.ingest_target import CommittedServingTargetUnavailableError, IneligibleIngestTargetError


class SpaCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(strict=True, min_length=1, max_length=255)
    timezone: str = Field(strict=True, min_length=1, max_length=255)


class SimilarityThresholdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold: float = Field(strict=True)
    pipeline_revision_id: uuid.UUID
    settings_revision: int = Field(strict=True, gt=0)


def _similarity_response(record: CalibrationServingSnapshot) -> JSONResponse:
    return JSONResponse({
        "spa_id": str(record.spa_id), "pipeline_revision_id": str(record.pipeline_revision_id),
        "pipeline_code": record.pipeline_code.value, "threshold": record.reference_threshold,
        "settings_revision": record.settings_revision,
    }, headers={"Cache-Control": "no-store"})


class DetectorThresholdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold: float = Field(strict=True, gt=0, le=1)


class ActiveSearchDateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visit_date: date


class DisplayClientNameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)


class DisplayClientCreateRequest(DisplayClientNameRequest):
    spa_id: uuid.UUID


class ActiveSearchDateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    spa_id: uuid.UUID
    active_visit_date: date | None
    settings_revision: int
    updated_at: datetime | None


class SearchDatesUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_today: StrictBool
    date_from: date | None = None
    date_to: date | None = None


class SearchDatesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    schema_version: int = 1
    spa_id: uuid.UUID
    search_today: bool
    date_from: date | None
    date_to: date | None
    timezone: str
    today: date
    settings_revision: int
    updated_at: datetime | None


def register_display_client_admin_routes(
    app: FastAPI, *, session_factory: Callable[[], Session]
) -> None:
    @app.post("/api/serving/display-clients")
    def create_display_client_route(
        payload: DisplayClientCreateRequest,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> JSONResponse:
        with _database_session(session_factory) as database_session:
            try:
                client_id = create_display_client(database_session,
                    session_token=fm_staff_session, csrf_cookie_token=fm_staff_csrf,
                    csrf_header_token=x_csrf_token, spa_id=payload.spa_id, name=payload.name)
                database_session.commit()
            except InvalidSessionError as error:
                raise HTTPException(status_code=401) from error
            except (CsrfValidationError, DisplayClientAdminAccessDeniedError) as error:
                raise HTTPException(status_code=403) from error
            except UnknownDisplayClientSpaError as error:
                raise HTTPException(status_code=404, detail="Площадка не найдена.") from error
            except InactiveIngestTargetError as error:
                raise HTTPException(status_code=409, detail="Площадка отключена.") from error
            except ValueError as error:
                raise HTTPException(status_code=422, detail="Введите название экрана от 1 до 255 символов.") from error
        return JSONResponse({"display_client_id": str(client_id), "spa_id": str(payload.spa_id)},
            status_code=201, headers={"Cache-Control": "no-store"})

    @app.put("/api/serving/display-clients/{display_client_id}/name")
    def rename_display_client_route(
        display_client_id: uuid.UUID, payload: DisplayClientNameRequest,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> JSONResponse:
        with _database_session(session_factory) as database_session:
            try:
                name = rename_display_client(
                    database_session, session_token=fm_staff_session,
                    csrf_cookie_token=fm_staff_csrf, csrf_header_token=x_csrf_token,
                    display_client_id=display_client_id, name=payload.name,
                )
                database_session.commit()
            except InvalidSessionError as error:
                raise HTTPException(status_code=401) from error
            except (CsrfValidationError, DisplayClientAdminAccessDeniedError) as error:
                raise HTTPException(status_code=403) from error
            except DisplayClientNotFoundError as error:
                raise HTTPException(status_code=404) from error
            except ValueError as error:
                raise HTTPException(status_code=422, detail="Название должно содержать от 1 до 255 символов") from error
        return JSONResponse({"display_client_id": str(display_client_id), "name": name}, headers={"Cache-Control": "no-store"})

    @app.get("/staff/display-clients", response_class=HTMLResponse)
    def display_client_admin_page(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        with _database_session(session_factory) as database_session:
            try:
                clients = read_display_client_admin(
                    database_session,
                    session_token=fm_staff_session,
                )
                spas = list_active_search_date_spas(database_session, session_token=fm_staff_session)
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
            except DisplayClientAdminAccessDeniedError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error

        response = HTMLResponse(staff_document(_display_client_page_html(clients, spas), "display-clients"))
        response.headers["Cache-Control"] = "no-store"
        return response


def register_active_search_date_routes(
    app: FastAPI, *, session_factory: Callable[[], Session]
) -> None:
    @app.post("/api/serving/spas")
    def create_spa_route(
        payload: SpaCreateRequest,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> JSONResponse:
        with _database_session(session_factory) as database_session:
            try:
                venue = create_spa(database_session, name=payload.name, timezone=payload.timezone,
                    session_token=fm_staff_session, csrf_cookie_token=fm_staff_csrf,
                    csrf_header_token=x_csrf_token)
                database_session.commit()
            except InvalidSessionError as error:
                raise HTTPException(status_code=401) from error
            except (CsrfValidationError, ActiveSearchDateAccessDeniedError) as error:
                raise HTTPException(status_code=403) from error
            except (CommittedServingTargetUnavailableError, IneligibleIngestTargetError) as error:
                raise HTTPException(status_code=409, detail="Общая модель недоступна или настройки площадок противоречат друг другу.") from error
            except ModelAdmissionError as error:
                raise HTTPException(status_code=503, detail="Не удалось проверить модель SFace. Проверьте настройки SFACE_* и файлы YuNet/SFace. Площадка не создана.") from error
            except ValueError as error:
                raise HTTPException(status_code=422, detail="Проверьте название и часовой пояс площадки.") from error
        return JSONResponse({"spa_id": str(venue.spa_id), "name": venue.name, "timezone": venue.timezone},
            status_code=201, headers={"Cache-Control": "no-store"})

    @app.get("/api/serving/spas/{spa_id}/similarity-threshold")
    def read_similarity_threshold_route(
        spa_id: uuid.UUID, fm_staff_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        with _database_session(session_factory) as database_session:
            try:
                record = read_similarity_threshold(database_session, spa_id=spa_id, session_token=fm_staff_session)
            except InvalidSessionError as error:
                raise HTTPException(status_code=401) from error
            except ActiveSearchDateAccessDeniedError as error:
                raise HTTPException(status_code=403) from error
            except ActiveSearchDateSpaNotFoundError as error:
                raise HTTPException(status_code=404) from error
            except CalibrationRecommendationConflictError as error:
                raise HTTPException(status_code=503, detail="Текущая модель или её настройки недоступны.") from error
        return _similarity_response(record)

    @app.put("/api/serving/spas/{spa_id}/similarity-threshold")
    def write_similarity_threshold_route(
        spa_id: uuid.UUID, payload: SimilarityThresholdRequest,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> JSONResponse:
        with _database_session(session_factory) as database_session:
            try:
                record = save_similarity_threshold(
                    database_session, spa_id=spa_id, threshold=payload.threshold,
                    pipeline_revision_id=payload.pipeline_revision_id, settings_revision=payload.settings_revision,
                    session_token=fm_staff_session, csrf_cookie_token=fm_staff_csrf, csrf_header_token=x_csrf_token,
                )
                database_session.commit()
            except InvalidSessionError as error:
                raise HTTPException(status_code=401) from error
            except (CsrfValidationError, ActiveSearchDateAccessDeniedError) as error:
                raise HTTPException(status_code=403) from error
            except ActiveSearchDateSpaNotFoundError as error:
                raise HTTPException(status_code=404) from error
            except CalibrationRecommendationConflictError as error:
                raise HTTPException(status_code=409, detail="Модель или настройки изменились. Обновите страницу.") from error
            except ValueError as error:
                raise HTTPException(status_code=422, detail="Введите конечное число от −1 до 1.") from error
        return _similarity_response(record)

    @app.put("/api/serving/spas/{spa_id}/detector-thresholds/{detector}")
    def write_detector_threshold_route(
        spa_id: uuid.UUID, detector: DetectorKind, payload: DetectorThresholdRequest,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> JSONResponse:
        with _database_session(session_factory) as database_session:
            try:
                threshold = update_detector_threshold(
                    database_session, spa_id=spa_id, detector=detector,
                    threshold=payload.threshold, session_token=fm_staff_session,
                    csrf_cookie_token=fm_staff_csrf, csrf_header_token=x_csrf_token,
                )
                database_session.commit()
            except InvalidSessionError as error:
                raise HTTPException(status_code=401) from error
            except (CsrfValidationError, ActiveSearchDateAccessDeniedError) as error:
                raise HTTPException(status_code=403) from error
            except ActiveSearchDateSpaNotFoundError as error:
                raise HTTPException(status_code=404) from error
        return JSONResponse({"threshold": threshold}, headers={"Cache-Control": "no-store"})

    @app.get("/api/serving/spas/{spa_id}/search-dates", response_model=SearchDatesResponse)
    def read_search_dates_route(
        spa_id: uuid.UUID, fm_staff_session: str | None = Cookie(default=None),
    ) -> JSONResponse:
        with _database_session(session_factory) as database_session:
            try:
                record = read_search_dates(database_session, session_token=fm_staff_session, spa_id=spa_id)
            except InvalidSessionError as error:
                raise HTTPException(status_code=401) from error
            except ActiveSearchDateAccessDeniedError as error:
                raise HTTPException(status_code=403) from error
            except ActiveSearchDateSpaNotFoundError as error:
                raise HTTPException(status_code=404) from error
        return _search_dates_response(record)

    @app.put("/api/serving/spas/{spa_id}/search-dates", response_model=SearchDatesResponse)
    def write_search_dates_route(
        spa_id: uuid.UUID, payload: SearchDatesUpdateRequest,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> JSONResponse:
        with _database_session(session_factory) as database_session:
            try:
                record = update_search_dates(
                    database_session, session_token=fm_staff_session,
                    csrf_cookie_token=fm_staff_csrf, csrf_header_token=x_csrf_token,
                    spa_id=spa_id, search_today=payload.search_today,
                    date_from=payload.date_from, date_to=payload.date_to,
                )
                database_session.commit()
            except InvalidSessionError as error:
                raise HTTPException(status_code=401) from error
            except (CsrfValidationError, ActiveSearchDateAccessDeniedError) as error:
                raise HTTPException(status_code=403) from error
            except ActiveSearchDateSpaNotFoundError as error:
                raise HTTPException(status_code=404) from error
            except ValueError as error:
                raise HTTPException(status_code=422, detail="Укажите обе даты: «С» не должна быть позже «По».") from error
        return _search_dates_response(record)

    @app.put("/api/serving/spas/{spa_id}/name")
    def rename_spa_route(
        spa_id: uuid.UUID, payload: DisplayClientNameRequest,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> JSONResponse:
        with _database_session(session_factory) as database_session:
            try:
                name = rename_spa(
                    database_session, session_token=fm_staff_session,
                    csrf_cookie_token=fm_staff_csrf, csrf_header_token=x_csrf_token,
                    spa_id=spa_id, name=payload.name,
                )
                database_session.commit()
            except InvalidSessionError as error:
                raise HTTPException(status_code=401) from error
            except (CsrfValidationError, ActiveSearchDateAccessDeniedError) as error:
                raise HTTPException(status_code=403) from error
            except ActiveSearchDateSpaNotFoundError as error:
                raise HTTPException(status_code=404) from error
            except ValueError as error:
                raise HTTPException(status_code=422, detail="Название должно содержать от 1 до 255 символов") from error
        return JSONResponse({"spa_id": str(spa_id), "name": name}, headers={"Cache-Control": "no-store"})

    @app.get("/staff/spas", response_class=HTMLResponse)
    def spa_admin_page(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        with _database_session(session_factory) as database_session:
            try:
                spas = list_active_search_date_spas(database_session, session_token=fm_staff_session)
            except InvalidSessionError as error:
                raise HTTPException(status_code=401) from error
            except ActiveSearchDateAccessDeniedError as error:
                raise HTTPException(status_code=403) from error
        return HTMLResponse(staff_document(_spa_admin_page_html(spas), "spas"), headers={"Cache-Control": "no-store"})

    @app.get("/staff/search-settings", response_class=HTMLResponse)
    def active_search_date_page(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> RedirectResponse:
        with _database_session(session_factory) as database_session:
            try:
                list_active_search_date_spas(
                    database_session,
                    session_token=fm_staff_session,
                )
            except InvalidSessionError as error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED
                ) from error
            except ActiveSearchDateAccessDeniedError as error:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN
                ) from error

        return RedirectResponse("/staff/spas", status_code=303, headers={"Cache-Control": "no-store"})

    @app.get(
        "/api/serving/spas/{spa_id}/active-visit-date",
        response_model=ActiveSearchDateResponse,
    )
    def read_active_search_date_route(
        spa_id: uuid.UUID,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> ActiveSearchDateResponse:
        with _database_session(session_factory) as database_session:
            try:
                record = read_active_search_date(
                    database_session,
                    session_token=fm_staff_session,
                    spa_id=spa_id,
                )
            except InvalidSessionError as error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED
                ) from error
            except ActiveSearchDateAccessDeniedError as error:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN
                ) from error
            except ActiveSearchDateSpaNotFoundError as error:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
        return _active_search_date_response(record)

    @app.put(
        "/api/serving/spas/{spa_id}/active-visit-date",
        response_model=ActiveSearchDateResponse,
    )
    def write_active_search_date_route(
        spa_id: uuid.UUID,
        payload: ActiveSearchDateUpdateRequest,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> ActiveSearchDateResponse:
        with _database_session(session_factory) as database_session:
            try:
                record = update_active_search_date(
                    database_session,
                    session_token=fm_staff_session,
                    csrf_cookie_token=fm_staff_csrf,
                    csrf_header_token=x_csrf_token,
                    spa_id=spa_id,
                    active_visit_date=payload.visit_date,
                )
                database_session.commit()
            except InvalidSessionError as error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED
                ) from error
            except (CsrfValidationError, ActiveSearchDateAccessDeniedError) as error:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN
                ) from error
            except ActiveSearchDateSpaNotFoundError as error:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
        return _active_search_date_response(record)


def _database_session(session_factory: Callable[[], Session]) -> Session:
    return session_factory()


def _display_client_page_html(clients: Sequence[DisplayClientAdminRecord], spas: Sequence[ActiveSearchDateSpa] = ()) -> str:
    names = {spa.spa_id: spa.name for spa in spas}
    options = "".join(f'<option value="{spa.spa_id}">{escape(spa.name)}</option>' for spa in spas)
    cards = "".join(
        '<article class="fm-device-card">'
        f'<a class="fm-device-face" href="/client1" target="_blank" rel="noopener noreferrer" '
        f'aria-label="Открыть экран «{escape(client.name, quote=True)}» в новой вкладке" data-tilt>'
        f'<p class="fm-eyebrow">КИОСК / {"РАЗРЕШЁН" if client.active else "ОТКЛЮЧЁН"}</p>'
        f'<h2>{escape(client.name)}</h2></a>'
        f'<p class="fm-device-meta">Площадка: {escape(names.get(client.spa_id, str(client.spa_id)))}<br>'
        f'ID экрана: …{escape(str(client.display_client_id)[-5:])}</p>'
        f'<form class="fm-device-rename" data-client-id="{client.display_client_id}">'
        f'<label>Название экрана<input name="name" value="{escape(client.name, quote=True)}" required maxlength="255"></label>'
        '<button type="submit">Сохранить название</button><p role="status"></p></form>'
        '<div class="fm-token"><span class="fm-eyebrow">Токен подключения</span>'
        f'<code>{escape(client.token_value)}</code>'
        '<button class="fm-button-secondary" type="button" data-copy-token>Скопировать токен</button>'
        '<span class="fm-copy-status" role="status"></span>'
        f'<a class="fm-button fm-button-secondary fm-device-advertising" href="/staff/advertising?spa_id={client.spa_id}">Реклама</a>'
        '</div></article>'
        for client in clients
    )
    rows = "".join(
        "<tr>"
        f'<td data-field="display-client-id">{escape(str(client.display_client_id))}</td>'
        f'<td data-field="name">{escape(client.name)}</td>'
        f'<td data-field="spa-id">{escape(str(client.spa_id))}</td>'
        f'<td data-field="active">{str(client.active).lower()}</td>'
        f'<td data-field="token"><code>{escape(client.token_value)}</code></td>'
        "</tr>"
        for client in clients
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Display client settings</title>
  <script type="module" src="/client/display-client-create.js"></script>
  <style>.fm-display-create[hidden] {{ display: none; }} .fm-display-create {{ max-width: 32rem; margin-block: 1rem; }} [data-show-display-create] {{ margin-bottom: 1rem; }}</style>
</head>
<body>
  <main>
    <h1>Display client settings</h1>
    <button type="button" data-show-display-create aria-expanded="false" aria-controls="display-create"{' disabled' if not spas else ''}>Добавить экран</button>
    {'' if spas else '<p>Сначала добавьте площадку в разделе «Площадки».</p>'}
    <section id="display-create" class="fm-device-card fm-display-create" hidden>
      <h2>Новый экран</h2><form data-display-create>
        <label>Название экрана<input name="name" required maxlength="255" autocomplete="off"></label>
        <label>Площадка<select name="spa_id" required><option value="" selected disabled>Выберите площадку</option>{options}</select></label>
        <div><button type="submit">Создать экран</button> <button type="button" data-cancel-display-create>Отмена</button></div>
        <p role="status" aria-live="polite"></p>
      </form>
    </section>
    <div class="fm-device-list">{cards or '<p>Экраны пока не настроены.</p>'}</div>
    <details class="fm-device-table"><summary>Таблица настроенных экранов</summary><table>
      <caption>Configured kiosks and current tokens</caption>
      <thead>
        <tr>
          <th scope="col">Display client ID</th>
          <th scope="col">Name</th>
          <th scope="col">SPA ID</th>
          <th scope="col">Active</th>
          <th scope="col">Current token</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table></details>
  </main>
</body>
</html>"""


def _active_search_date_response(record: ActiveSearchDateRecord) -> ActiveSearchDateResponse:
    return ActiveSearchDateResponse(
        schema_version=1,
        spa_id=record.spa_id,
        active_visit_date=record.active_visit_date,
        settings_revision=record.settings_revision,
        updated_at=record.updated_at,
    )


def _search_dates_response(record: SearchDatesRecord) -> JSONResponse:
    return JSONResponse(
        SearchDatesResponse.model_validate(record).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


def _spa_admin_page_html(spas: Sequence[ActiveSearchDateSpa]) -> str:
    # IANA Etc/GMT identifiers use the opposite sign to the displayed offset.
    timezone_options = "".join(
        f'<option value="Etc/GMT-{offset}"{" selected" if offset == 7 else ""}>GMT+{offset}</option>'
        for offset in range(1, 11))
    cards = "".join(
        f'''<article class="fm-device-card"><h2 data-spa-title>{escape(spa.name)}</h2>
<details class="fm-spa-settings"><summary>Настройки площадки</summary>
<form data-spa-rename data-spa-id="{spa.spa_id}">
<label>Название площадки<input name="name" value="{escape(spa.name, quote=True)}" required maxlength="255"></label>
<button type="submit">Сохранить название</button><p role="status" aria-live="polite"></p>
</form>{_spa_search_dates_form(spa)}{_spa_similarity_form(spa)}{_spa_detector_forms(spa)}</details></article>'''
        for spa in spas
    ) or '<p>Нет доступных площадок.</p>'
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Площадки</title>
<link rel="stylesheet" href="/client/spa-search-settings.css">
<script type="module" src="/client/spa-search-settings.js"></script></head><body>
<main><h1>Площадки</h1>
<button type="button" data-show-spa-create aria-expanded="false" aria-controls="spa-create">Добавить площадку</button>
<section id="spa-create" class="fm-device-card fm-spa-create" hidden>
<h2>Новая площадка</h2><form data-spa-create>
<label>Название площадки<input name="name" required maxlength="255" autocomplete="off"></label>
<label>Часовой пояс<select name="timezone" required>{timezone_options}</select></label>
<p>Поиск за сегодня, порог сходства 0.38. Настройки можно изменить после создания.</p>
<div><button type="submit">Создать площадку</button> <button type="button" data-cancel-spa-create>Отмена</button></div>
<p role="status" aria-live="polite"></p></form></section>
<div class="fm-device-list">{cards}</div></main></body></html>'''


def _spa_similarity_form(spa: ActiveSearchDateSpa) -> str:
    return f'''<form class="fm-spa-search" data-similarity-threshold data-spa-id="{spa.spa_id}">
<label class="fm-search-toggle" title="определяет сходство лиц во время  Захвата на выходе с фотографиями от фотографов. По умолчанию 0.38">
<input type="checkbox" role="switch" name="edit_threshold" disabled>
<span>Изменить порог сходства</span></label>
<p>Текущая модель: <span data-serving-model>загрузка…</span></p>
<div class="fm-detector-value"><label>Порог
<input type="number" name="threshold" min="-1" max="1" step="any" required disabled></label>
<button type="submit" disabled>Сохранить порог</button></div>
<p role="status" aria-live="polite">Загрузка настроек…</p></form>'''


def _spa_search_dates_form(spa: ActiveSearchDateSpa) -> str:
    today = datetime.now(timezone.utc).astimezone(ZoneInfo(spa.timezone)).date()
    start = (spa.date_from or today).isoformat()
    end = (spa.date_to or spa.date_from or today).isoformat()
    prefix = f"search-{spa.spa_id}"
    return f'''<form class="fm-spa-search" data-spa-search data-spa-id="{spa.spa_id}">
<h3>Поиск камерой на выходе</h3>
<label class="fm-search-toggle"><input type="checkbox" role="switch" name="search_today"{' checked' if spa.search_today else ''}>
<span>камера на выходе ищет лица ТОЛЬКО из сегодняшних фоток</span></label>
<p class="fm-search-hint">«Сегодня» определяется по времени площадки: {escape(spa.timezone)}.</p>
<div data-manual-search{' hidden' if spa.search_today else ''}>
<fieldset class="fm-search-dates" data-manual-dates{' disabled' if spa.search_today else ''}>
<legend>За какие дни искать фотографии</legend>
<label for="{prefix}-from">С{date_picker(prefix + '-from', start, name='date_from')}</label>
<label for="{prefix}-to">По{date_picker(prefix + '-to', end, name='date_to')}</label>
</fieldset>
<p class="fm-search-hint">Обе даты входят в период поиска.</p>
<button type="submit">Сохранить поиск</button></div><p role="status" aria-live="polite"></p>
</form>'''


def _spa_detector_forms(spa: ActiveSearchDateSpa) -> str:
    return "".join(
        f'''<form class="fm-spa-search" data-detector-threshold data-spa-id="{spa.spa_id}" data-detector="{detector}">
<label class="fm-search-toggle" title="{escape(hint, quote=True)}">
<input type="checkbox" role="switch" name="edit_threshold">
<span>{label}</span></label>
<div class="fm-detector-value"><label>Порог
<input type="number" name="threshold" min="0" max="1" step="any" value="{value}" required disabled></label>
<button type="submit" disabled>Сохранить порог</button></div>
<p role="status" aria-live="polite"></p></form>'''
        for detector, value, label, hint in (
            ("photo_yunet", spa.photo_yunet_threshold,
             "Изменить порог детектора YuNet для фоток от фотографов",
             "ниже порог, меньше лиц потеряем но выше вероятность воспринять чепуху за лицо, хотя это и не страшно. Этот детектор не распознает лица, а лишь передает распознавалке места на фотке, где лица могут находиться"),
            ("capture_blazeface", spa.capture_blazeface_threshold,
             "Изменить порог детектора Захвата",
             "Ниже порог, есть риск распознать одежду как лицо или пробегающую кошку :)"),
        )
    )

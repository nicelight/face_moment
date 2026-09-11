"""Thin HTTP transport for inventory-owned staff reads."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from html import escape

from datetime import date, datetime
from ipaddress import ip_address
from uuid import UUID

from fastapi import Cookie, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from starlette.datastructures import UploadFile
from sqlalchemy.orm import Session

from face_moment.serving_control.ingest_target import IngestTargetRepository
from face_moment.infrastructure.settings import Settings
from face_moment.platform.staff_presentation import staff_document
from face_moment.platform.staff_datetime import date_picker, datetime_range_fields, staff_today
from face_moment.inventory.ingest_targets import (
    InvalidSessionError,
    IngestTargetContext,
    PhotographerAccessDeniedError,
    read_ingest_target_context,
)
from face_moment.inventory.photo_upload import (
    InvalidPhotoUploadError,
    PhotoUploadRateLimiter,
    PhotoUploadRateLimitError,
    PhotographerAccessDeniedError as UploadPhotographerAccessDeniedError,
    upload_photo,
)
from face_moment.inventory.photo_processing_status import (
    PhotoProcessingStatusAccessDeniedError,
    PhotoProcessingStatusNotFoundError,
    read_photo_processing_status,
)
from face_moment.inventory.photo_inventory import (
    InvalidPhotoInventorySelectionError,
    PhotoInventoryAccessDeniedError,
    PhotoInventoryNotFoundError,
    read_photo_inventory,
    set_photo_visibility,
)
from face_moment.inventory.processing_health import (
    InvalidProcessingHealthIntervalError,
    ProcessingHealthAccessDeniedError,
    ProcessingHealthNotFoundError,
    authorize_processing_health_access,
    read_processing_health,
)
from face_moment.inventory.recent_statistics import (
    RecentStatisticsAccessDeniedError,
    RecentStatisticsNotFoundError,
    authorize_recent_statistics_access,
    read_recent_statistics,
)
from face_moment.inventory.validation import InvalidJpegCandidateError
from face_moment.inventory.hard_purge import (
    HardPurgeService,
    InventoryPurgeAccessDeniedError,
    InventoryPurgeConflictError,
)
from face_moment.platform.auth.sessions import (
    CsrfValidationError,
    InvalidSessionError,
    get_current_principal,
)


_NO_STORE_HEADERS = {"Cache-Control": "no-store"}


def register_ingest_target_routes(
    app: FastAPI, *, session_factory: Callable[[], Session]
) -> None:
    def purge_response(operation: Callable[[HardPurgeService], dict[str, object]]) -> Response:
        from fastapi.responses import JSONResponse

        with _database_session(session_factory) as session:
            try:
                payload = operation(HardPurgeService(session))
            except InvalidSessionError as error:
                raise HTTPException(401, headers=_NO_STORE_HEADERS) from error
            except (CsrfValidationError, InventoryPurgeAccessDeniedError) as error:
                raise HTTPException(403, headers=_NO_STORE_HEADERS) from error
            except InventoryPurgeConflictError as error:
                raise HTTPException(409, headers=_NO_STORE_HEADERS) from error
            except Exception as error:
                raise HTTPException(500, headers=_NO_STORE_HEADERS) from error
        return JSONResponse(payload, headers=_NO_STORE_HEADERS)

    @app.get("/api/inventory/hard-purge")
    def read_hard_purge(fm_staff_session: str | None = Cookie(default=None)) -> Response:
        return purge_response(lambda service: service.read(session_token=fm_staff_session))

    @app.post("/api/inventory/hard-purge")
    async def confirm_hard_purge(
        request: Request,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> Response:
        await _validate_purge_payload(request, confirmation=True)
        return purge_response(lambda service: service.confirm(
            session_token=fm_staff_session, csrf_cookie_token=fm_staff_csrf,
            csrf_header_token=x_csrf_token,
        ))

    @app.post("/api/inventory/restore-all")
    async def restore_all_photos(
        request: Request,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> Response:
        await _validate_purge_payload(request, confirmation=False)
        return purge_response(lambda service: service.restore_all(
            session_token=fm_staff_session, csrf_cookie_token=fm_staff_csrf,
            csrf_header_token=x_csrf_token,
        ))

    @app.get("/staff/photo-upload", response_class=HTMLResponse)
    def photo_upload_page(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        with _database_session(session_factory) as database_session:
            try:
                read_ingest_target_context(
                    database_session,
                    session_token=fm_staff_session,
                )
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
            except PhotographerAccessDeniedError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error
        return HTMLResponse(staff_document(_photo_upload_page_html(), "photo-upload"))

    @app.get("/staff/processing-health", response_class=HTMLResponse)
    def processing_health_page(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        with _database_session(session_factory) as database_session:
            try:
                authorize_processing_health_access(
                    database_session,
                    session_token=fm_staff_session,
                )
                spas = IngestTargetRepository(database_session).list_active_spa_names()
            except ProcessingHealthAccessDeniedError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
        return HTMLResponse(staff_document(_processing_health_page_html(spas), "processing-health"), headers=_NO_STORE_HEADERS)

    @app.get("/staff/photo-inventory", response_class=HTMLResponse)
    def photo_inventory_page(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        with _database_session(session_factory) as database_session:
            try:
                get_current_principal(
                    database_session,
                    session_token=fm_staff_session,
                )
                spas = IngestTargetRepository(database_session).list_active_spa_names()
            except InvalidSessionError as error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers=_NO_STORE_HEADERS,
                ) from error
        response = HTMLResponse(staff_document(_photo_inventory_page_html(spas), "photo-inventory"))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/inventory/ingest-targets", response_model=None)
    def ingest_targets(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> IngestTargetContext:
        with _database_session(session_factory) as database_session:
            try:
                return read_ingest_target_context(
                    database_session,
                    session_token=fm_staff_session,
                )
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
            except PhotographerAccessDeniedError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error

    @app.get("/api/inventory/photos/{photo_id}/processing", response_model=None)
    def photo_processing_status(
        photo_id: UUID,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> dict[str, object]:
        with _database_session(session_factory) as database_session:
            try:
                return read_photo_processing_status(
                    database_session,
                    session_token=fm_staff_session,
                    photo_id=photo_id,
                ).as_response()
            except PhotoProcessingStatusAccessDeniedError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error
            except PhotoProcessingStatusNotFoundError as error:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
            except Exception as error:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from error

    @app.get("/api/inventory/photos", response_model=None)
    def photo_inventory(
        response: Response,
        spa_id: str | None = None,
        visit_date: str | None = None,
        captured_from: str | None = None,
        captured_before: str | None = None,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> dict[str, object]:
        try:
            parsed_spa_id = UUID(spa_id) if spa_id is not None else None
            parsed_visit_date = date.fromisoformat(visit_date) if visit_date else None
            parsed_from = datetime.fromisoformat(captured_from) if captured_from else None
            parsed_before = (
                datetime.fromisoformat(captured_before) if captured_before else None
            )
            if (
                parsed_spa_id is None
                or parsed_visit_date is None
                or parsed_from is None
                or parsed_before is None
            ):
                raise ValueError
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                headers=_NO_STORE_HEADERS,
            ) from error
        with _database_session(session_factory) as database_session:
            try:
                result = read_photo_inventory(
                    database_session,
                    session_token=fm_staff_session,
                    spa_id=parsed_spa_id,
                    visit_date=parsed_visit_date,
                    captured_from=parsed_from,
                    captured_before=parsed_before,
                )
            except InvalidPhotoInventorySelectionError as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except PhotoInventoryAccessDeniedError as error:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except PhotoInventoryNotFoundError as error:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except InvalidSessionError as error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except Exception as error:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    headers=_NO_STORE_HEADERS,
                ) from error
        response.headers["Cache-Control"] = "no-store"
        return result.as_response()

    @app.put("/api/inventory/photos/{photo_id}/visibility", response_model=None)
    async def photo_visibility(
        photo_id: str,
        request: Request,
        response: Response,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        try:
            parsed_photo_id = UUID(photo_id)
            payload = await request.json()
            if (
                not isinstance(payload, dict)
                or set(payload) != {"schema_version", "active"}
                or type(payload["schema_version"]) is not int
                or payload["schema_version"] != 1
                or type(payload["active"]) is not bool
            ):
                raise ValueError
        except (ValueError, TypeError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                headers=_NO_STORE_HEADERS,
            ) from error
        with _database_session(session_factory) as database_session:
            try:
                result = set_photo_visibility(
                    database_session,
                    session_token=fm_staff_session,
                    csrf_cookie_token=fm_staff_csrf,
                    csrf_header_token=x_csrf_token,
                    photo_id=parsed_photo_id,
                    active=payload["active"],
                )
            except InventoryPurgeConflictError as error:
                raise HTTPException(409, headers=_NO_STORE_HEADERS) from error
            except (CsrfValidationError, PhotoInventoryAccessDeniedError) as error:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except PhotoInventoryNotFoundError as error:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except InvalidSessionError as error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except Exception as error:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    headers=_NO_STORE_HEADERS,
                ) from error
        response.headers["Cache-Control"] = "no-store"
        return result.as_response()

    @app.get("/api/inventory/processing-health", response_model=None)
    def processing_health(
        spa_id: UUID,
        accepted_from: datetime | None = None,
        accepted_before: datetime | None = None,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> dict[str, object]:
        settings = Settings.from_env()
        with _database_session(session_factory) as database_session:
            try:
                return read_processing_health(
                    database_session,
                    settings=settings,
                    session_token=fm_staff_session,
                    spa_id=spa_id,
                    accepted_from=accepted_from,
                    accepted_before=accepted_before,
                ).as_response()
            except ProcessingHealthAccessDeniedError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error
            except ProcessingHealthNotFoundError as error:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
            except InvalidProcessingHealthIntervalError as error:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY) from error
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
            except Exception as error:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from error

    @app.get("/api/inventory/recent-statistics", response_model=None)
    def recent_statistics(
        response: Response,
        spa_id: str | None = None,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> dict[str, object]:
        try:
            parsed_spa_id = UUID(spa_id) if spa_id is not None else None
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                headers=_NO_STORE_HEADERS,
            ) from error
        if parsed_spa_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                headers=_NO_STORE_HEADERS,
            )
        with _database_session(session_factory) as database_session:
            try:
                result = read_recent_statistics(
                    database_session,
                    session_token=fm_staff_session,
                    spa_id=parsed_spa_id,
                )
            except RecentStatisticsAccessDeniedError as error:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except RecentStatisticsNotFoundError as error:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except InvalidSessionError as error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers=_NO_STORE_HEADERS,
                ) from error
            except Exception as error:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    headers=_NO_STORE_HEADERS,
                ) from error
        response.headers["Cache-Control"] = "no-store"
        return result.as_response()

    @app.post("/api/inventory/photos", response_model=None)
    async def photo_upload(
        request: Request,
        response: Response,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        spa_id, visit_date, photo_bytes = await _photo_upload_form(request)
        settings = Settings.from_env()
        with _database_session(session_factory) as database_session:
            try:
                result = upload_photo(
                    database_session,
                    settings=settings,
                    rate_limiter=_photo_upload_limiter(app, settings),
                    session_token=fm_staff_session,
                    csrf_cookie_token=fm_staff_csrf,
                    csrf_header_token=x_csrf_token,
                    ip_address=_client_ip(request),
                    spa_id=spa_id,
                    visit_date=visit_date,
                    photo_bytes=photo_bytes,
                )
            except UploadPhotographerAccessDeniedError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
            except CsrfValidationError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error
            except PhotoUploadRateLimitError as error:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS) from error
            except InvalidPhotoUploadError as error:
                raise HTTPException(status_code=422, detail={"code": "invalid_target", "message": "Выбранный СПА недоступен для загрузки. Обновите страницу и выберите СПА снова."}) from error
            except InvalidJpegCandidateError as error:
                status_code = (
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                    if error.code == "compressed_bytes_exceeded"
                    else status.HTTP_422_UNPROCESSABLE_ENTITY
                )
                messages = {
                    "compressed_bytes_exceeded": f"Размер файла превышает лимит {settings.photo_upload_max_compressed_bytes / 1048576:g} МиБ.",
                    "decoded_side_exceeded": f"Сторона фотографии превышает лимит {settings.photo_upload_max_decoded_side_length} пикселей.",
                    "decoded_pixels_exceeded": f"Разрешение фотографии превышает лимит {settings.photo_upload_max_decoded_pixels / 1000000:g} мегапикселей.",
                    "unsupported_media_type": "Файл должен быть в формате JPEG.",
                    "decode_failed": "Не удалось прочитать JPEG. Файл повреждён или имеет неподдерживаемое кодирование.",
                    "invalid_exif_orientation": "В JPEG некорректно указана ориентация EXIF. Пересохраните фотографию в редакторе.",
                }
                raise HTTPException(status_code=status_code, detail={
                    "code": error.code if error.code in messages else "invalid_jpeg",
                    "message": messages.get(error.code, "Не удалось проверить JPEG."),
                }) from error
            except Exception as error:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from error
            if result.admission.outcome == "duplicate":
                return {
                    "schema_version": 1,
                    "outcome": "duplicate",
                    "warnings": result.warnings,
                }
            photo = result.admission.photo
            assert photo is not None
            response.status_code = status.HTTP_201_CREATED
            return {
                "schema_version": 1,
                "outcome": "accepted",
                "photo": {
                    "photo_id": str(photo.id),
                    "spa_id": str(photo.spa_id),
                    "visit_date": photo.visit_date.isoformat(),
                    "accepted_at": photo.accepted_at.isoformat().replace("+00:00", "Z"),
                    "captured_at": photo.captured_at.isoformat().replace("+00:00", "Z"),
                    "processing_status": "pending",
                },
                "warnings": result.warnings,
            }


def _database_session(session_factory: Callable[[], Session]) -> Session:
    return session_factory()


async def _photo_upload_form(request: Request) -> tuple[UUID, date, bytes]:
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    try:
        form = await request.form()
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY) from error
    expected_names = {"spa_id", "visit_date", "photo"}
    if {name for name, _ in form.multi_items()} != expected_names:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    values = {name: form.getlist(name) for name in expected_names}
    if any(len(value) != 1 for value in values.values()):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    raw_spa_id, raw_visit_date, raw_photo = (
        values["spa_id"][0],
        values["visit_date"][0],
        values["photo"][0],
    )
    if (
        not isinstance(raw_spa_id, str)
        or not isinstance(raw_visit_date, str)
        or not isinstance(raw_photo, UploadFile)
        or raw_photo.content_type != "image/jpeg"
    ):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    try:
        spa_id = UUID(raw_spa_id)
        visit_date = date.fromisoformat(raw_visit_date)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY) from error
    try:
        return spa_id, visit_date, await raw_photo.read()
    finally:
        await raw_photo.close()


def _photo_upload_limiter(app: FastAPI, settings: Settings) -> PhotoUploadRateLimiter:
    limiter = getattr(app.state, "photo_upload_limiter", None)
    if limiter is None:
        limiter = PhotoUploadRateLimiter(
            limit=settings.photo_upload_rate_limit,
            window_seconds=settings.photo_upload_rate_window_seconds,
        )
        app.state.photo_upload_limiter = limiter
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


def _photo_upload_page_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Photo upload</title>
</head>
<body>
  <main>
    <h1>Photo upload</h1>
    <div class="fm-upload-layout" id="upload-perspective">
    <form id="photo-upload-form">
      <label for="spa-id">СПА</label>
      <select id="spa-id" name="spa_id" required>
        <option value="">Выберите площадку</option>
      </select>
      <label for="visit-date">Дата съёмки</label>
      __VISIT_DATE_PICKER__
      <label for="photos">Фотографии в формате JPEG</label>
      <input id="photos" name="photos" type="file" accept="image/jpeg" multiple required>
      <button type="submit">Загрузить фотографии <span aria-hidden="true">↗</span></button>
    </form>
    <p class="fm-upload-state" id="upload-transfer-state" role="status">Готово к загрузке</p>
    </div>
    <p id="form-message" role="alert"></p>
    <section aria-label="Upload results">
      <h2>Результаты загрузки</h2>
      <p class="fm-upload-totals">Результаты: <span id="upload-settled" data-rolling-count>0</span> <span id="upload-selected-total"></span></p>
      <ol id="upload-results"></ol>
    </section>
  </main>
  <script>
    const form = document.querySelector("#photo-upload-form");
    const spaSelect = document.querySelector("#spa-id");
    const visitDateInput = document.querySelector("#visit-date");
    function uploadVisitDate() {
      return StaffDateTime.dateValue(visitDateInput) || null;
    }
    visitDateInput.addEventListener("input", () => visitDateInput.setCustomValidity(""));
    const filesInput = document.querySelector("#photos");
    const results = document.querySelector("#upload-results");
    const formMessage = document.querySelector("#form-message");
    const terminalProcessingStatuses = new Set(["ready", "no_faces", "failed"]);

    function csrfToken() {
      const prefix = "fm_staff_csrf=";
      const cookie = document.cookie.split("; ").find((value) => value.startsWith(prefix));
      return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
    }

    function appendResultRow(file, visitDate) {
      const row = document.createElement("li");
      const name = document.createElement("span");
      const date = document.createElement("span");
      const outcome = document.createElement("strong");
      const detail = document.createElement("span");
      name.textContent = file.name;
      date.textContent = ` — ${visitDate.split("-").reverse().join(".")} — `;
      outcome.textContent = "uploading";
      outcome.setAttribute("aria-live", "polite");
      row.append(name, date, outcome, detail);
      results.append(row);
      return { outcome, detail };
    }

    function setResult(row, outcome, detail = "") {
      row.outcome.textContent = outcome;
      row.detail.textContent = detail ? ` — ${detail}` : "";
    }

    function renderProcessingStatus(payload, row) {
      if (payload.processing_status === "ready") {
        setResult(
          row,
          payload.searchable ? "searchable" : "ready",
          payload.searchable ? "" : "not searchable",
        );
      } else if (payload.processing_status === "failed") {
        setResult(row, "failed", payload.failure_reason || "");
      } else if (payload.processing_status === "no_faces") {
        setResult(row, "no_faces");
      } else {
        setResult(row, payload.processing_status);
      }
    }

    async function pollProcessingStatus(photoId, row) {
      while (true) {
        try {
          const response = await fetch(`/api/inventory/photos/${photoId}/processing`, {
            credentials: "same-origin",
          });
          if (!response.ok) {
            setResult(row, "status unavailable");
            return;
          }
          const payload = await response.json();
          renderProcessingStatus(payload, row);
          if (terminalProcessingStatuses.has(payload.processing_status)) {
            return;
          }
        } catch (_) {
          setResult(row, "status unavailable");
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    }

    async function uploadFile(file, spaId, visitDate, row) {
      const body = new FormData();
      body.append("spa_id", spaId);
      body.append("visit_date", visitDate);
      body.append("photo", file, file.name);
      try {
        const response = await fetch("/api/inventory/photos", {
          method: "POST",
          body,
          credentials: "same-origin",
          headers: { "X-CSRF-Token": csrfToken() },
        });
        if (response.status === 201) {
          const payload = await response.json();
          const warning = payload.warnings.includes("exif_visit_date_mismatch")
            ? "EXIF date differs; selected date retained"
            : "";
          setResult(row, "pending", warning);
          void pollProcessingStatus(payload.photo.photo_id, row);
        } else if (response.status === 200) {
          setResult(row, "duplicate");
        } else if (response.status === 413 || response.status === 422) {
          let reason = response.status === 413
            ? "Размер файла или запроса превышает допустимый лимит загрузки."
            : "Проверьте формат JPEG, выбранный СПА и дату съёмки.";
          try {
            const payload = await response.json();
            if (typeof payload.detail?.message === "string") reason = payload.detail.message;
          } catch (_) { /* The proxy may return an empty or non-JSON rejection. */ }
          setResult(row, "Отклонено", reason);
        } else {
          setResult(row, "upload unavailable");
        }
      } catch (_) {
        setResult(row, "upload unavailable");
      }
    }

    async function loadTargets() {
      const response = await fetch("/api/inventory/ingest-targets", {
        credentials: "same-origin",
      });
      if (!response.ok) {
        formMessage.textContent = "Unable to load СПА choices.";
        return;
      }
      const payload = await response.json();
      for (const spa of payload.spas) {
        const option = document.createElement("option");
        option.value = spa.spa_id;
        option.textContent = spa.name;
        spaSelect.append(option);
      }
    }

    let activeUploads = 0;
    let selectedTotal = 0;
    let settledTotal = 0;
    const perspective = document.querySelector("#upload-perspective");
    const transferState = document.querySelector("#upload-transfer-state");
    function updateTransferState() {
      perspective.classList.toggle("is-uploading", activeUploads > 0);
      form.setAttribute("aria-busy", String(activeUploads > 0));
      transferState.textContent = activeUploads > 0
        ? "Загружаем фотографии — можно добавить ещё файлы"
        : "Передача завершена. Результат каждого файла — ниже";
      document.querySelector("#upload-settled").textContent = String(settledTotal);
      document.querySelector("#upload-selected-total").textContent = `из ${selectedTotal}`;
    }
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const spaId = spaSelect.value;
      const visitDate = uploadVisitDate();
      if (!visitDate) {
        visitDateInput.setCustomValidity("Выберите существующую дату съёмки.");
        visitDateInput.reportValidity();
        return;
      }
      const files = Array.from(filesInput.files);
      if (!spaId || !visitDate || files.length === 0) {
        formMessage.textContent = "Select one СПА, one visit date and at least one file.";
        return;
      }
      formMessage.textContent = "";
      const uploads = files.map((file) => ({
        file,
        row: appendResultRow(file, visitDate),
      }));
      filesInput.value = "";
      selectedTotal += uploads.length;
      activeUploads += uploads.length;
      updateTransferState();
      await Promise.all(uploads.map(async ({ file, row }) => {
        try { await uploadFile(file, spaId, visitDate, row); }
        finally { activeUploads -= 1; settledTotal += 1; updateTransferState(); }
      }));
    });

    loadTargets();
  </script>
</body>
</html>""".replace("__VISIT_DATE_PICKER__", date_picker("visit-date", staff_today(), name="visit_date"))


def _spa_options(spas: Sequence[tuple[UUID, str]]) -> str:
    if not spas:
        return '<option value="">Нет доступных площадок</option>'
    return "".join(f'<option value="{spa_id}">{escape(name)}</option>' for spa_id, name in spas)


def _processing_health_page_html(spas: Sequence[tuple[UUID, str]] = ()) -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Processing health</title>
</head>
<body>
  <main>
    <h1>Processing health</h1>
    <form id="processing-health-query">
      <label for="health-spa-id">Площадка</label>
      <select id="health-spa-id" name="spa_id" required>__SPA_OPTIONS__</select>
      __DATETIME_RANGE__
      <button type="submit">Обновить состояние</button>
    </form>
    <p id="health-message" role="alert"></p>

    <section aria-label="Processing queue">
      <h2>Очередь фотографий</h2>
      <dl>
        <dt>В очереди</dt><dd id="queue-pending">—</dd>
        <dt>Обрабатываются</dt><dd id="queue-processing">—</dd>
        <dt>Готовы</dt><dd id="queue-ready">—</dd>
        <dt>Без лиц</dt><dd id="queue-no-faces">—</dd>
        <dt>Ошибки</dt><dd id="queue-failed">—</dd>
        <dt>Самая ранняя заявка в очереди</dt><dd id="queue-oldest-pending-accepted-at">—</dd>
        <dt>Текущая операция</dt><dd id="queue-current-operation">—</dd>
        <dt>Начало операции</dt><dd id="queue-operation-started-at">—</dd>
        <dt>Обработчик запущен</dt><dd id="queue-worker-started-at">—</dd>
        <dt>Последнее восстановление</dt><dd id="queue-last-recovery-at">—</dd>
        <dt>Восстановлено задач</dt><dd id="queue-last-recovered-count">—</dd>
      </dl>
    </section>

    <section aria-label="Ingest to searchable SLO">
      <h2>Скорость появления в поиске</h2>
      <p id="slo-message"></p>
      <dl>
        <dt>Начало периода</dt><dd id="slo-accepted-from">—</dd>
        <dt>Конец периода</dt><dd id="slo-accepted-before">—</dd>
        <dt>Всего фотографий</dt><dd id="slo-population">—</dd>
        <dt>Готовы менее чем за 15 минут</dt><dd id="slo-success-under-15-minutes">—</dd>
        <dt>Превышено время</dt><dd id="slo-breach">—</dd>
        <dt>Ещё в работе</dt><dd id="slo-open">—</dd>
        <dt>Доля успешных</dt><dd id="slo-success-ratio">—</dd>
        <dt>Достигнуты 95%</dt><dd id="slo-verdict">—</dd>
      </dl>
    </section>

    <section aria-label="PostgreSQL capacity">
      <h2>Хранилище данных · PostgreSQL</h2>
      <dl>
        <dt>Состояние</dt><dd id="postgresql-status">—</dd>
        <dt>Свободно, байт</dt><dd id="postgresql-available-bytes">—</dd>
        <dt>Минимальный остаток, байт</dt><dd id="postgresql-low-threshold-bytes">—</dd>
        <dt>Проверено</dt><dd id="postgresql-observed-at">—</dd>
        <dt>Ошибка</dt><dd id="postgresql-error">—</dd>
      </dl>
    </section>

    <section aria-label="MinIO capacity">
      <h2>Хранилище фотографий · MinIO</h2>
      <dl>
        <dt>Состояние</dt><dd id="minio-status">—</dd>
        <dt>Свободно, байт</dt><dd id="minio-available-bytes">—</dd>
        <dt>Минимальный остаток, байт</dt><dd id="minio-low-threshold-bytes">—</dd>
        <dt>Проверено</dt><dd id="minio-observed-at">—</dd>
        <dt>Ошибка</dt><dd id="minio-error">—</dd>
      </dl>
    </section>
  </main>
  <script>
    const healthForm = document.querySelector("#processing-health-query");
    const healthMessage = document.querySelector("#health-message");
    const sloMessage = document.querySelector("#slo-message");
    const healthFieldNames = ["spa_id", "accepted_from", "accepted_before"];
    StaffDateTime.init(healthForm);

    function renderValue(id, value, missing = "нет данных") {
      document.querySelector(`#${id}`).textContent = value === null ? missing : String(value);
    }

    function queryFromForm() {
      const query = new URLSearchParams();
      const values = new FormData(healthForm);
      for (const name of healthFieldNames) {
        const value = values.get(name);
        if (typeof value === "string" && value) {
          query.set(name, value);
        }
      }
      return query.toString();
    }

    function renderQueue(queue) {
      renderValue("queue-pending", queue.pending);
      renderValue("queue-processing", queue.processing);
      renderValue("queue-ready", queue.ready);
      renderValue("queue-no-faces", queue.no_faces);
      renderValue("queue-failed", queue.failed);
      renderValue("queue-oldest-pending-accepted-at", queue.oldest_pending_accepted_at);
      renderValue("queue-current-operation", queue.current_operation);
      renderValue("queue-operation-started-at", queue.operation_started_at);
      renderValue("queue-worker-started-at", queue.worker_started_at);
      renderValue("queue-last-recovery-at", queue.last_recovery_at);
      renderValue("queue-last-recovered-count", queue.last_recovered_count);
    }

    function renderSlo(slo) {
      if (slo === null) {
        sloMessage.textContent = "Выберите период, чтобы оценить время обработки.";
        for (const id of [
          "slo-accepted-from", "slo-accepted-before", "slo-population",
          "slo-success-under-15-minutes", "slo-breach", "slo-open",
          "slo-success-ratio", "slo-verdict",
        ]) {
          renderValue(id, null, "не выбрано");
        }
        return;
      }
      sloMessage.textContent = "Показатели за выбранный период.";
      renderValue("slo-accepted-from", slo.accepted_from);
      renderValue("slo-accepted-before", slo.accepted_before);
      renderValue("slo-population", slo.population);
      renderValue("slo-success-under-15-minutes", slo.success_under_15_minutes);
      renderValue("slo-breach", slo.breach);
      renderValue("slo-open", slo.open);
      renderValue("slo-success-ratio", slo.success_ratio, "no ratio");
      renderValue("slo-verdict", slo.meets_95_percent, "no verdict");
    }

    function renderStorage(name, storage) {
      renderValue(`${name}-status`, storage.status);
      renderValue(`${name}-available-bytes`, storage.available_bytes);
      renderValue(`${name}-low-threshold-bytes`, storage.low_threshold_bytes);
      renderValue(`${name}-observed-at`, storage.observed_at);
      renderValue(`${name}-error`, storage.error);
    }

    function renderHealth(payload) {
      renderQueue(payload.queue);
      renderSlo(payload.ingest_to_searchable);
      renderStorage("postgresql", payload.storage.postgresql);
      renderStorage("minio", payload.storage.minio);
      healthMessage.textContent = "";
    }

    async function loadHealth() {
      if (!StaffDateTime.sync(healthForm)) return;
      const query = queryFromForm();
      if (!query.includes("spa_id=")) {
        healthMessage.textContent = "Выберите площадку для просмотра состояния.";
        return;
      }
      try {
        const response = await fetch(`/api/inventory/processing-health?${query}`, {
          credentials: "same-origin",
        });
        if (!response.ok) {
          healthMessage.textContent = "Не удалось получить состояние обработки.";
          return;
        }
        const payload = await response.json();
        if (query !== queryFromForm()) return;
        renderHealth(payload);
      } catch (_) {
        healthMessage.textContent = "Не удалось получить состояние обработки.";
      }
    }

    function loadInitialQuery() {
      const initialQuery = new URLSearchParams(window.location.search);
      for (const name of healthFieldNames) {
        const value = initialQuery.get(name);
        if (value !== null && (name !== "spa_id" || Array.from(healthForm.elements.namedItem(name).options).some(option => option.value === value))) {
          if (name === "spa_id") healthForm.elements.namedItem(name).value = value;
          else StaffDateTime.setValue(healthForm, name, value);
        }
      }
      void loadHealth();
    }

    healthForm.addEventListener("submit", (event) => {
      event.preventDefault();
      void loadHealth();
    });

    document.querySelector("#health-spa-id").addEventListener("change", loadHealth);
    loadInitialQuery();
    setInterval(loadHealth, 5000);
  </script>
</body>
</html>""".replace("__SPA_OPTIONS__", _spa_options(spas)).replace("__DATETIME_RANGE__", datetime_range_fields(from_name="accepted_from", to_name="accepted_before", from_label="Поступили после", to_label="Поступили до"))


async def _validate_purge_payload(request: Request, *, confirmation: bool) -> None:
    try:
        payload = await request.json()
        expected = {"schema_version", "confirmed"} if confirmation else {"schema_version"}
        if (
            not isinstance(payload, dict) or set(payload) != expected
            or type(payload["schema_version"]) is not int
            or payload["schema_version"] != 1
            or (confirmation and payload["confirmed"] is not True)
        ):
            raise ValueError
    except (ValueError, TypeError) as error:
        raise HTTPException(422, headers=_NO_STORE_HEADERS) from error


def _photo_inventory_page_html(spas: Sequence[tuple[UUID, str]] = ()) -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Photo inventory</title>
</head>
<body>
  <main>
    <h1>Photo inventory</h1>
    <form id="recent-statistics-query">
      <label for="recent-statistics-spa-id">Площадка</label>
      <select id="recent-statistics-spa-id" name="spa_id" required>__SPA_OPTIONS__</select>
      <button type="submit">Обновить статистику</button>
    </form>
    <p id="recent-statistics-message" role="alert"></p>
    <section aria-label="Recent photo statistics">
      <h2>Последние поступления</h2>
      <ol id="recent-statistics-windows"></ol>
    </section>
    <section id="inventory-purge" aria-label="Управление скрытыми фото" hidden>
      <h2>Скрытые фотографии проекта</h2>
      <div id="inventory-purge-controls">
        <button id="inventory-restore-all" type="button">Восстановить все скрытые фото</button>
        <button id="inventory-confirm-purge" type="button">Удалить все скрытые фото навсегда</button>
      </div>
      <p id="inventory-purge-progress" role="status" aria-live="polite"></p>
      <p id="inventory-purge-message" role="alert"></p>
    </section>
  </main>
  <script>
    const recentStatisticsForm = document.querySelector("#recent-statistics-query");
    const recentStatisticsSpaId = document.querySelector("#recent-statistics-spa-id");
    const recentStatisticsMessage = document.querySelector("#recent-statistics-message");
    const recentStatisticsWindows = document.querySelector("#recent-statistics-windows");

    function renderWindow(window) {
      const item = document.createElement("li");
      item.textContent = `${window.minutes} minutes: new ${window.new}, unprocessed ${window.unprocessed}, processed ${window.processed}, failed ${window.failed}`;
      recentStatisticsWindows.append(item);
    }

    async function loadRecentStatistics() {
      const spaId = recentStatisticsSpaId.value.trim();
      if (!spaId) return;
      try {
        const response = await fetch(`/api/inventory/recent-statistics?spa_id=${encodeURIComponent(spaId)}`, {
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error("Statistics request failed");
        const payload = await response.json();
        if (spaId !== recentStatisticsSpaId.value) return;
        recentStatisticsWindows.replaceChildren();
        payload.windows.forEach(renderWindow);
        recentStatisticsMessage.textContent = `Observed at ${payload.observed_at}`;
      } catch (error) {
        recentStatisticsMessage.textContent = error.message;
      }
    }

    recentStatisticsForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      await loadRecentStatistics();
    });
    const initialSpa = new URLSearchParams(window.location.search).get("spa_id");
    if (Array.from(recentStatisticsSpaId.options).some(option => option.value === initialSpa)) {
      recentStatisticsSpaId.value = initialSpa;
    }
    recentStatisticsSpaId.addEventListener("change", loadRecentStatistics);
    void loadRecentStatistics();
    setInterval(loadRecentStatistics, 5000);

    const purgeSection = document.querySelector("#inventory-purge");
    const purgeControls = document.querySelector("#inventory-purge-controls");
    const purgeProgress = document.querySelector("#inventory-purge-progress");
    const purgeMessage = document.querySelector("#inventory-purge-message");
    const restoreAllButton = document.querySelector("#inventory-restore-all");
    const confirmPurgeButton = document.querySelector("#inventory-confirm-purge");

    function renderPurge(payload) {
      purgeSection.hidden = false;
      const run = payload.run;
      purgeControls.hidden = Boolean(run && run.state !== "completed");
      purgeProgress.textContent = !run ? "" : run.waiting_for
        ? `Начну удаление, как только закончится процесс ${run.waiting_for}`
        : run.state === "confirmed_waiting" ? `Ожидание удаления: ${run.completed}/${run.total}`
        : run.state === "completed" ? `Удаление завершено: ${run.completed}/${run.total}`
        : `Удалено: ${run.completed}/${run.total}`;
    }

    async function loadPurge() {
      try {
        const response = await fetch("/api/inventory/hard-purge", { credentials: "same-origin" });
        if (response.status === 401 || response.status === 403) {
          purgeSection.hidden = true;
          return;
        }
        if (!response.ok) throw new Error("Не удалось получить состояние удаления");
        renderPurge(await response.json());
      } catch (error) {
        purgeMessage.textContent = error.message;
      }
    }

    async function mutateInventory(path, payload) {
      restoreAllButton.disabled = confirmPurgeButton.disabled = true;
      purgeMessage.textContent = "";
      const csrf = document.cookie.split("; ").find(value => value.startsWith("fm_staff_csrf="));
      try {
        const response = await fetch(path, {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf ? decodeURIComponent(csrf.slice(14)) : "" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error(response.status === 409
          ? "Удаление уже выполняется" : "Не удалось выполнить действие");
        const result = await response.json();
        if ("run" in result) renderPurge(result);
        else purgeMessage.textContent = `Восстановлено: ${result.restored_count}. В списке удаления: ${result.excluded_snapshot_count}.`;
      } catch (error) {
        purgeMessage.textContent = error.message;
      } finally {
        await loadPurge();
        restoreAllButton.disabled = confirmPurgeButton.disabled = false;
      }
    }

    restoreAllButton.addEventListener("click", () => mutateInventory("/api/inventory/restore-all", { schema_version: 1 }));
    confirmPurgeButton.addEventListener("click", () => {
      if (window.confirm("Удалить все скрытые фотографии проекта навсегда? Восстановить их будет невозможно.")) {
        return mutateInventory("/api/inventory/hard-purge", { schema_version: 1, confirmed: true });
      }
    });
    loadPurge();
    setInterval(loadPurge, 5000);
  </script>
</body>
</html>""".replace("__SPA_OPTIONS__", _spa_options(spas))

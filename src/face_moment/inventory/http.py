"""Thin HTTP transport for inventory-owned staff reads."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from datetime import date
from ipaddress import ip_address
from uuid import UUID

from fastapi import Cookie, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from starlette.datastructures import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
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
from face_moment.inventory.validation import InvalidJpegCandidateError
from face_moment.platform.auth.sessions import CsrfValidationError, InvalidSessionError


def register_ingest_target_routes(app: FastAPI) -> None:
    @app.get("/staff/photo-upload", response_class=HTMLResponse)
    def photo_upload_page(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        with _database_session(Settings.from_env()) as database_session:
            try:
                read_ingest_target_context(
                    database_session,
                    session_token=fm_staff_session,
                )
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
            except PhotographerAccessDeniedError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error
        return HTMLResponse(_photo_upload_page_html())

    @app.get("/api/inventory/ingest-targets", response_model=None)
    def ingest_targets(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> IngestTargetContext:
        with _database_session(Settings.from_env()) as database_session:
            try:
                return read_ingest_target_context(
                    database_session,
                    session_token=fm_staff_session,
                )
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
            except PhotographerAccessDeniedError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error

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
        with _database_session(settings) as database_session:
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
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY) from error
            except InvalidJpegCandidateError as error:
                status_code = (
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                    if error.code == "compressed_bytes_exceeded"
                    else status.HTTP_422_UNPROCESSABLE_ENTITY
                )
                raise HTTPException(status_code=status_code) from error
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


@contextmanager
def _database_session(settings: Settings) -> Iterator[Session]:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as database_session:
            yield database_session
    finally:
        engine.dispose()


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
    <form id="photo-upload-form">
      <label for="spa-id">СПА</label>
      <select id="spa-id" name="spa_id" required>
        <option value="">Select СПА</option>
      </select>
      <label for="visit-date">Visit date</label>
      <input id="visit-date" name="visit_date" type="date" required>
      <label for="photos">JPEG files</label>
      <input id="photos" name="photos" type="file" accept="image/jpeg" multiple required>
      <button type="submit">Upload selected files</button>
    </form>
    <p id="form-message" role="alert"></p>
    <section aria-label="Upload results">
      <h2>Results</h2>
      <ol id="upload-results"></ol>
    </section>
  </main>
  <script>
    const form = document.querySelector("#photo-upload-form");
    const spaSelect = document.querySelector("#spa-id");
    const visitDateInput = document.querySelector("#visit-date");
    const filesInput = document.querySelector("#photos");
    const results = document.querySelector("#upload-results");
    const formMessage = document.querySelector("#form-message");

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
      date.textContent = ` — ${visitDate} — `;
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
          setResult(row, "accepted", warning);
        } else if (response.status === 200) {
          setResult(row, "duplicate");
        } else if (response.status === 413 || response.status === 422) {
          setResult(row, "rejected");
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

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const spaId = spaSelect.value;
      const visitDate = visitDateInput.value;
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
      await Promise.all(uploads.map(({ file, row }) => uploadFile(file, spaId, visitDate, row)));
    });

    loadTargets();
  </script>
</body>
</html>"""

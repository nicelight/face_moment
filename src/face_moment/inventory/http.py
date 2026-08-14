"""Thin HTTP transport for inventory-owned staff reads."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from datetime import date, datetime
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
from face_moment.inventory.photo_processing_status import (
    PhotoProcessingStatusAccessDeniedError,
    PhotoProcessingStatusNotFoundError,
    read_photo_processing_status,
)
from face_moment.inventory.processing_health import (
    InvalidProcessingHealthIntervalError,
    ProcessingHealthAccessDeniedError,
    ProcessingHealthNotFoundError,
    authorize_processing_health_access,
    read_processing_health,
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

    @app.get("/staff/processing-health", response_class=HTMLResponse)
    def processing_health_page(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        with _database_session(Settings.from_env()) as database_session:
            try:
                authorize_processing_health_access(
                    database_session,
                    session_token=fm_staff_session,
                )
            except ProcessingHealthAccessDeniedError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
        return HTMLResponse(_processing_health_page_html())

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

    @app.get("/api/inventory/photos/{photo_id}/processing", response_model=None)
    def photo_processing_status(
        photo_id: UUID,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> dict[str, object]:
        with _database_session(Settings.from_env()) as database_session:
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

    @app.get("/api/inventory/processing-health", response_model=None)
    def processing_health(
        spa_id: UUID,
        accepted_from: datetime | None = None,
        accepted_before: datetime | None = None,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> dict[str, object]:
        settings = Settings.from_env()
        with _database_session(settings) as database_session:
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


def _processing_health_page_html() -> str:
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
      <label for="health-spa-id">SPA ID</label>
      <input id="health-spa-id" name="spa_id" required>
      <label for="accepted-from">Accepted from (optional ISO timestamp)</label>
      <input id="accepted-from" name="accepted_from">
      <label for="accepted-before">Accepted before (optional ISO timestamp)</label>
      <input id="accepted-before" name="accepted_before">
      <button type="submit">Refresh health</button>
    </form>
    <p id="health-message" role="alert"></p>

    <section aria-label="Processing queue">
      <h2>Processing queue</h2>
      <dl>
        <dt>Pending</dt><dd id="queue-pending"></dd>
        <dt>Processing</dt><dd id="queue-processing"></dd>
        <dt>Ready</dt><dd id="queue-ready"></dd>
        <dt>No faces</dt><dd id="queue-no-faces"></dd>
        <dt>Failed</dt><dd id="queue-failed"></dd>
        <dt>Oldest pending accepted at</dt><dd id="queue-oldest-pending-accepted-at"></dd>
        <dt>Current operation</dt><dd id="queue-current-operation"></dd>
        <dt>Operation started at</dt><dd id="queue-operation-started-at"></dd>
        <dt>Worker started at</dt><dd id="queue-worker-started-at"></dd>
        <dt>Last recovery at</dt><dd id="queue-last-recovery-at"></dd>
        <dt>Last recovered count</dt><dd id="queue-last-recovered-count"></dd>
      </dl>
    </section>

    <section aria-label="Ingest to searchable SLO">
      <h2>Ingest to searchable SLO</h2>
      <p id="slo-message"></p>
      <dl>
        <dt>Accepted from</dt><dd id="slo-accepted-from"></dd>
        <dt>Accepted before</dt><dd id="slo-accepted-before"></dd>
        <dt>Population</dt><dd id="slo-population"></dd>
        <dt>Success under 15 minutes</dt><dd id="slo-success-under-15-minutes"></dd>
        <dt>Breach</dt><dd id="slo-breach"></dd>
        <dt>Open</dt><dd id="slo-open"></dd>
        <dt>Success ratio</dt><dd id="slo-success-ratio"></dd>
        <dt>95 percent verdict</dt><dd id="slo-verdict"></dd>
      </dl>
    </section>

    <section aria-label="PostgreSQL capacity">
      <h2>PostgreSQL capacity</h2>
      <dl>
        <dt>Status</dt><dd id="postgresql-status"></dd>
        <dt>Available bytes</dt><dd id="postgresql-available-bytes"></dd>
        <dt>Low threshold bytes</dt><dd id="postgresql-low-threshold-bytes"></dd>
        <dt>Observed at</dt><dd id="postgresql-observed-at"></dd>
        <dt>Error</dt><dd id="postgresql-error"></dd>
      </dl>
    </section>

    <section aria-label="MinIO capacity">
      <h2>MinIO capacity</h2>
      <dl>
        <dt>Status</dt><dd id="minio-status"></dd>
        <dt>Available bytes</dt><dd id="minio-available-bytes"></dd>
        <dt>Low threshold bytes</dt><dd id="minio-low-threshold-bytes"></dd>
        <dt>Observed at</dt><dd id="minio-observed-at"></dd>
        <dt>Error</dt><dd id="minio-error"></dd>
      </dl>
    </section>
  </main>
  <script>
    const healthForm = document.querySelector("#processing-health-query");
    const healthMessage = document.querySelector("#health-message");
    const sloMessage = document.querySelector("#slo-message");
    const healthFieldNames = ["spa_id", "accepted_from", "accepted_before"];

    function renderValue(id, value, missing = "not available") {
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
        sloMessage.textContent = "No controlled SLO interval selected.";
        for (const id of [
          "slo-accepted-from", "slo-accepted-before", "slo-population",
          "slo-success-under-15-minutes", "slo-breach", "slo-open",
          "slo-success-ratio", "slo-verdict",
        ]) {
          renderValue(id, null, "not selected");
        }
        return;
      }
      sloMessage.textContent = "Controlled SLO interval.";
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
      const query = queryFromForm();
      if (!query.includes("spa_id=")) {
        healthMessage.textContent = "Enter a SPA ID.";
        return;
      }
      try {
        const response = await fetch(`/api/inventory/processing-health?${query}`, {
          credentials: "same-origin",
        });
        if (!response.ok) {
          healthMessage.textContent = "Health data unavailable.";
          return;
        }
        renderHealth(await response.json());
      } catch (_) {
        healthMessage.textContent = "Health data unavailable.";
      }
    }

    function loadInitialQuery() {
      const initialQuery = new URLSearchParams(window.location.search);
      for (const name of healthFieldNames) {
        const value = initialQuery.get(name);
        if (value !== null) {
          healthForm.elements.namedItem(name).value = value;
        }
      }
      void loadHealth();
    }

    healthForm.addEventListener("submit", (event) => {
      event.preventDefault();
      void loadHealth();
    });

    loadInitialQuery();
    setInterval(loadHealth, 5000);
  </script>
</body>
</html>"""

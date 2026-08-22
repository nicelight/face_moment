from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date, datetime
from html import escape
import uuid

from fastapi import Cookie, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.sessions import (
    CsrfValidationError,
    InvalidSessionError,
)
from face_moment.serving_control.active_search_date import (
    ActiveSearchDateAccessDeniedError,
    ActiveSearchDateRecord,
    ActiveSearchDateSpa,
    ActiveSearchDateSpaNotFoundError,
    list_active_search_date_spas,
    read_active_search_date,
    update_active_search_date,
)
from face_moment.serving_control.display_client_admin import (
    DisplayClientAdminAccessDeniedError,
    DisplayClientAdminRecord,
    read_display_client_admin,
)


class ActiveSearchDateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visit_date: date


class ActiveSearchDateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    spa_id: uuid.UUID
    active_visit_date: date | None
    settings_revision: int
    updated_at: datetime | None


def register_display_client_admin_routes(app: FastAPI) -> None:
    @app.get("/staff/display-clients", response_class=HTMLResponse)
    def display_client_admin_page(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        with _database_session(Settings.from_env()) as database_session:
            try:
                clients = read_display_client_admin(
                    database_session,
                    session_token=fm_staff_session,
                )
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
            except DisplayClientAdminAccessDeniedError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error

        response = HTMLResponse(_display_client_page_html(clients))
        response.headers["Cache-Control"] = "no-store"
        return response


def register_active_search_date_routes(app: FastAPI) -> None:
    @app.get("/staff/search-settings", response_class=HTMLResponse)
    def active_search_date_page(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        with _database_session(Settings.from_env()) as database_session:
            try:
                spas = list_active_search_date_spas(
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

        response = HTMLResponse(_active_search_date_page_html(spas))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get(
        "/api/serving/spas/{spa_id}/active-visit-date",
        response_model=ActiveSearchDateResponse,
    )
    def read_active_search_date_route(
        spa_id: uuid.UUID,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> ActiveSearchDateResponse:
        with _database_session(Settings.from_env()) as database_session:
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
        with _database_session(Settings.from_env()) as database_session:
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


@contextmanager
def _database_session(settings: Settings) -> Iterator[Session]:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as database_session:
            yield database_session
    finally:
        engine.dispose()


def _display_client_page_html(clients: Sequence[DisplayClientAdminRecord]) -> str:
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
</head>
<body>
  <main>
    <h1>Display client settings</h1>
    <table>
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
    </table>
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


def _active_search_date_page_html(spas: Sequence[ActiveSearchDateSpa]) -> str:
    options = "".join(
        f'<option value="{escape(str(spa.spa_id))}">{escape(spa.name)}</option>'
        for spa in spas
    )
    empty_state = "No active SPA is configured." if not spas else ""
    disabled = " disabled" if not spas else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Active search date</title>
</head>
<body>
  <main>
    <h1>Active search date</h1>
    <p>{escape(empty_state)}</p>
    <form id="active-search-date-form"{disabled}>
      <label>SPA
        <select id="spa-id" name="spa_id">{options}</select>
      </label>
      <label>Visit date
        <input id="visit-date" name="visit_date" type="date" required>
      </label>
      <p>Settings revision: <output id="settings-revision">—</output></p>
      <button type="submit">Save active date</button>
      <output id="status" role="status" aria-live="polite"></output>
    </form>
  </main>
  <script>
    const form = document.querySelector("#active-search-date-form");
    const spaId = document.querySelector("#spa-id");
    const visitDate = document.querySelector("#visit-date");
    const revision = document.querySelector("#settings-revision");
    const statusOutput = document.querySelector("#status");
    const csrfToken = () => document.cookie.split("; ")
      .find((item) => item.startsWith("fm_staff_csrf="))?.slice("fm_staff_csrf=".length) ?? "";
    async function loadActiveDate() {{
      const response = await fetch(`/api/serving/spas/${{spaId.value}}/active-visit-date`, {{
        headers: {{"Accept": "application/json"}}
      }});
      if (!response.ok) throw new Error(`Unable to load active date (${{response.status}})`);
      const data = await response.json();
      visitDate.value = data.active_visit_date ?? "";
      revision.value = data.settings_revision;
    }}
    spaId?.addEventListener("change", () => loadActiveDate().catch((error) => {{ statusOutput.value = error.message; }}));
    form?.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const response = await fetch(`/api/serving/spas/${{spaId.value}}/active-visit-date`, {{
        method: "PUT",
        headers: {{"Content-Type": "application/json", "X-CSRF-Token": csrfToken()}},
        body: JSON.stringify({{visit_date: visitDate.value}})
      }});
      if (!response.ok) {{ statusOutput.value = `Unable to save active date (${{response.status}})`; return; }}
      const data = await response.json();
      revision.value = data.settings_revision;
      statusOutput.value = `Saved ${{data.active_visit_date}}`;
    }});
    if (spaId?.value) loadActiveDate().catch((error) => {{ statusOutput.value = error.message; }});
  </script>
</body>
</html>"""

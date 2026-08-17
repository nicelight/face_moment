from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from html import escape

from fastapi import Cookie, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.sessions import InvalidSessionError
from face_moment.serving_control.display_client_admin import (
    DisplayClientAdminAccessDeniedError,
    DisplayClientAdminRecord,
    read_display_client_admin,
)


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

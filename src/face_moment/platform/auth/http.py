from __future__ import annotations

from collections.abc import Callable
from ipaddress import ip_address

from fastapi import Cookie, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.sessions import (
    BrowserSession,
    CsrfValidationError,
    InvalidCredentialsError,
    InvalidSessionError,
    LoginRateLimitError,
    LoginRateLimiter,
    create_browser_session,
    get_current_principal,
    revoke_current_browser_session,
)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str


def register_staff_session_routes(
    app: FastAPI, *, session_factory: Callable[[], Session]
) -> None:
    @app.get("/staff/login", response_class=HTMLResponse)
    def staff_login_page() -> HTMLResponse:
        return HTMLResponse(_staff_login_page_html())

    @app.post("/api/staff/sessions", status_code=status.HTTP_204_NO_CONTENT)
    def login(request: Request, payload: LoginRequest) -> Response:
        settings = Settings.from_env()
        with _database_session(session_factory) as database_session:
            try:
                browser_session = create_browser_session(
                    database_session,
                    username=payload.username,
                    password=payload.password,
                    ip_address=_client_ip(request),
                    ttl_seconds=settings.staff_session_ttl_seconds,
                    limiter=_login_limiter(app, settings),
                )
            except LoginRateLimitError as error:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS) from error
            except InvalidCredentialsError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        _set_session_cookies(response, browser_session, settings)
        return response

    @app.get("/api/staff/session")
    def current_session(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> dict[str, str]:
        with _database_session(session_factory) as database_session:
            try:
                principal = get_current_principal(
                    database_session, session_token=fm_staff_session
                )
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
        return {
            "staff_user_id": str(principal.staff_user_id),
            "username": principal.username,
            "role": principal.role.value,
        }

    @app.delete("/api/staff/session", status_code=status.HTTP_204_NO_CONTENT)
    def logout(
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> Response:
        with _database_session(session_factory) as database_session:
            try:
                revoke_current_browser_session(
                    database_session,
                    session_token=fm_staff_session,
                    csrf_cookie_token=fm_staff_csrf,
                    csrf_header_token=x_csrf_token,
                )
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
            except CsrfValidationError as error:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(
            "fm_staff_session", path="/", secure=True, httponly=True, samesite="lax"
        )
        response.delete_cookie(
            "fm_staff_csrf", path="/", secure=True, httponly=False, samesite="lax"
        )
        return response


def _set_session_cookies(
    response: Response, browser_session: BrowserSession, settings: Settings
) -> None:
    response.set_cookie(
        "fm_staff_session",
        browser_session.session_token,
        max_age=settings.staff_session_ttl_seconds,
        expires=browser_session.expires_at,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        "fm_staff_csrf",
        browser_session.csrf_token,
        max_age=settings.staff_session_ttl_seconds,
        expires=browser_session.expires_at,
        path="/",
        secure=True,
        httponly=False,
        samesite="lax",
    )


def _database_session(session_factory: Callable[[], Session]) -> Session:
    return session_factory()


def _login_limiter(app: FastAPI, settings: Settings) -> LoginRateLimiter:
    limiter = getattr(app.state, "staff_login_limiter", None)
    if limiter is None:
        limiter = LoginRateLimiter(
            limit=settings.staff_login_rate_limit,
            window_seconds=settings.staff_login_rate_window_seconds,
        )
        app.state.staff_login_limiter = limiter
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


def _staff_login_page_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Staff login</title>
</head>
<body>
  <main>
    <h1>Staff login</h1>
    <form id="staff-login-form" method="post">
      <label for="staff-username">Username</label>
      <input id="staff-username" name="username" type="text" autocomplete="username" required>
      <label for="staff-password">Password</label>
      <input id="staff-password" name="password" type="password" autocomplete="current-password" required>
      <button id="staff-login-submit" type="submit">Sign in</button>
      <p id="staff-login-message" role="alert" aria-live="assertive"></p>
    </form>
  </main>
  <script>
    const form = document.querySelector("#staff-login-form");
    const usernameInput = document.querySelector("#staff-username");
    const passwordInput = document.querySelector("#staff-password");
    const submitButton = document.querySelector("#staff-login-submit");
    const message = document.querySelector("#staff-login-message");

    function setPending(pending) {
      usernameInput.disabled = pending;
      passwordInput.disabled = pending;
      submitButton.disabled = pending;
      form.setAttribute("aria-busy", pending ? "true" : "false");
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity() || submitButton.disabled) return;
      message.textContent = "";
      setPending(true);
      try {
        const response = await fetch("/api/staff/sessions", {
          method: "POST",
          credentials: "same-origin",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({username: usernameInput.value, password: passwordInput.value}),
        });
        if (response.status === 204) {
          window.location.assign("/staff/photo-inventory");
          return;
        }
        if (response.status === 401) {
          message.textContent = "Invalid username or password.";
        } else if (response.status === 429) {
          message.textContent = "Too many login attempts. Please try again later.";
        } else {
          message.textContent = "Login is temporarily unavailable. Please try again.";
        }
      } catch (_) {
        message.textContent = "Login is temporarily unavailable. Please try again.";
      } finally {
        setPending(false);
      }
    });
  </script>
</body>
</html>"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi import FastAPI

from face_moment.entrypoints.backend import create_app
from face_moment.inventory import http as inventory_http
from face_moment.platform.auth.sessions import InvalidSessionError


@pytest.fixture
def photo_inventory_page_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    @contextmanager
    def database_session(_: object) -> Iterator[object]:
        yield object()

    def current_principal(_: object, *, session_token: str | None) -> object:
        if session_token in {
            "operator-session",
            "developer-session",
            "photographer-session",
        }:
            return object()
        raise InvalidSessionError

    monkeypatch.setattr(inventory_http, "_database_session", database_session)
    monkeypatch.setattr(inventory_http, "get_current_principal", current_principal)
    return create_app()


def test_photo_inventory_statistics_page_requires_staff_and_polls_every_five_seconds(
    photo_inventory_page_app: FastAPI,
) -> None:
    assert _get_page(photo_inventory_page_app)[0] == 401
    for role in ("operator", "developer", "photographer"):
        status_code, page = _get_page(
            photo_inventory_page_app,
            cookie=f"fm_staff_session={role}-session",
        )
        assert status_code == 200
        assert "Photo inventory" in page
        assert 'id="recent-statistics-query"' in page
        assert 'id="recent-statistics-spa-id"' in page
        assert "/api/inventory/recent-statistics?spa_id=${encodeURIComponent(spaId)}" in page
        assert "setInterval(loadRecentStatistics, 5000);" in page
        assert "payload.windows.forEach(renderWindow);" in page
        assert "WebSocket" not in page
        assert "EventSource" not in page


def _get_page(app: FastAPI, *, cookie: str | None = None) -> tuple[int, str]:
    headers = [(b"host", b"testserver")]
    if cookie is not None:
        headers.append((b"cookie", cookie.encode()))
    messages: list[dict[str, object]] = []
    delivered = False

    async def receive() -> dict[str, object]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "https",
                "path": "/staff/photo-inventory",
                "raw_path": b"/staff/photo-inventory",
                "query_string": b"",
                "headers": headers,
                "client": ("127.0.0.1", 51515),
                "server": ("testserver", 443),
            },
            receive,
            send,
        )
    )
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return int(start["status"]), body.decode()

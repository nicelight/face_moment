from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi import FastAPI

from face_moment.entrypoints.backend import create_app
from face_moment.inventory import http as inventory_http
from face_moment.inventory.ingest_targets import InvalidSessionError


@pytest.fixture
def uploader_page_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    @contextmanager
    def database_session(_: object) -> Iterator[object]:
        yield object()

    def read_context(_: object, *, session_token: str | None) -> dict[str, object]:
        if session_token != "photographer-session":
            raise InvalidSessionError
        return {"schema_version": 1, "spas": []}

    monkeypatch.setattr(inventory_http, "_database_session", database_session)
    monkeypatch.setattr(inventory_http, "read_ingest_target_context", read_context)
    return create_app()


def test_photo_upload_page_requires_photographer_and_keeps_independent_rows(
    uploader_page_app: FastAPI,
) -> None:
    unauthorized_status, _ = _get_page(uploader_page_app)
    assert unauthorized_status == 401

    status_code, page = _get_page(
        uploader_page_app,
        cookie="fm_staff_session=photographer-session",
    )

    assert status_code == 200
    assert 'id="spa-id"' in page
    assert 'id="visit-date"' in page
    assert 'id="photos"' in page
    assert 'accept="image/jpeg" multiple' in page
    assert 'fetch("/api/inventory/ingest-targets"' in page
    assert 'fetch("/api/inventory/photos"' in page
    assert "await Promise.all" in page
    assert "appendResultRow(file, visitDate)" in page
    assert 'response.status === 201' in page
    assert 'response.status === 200' in page
    assert 'response.status === 413 || response.status === 422' in page
    assert "EXIF date differs; selected date retained" in page
    assert "minio" not in page.lower()
    assert "batch" not in page.lower()
    assert "manifest" not in page.lower()


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
                "path": "/staff/photo-upload",
                "raw_path": b"/staff/photo-upload",
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
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return int(start["status"]), response_body.decode()

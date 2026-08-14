from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI

from face_moment.entrypoints.backend import create_app
from face_moment.inventory import http as inventory_http
from face_moment.inventory.processing_health import ProcessingHealthAccessDeniedError
from face_moment.platform.auth.sessions import InvalidSessionError


@pytest.fixture
def processing_health_page_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    @contextmanager
    def database_session(_: object) -> Iterator[object]:
        yield object()

    def authorize(_: object, *, session_token: str | None) -> None:
        if session_token in {"operator-session", "developer-session"}:
            return
        if session_token == "photographer-session":
            raise ProcessingHealthAccessDeniedError
        raise InvalidSessionError

    monkeypatch.setattr(inventory_http, "_database_session", database_session)
    monkeypatch.setattr(
        inventory_http,
        "authorize_processing_health_access",
        authorize,
        raising=False,
    )
    return create_app()


def test_processing_health_page_requires_operational_role_and_renders_only_api_truth(
    processing_health_page_app: FastAPI,
) -> None:
    assert _get_page(processing_health_page_app)[0] == 401

    for role in ("operator", "developer"):
        status_code, page = _get_page(
            processing_health_page_app,
            cookie=f"fm_staff_session={role}-session",
        )
        assert status_code == 200
        assert 'id="processing-health-query"' in page
        assert 'id="health-spa-id"' in page
        assert 'fetch(`/api/inventory/processing-health?${query}`' in page
        assert "setInterval(loadHealth, 5000);" in page
        assert 'id="queue-failed"' in page
        assert 'id="queue-last-recovery-at"' in page
        assert 'id="slo-success-ratio"' in page
        assert 'id="slo-verdict"' in page
        assert 'id="postgresql-status"' in page
        assert 'id="minio-status"' in page
        assert 'renderValue("slo-success-ratio", slo.success_ratio, "no ratio")' in page
        assert 'renderValue("slo-verdict", slo.meets_95_percent, "no verdict")' in page
        assert "storage.postgresql" in page
        assert "storage.minio" in page
        assert "JSON.stringify" not in page
        assert "handle /staff/processing-health" in Path("deploy/Caddyfile").read_text()
        for protected_term in (
            "task036-protected",
            "postgresql://",
            "s3_secret_key",
            "/run/face-moment",
            "object_key",
            "embedding",
        ):
            assert protected_term not in page.lower()

    assert _get_page(
        processing_health_page_app,
        cookie="fm_staff_session=photographer-session",
    )[0] == 403


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
                "path": "/staff/processing-health",
                "raw_path": b"/staff/processing-health",
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

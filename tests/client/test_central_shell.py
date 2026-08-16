from __future__ import annotations

import asyncio
from pathlib import Path

from face_moment.entrypoints.backend import CLIENT_ROOT, create_app


def test_central_shell_is_plain_static_and_uses_same_origin_navigation() -> None:
    html = (CLIENT_ROOT / "index.html").read_text()
    module = (CLIENT_ROOT / "app.js").read_text()
    stylesheet = (CLIENT_ROOT / "styles.css").read_text()

    assert '<script type="module" src="/client/app.js"></script>' in html
    assert 'href="#advertising"' in html
    assert 'href="#configuration"' in html
    assert 'href="#debug"' in html
    assert 'id="client-view"' in html
    assert "Добро пожаловать" in module
    assert "local advertising" not in module.lower()
    assert "fetch(" not in module
    assert "WebSocket" not in module
    assert "http://" not in html + module + stylesheet
    assert "https://" not in html + module + stylesheet


def test_backend_serves_shell_and_static_module() -> None:
    app = create_app()
    assert CLIENT_ROOT == Path("client").resolve()
    assert _get(app, "/")[0] == 200
    assert "SpaPromoClient" in _get(app, "/")[1]
    module_status, module = _get(app, "/client/app.js")
    assert module_status == 200
    assert "hashchange" in module


def test_edge_has_only_the_existing_backend_as_client_origin() -> None:
    caddy = Path("deploy/Caddyfile").read_text()

    assert "handle /client/*" in caddy
    assert "handle /" in caddy
    assert caddy.count("reverse_proxy backend:8000") >= 8
    assert caddy.count("https://") == 1
    assert "https://localhost:8443" in caddy
    assert "http://" not in caddy
    assert "websocket" not in caddy.lower()
    assert "bridge" not in caddy.lower()


def _get(app: object, path: str) -> tuple[int, str]:
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
        app(  # type: ignore[operator]
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "https",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [(b"host", b"testserver")],
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

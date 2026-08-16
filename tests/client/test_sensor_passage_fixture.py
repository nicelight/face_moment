from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


CLIENT_ROOT = Path(__file__).parents[2] / "client"
ALLOWED_ORIGIN = "https://central.example.test"
SENSOR_SECRET = "fixture-secret-never-in-url"
SENSOR_ID = "fm-sensor1"
EVENT = {
    "schema_version": 1,
    "sensor_id": SENSOR_ID,
    "boot_id": "48cf0a18-2c87-46b6-bb26-c46e81606535",
    "sequence": 17,
    "type": "passage",
}


class PassageFixtureHandler(BaseHTTPRequestHandler):
    poll_count = 0
    authorized_poll_count = 0
    observed_paths: list[str] = []

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Vary", "Origin")

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler contract
        if self.headers.get("Origin") != ALLOWED_ORIGIN:
            self.send_response(403)
            self._cors()
            self.end_headers()
            return
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        self.__class__.poll_count += 1
        self.__class__.observed_paths.append(self.path)
        origin = self.headers.get("Origin")
        authorization = self.headers.get("Authorization")
        if origin != ALLOWED_ORIGIN:
            self.send_response(403)
            self._cors()
            self.end_headers()
            return
        if authorization != f"Bearer {SENSOR_SECRET}":
            self.send_response(401)
            self._cors()
            self.end_headers()
            return

        self.__class__.authorized_poll_count += 1
        if self.__class__.authorized_poll_count == 1:
            body = json.dumps(EVENT).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(204)
        self._cors()
        self.end_headers()


def _start_fixture() -> tuple[ThreadingHTTPServer, str]:
    PassageFixtureHandler.poll_count = 0
    PassageFixtureHandler.authorized_poll_count = 0
    PassageFixtureHandler.observed_paths = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), PassageFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}/api/v1/passage-events/next"


def _request(url: str, *, method: str = "GET", **headers: str):
    request = Request(url, method=method, headers=headers)
    try:
        return urlopen(request, timeout=2)
    except HTTPError as error:
        return error


def test_protocol_fixture_proves_cors_auth_event_and_timeout() -> None:
    server, endpoint = _start_fixture()
    try:
        preflight = _request(
            endpoint,
            method="OPTIONS",
            Origin=ALLOWED_ORIGIN,
            **{"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "Authorization"},
        )
        assert preflight.status == 204
        assert preflight.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
        assert preflight.headers["Vary"] == "Origin"
        assert preflight.headers["Access-Control-Allow-Methods"] == "GET, OPTIONS"
        assert preflight.headers["Access-Control-Allow-Headers"] == "Authorization"

        wrong_origin = _request(endpoint, Origin="https://unlisted.example.test")
        assert wrong_origin.status == 403
        missing_auth = _request(endpoint, Origin=ALLOWED_ORIGIN)
        assert missing_auth.status == 401
        wrong_auth = _request(
            endpoint,
            Origin=ALLOWED_ORIGIN,
            Authorization="Bearer wrong-secret",
        )
        assert wrong_auth.status == 401

        event_response = _request(
            endpoint,
            Origin=ALLOWED_ORIGIN,
            Authorization=f"Bearer {SENSOR_SECRET}",
        )
        assert event_response.status == 200
        assert json.loads(event_response.read()) == EVENT

        timeout_response = _request(
            endpoint,
            Origin=ALLOWED_ORIGIN,
            Authorization=f"Bearer {SENSOR_SECRET}",
        )
        assert timeout_response.status == 204
        assert PassageFixtureHandler.poll_count == 5
        assert all(SENSOR_SECRET not in path for path in PassageFixtureHandler.observed_paths)
    finally:
        server.shutdown()
        server.server_close()


def test_client_source_keeps_strict_decode_and_forbidden_routes_out() -> None:
    source = (CLIENT_ROOT / "sensor.js").read_text()
    app_source = (CLIENT_ROOT / "app.js").read_text()
    assert '"/api/v1/passage-events/next"' in source
    assert 'method: "GET"' in source
    assert "Authorization: this.authorization" in source
    assert "mode: \"cors\"" in source
    assert 'response.status === 204' in source
    assert 'response.status === 200' in source
    assert "schema_version" in source
    assert "boot_id" in source
    assert "sequence" in source
    assert "new Set()" in source
    assert "WebSocket" not in source + app_source
    assert "EventSource" not in source + app_source
    assert "navigator.serviceWorker" not in source + app_source
    assert "discover" not in source.lower()
    assert SENSOR_SECRET not in source + app_source
    assert "http://fm-sensor" not in source

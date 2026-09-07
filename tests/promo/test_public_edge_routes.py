"""Live Caddy proof for the canonical public backend route groups."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.platform.auth.sessions import LoginRateLimiter, create_browser_session
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.promo import (
    PromoAttemptRepository,
    ResultAssembly,
    derive_media_ref,
)
from face_moment.serving_control import DisplayClientRepository, IngestTargetRepository
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY


ROOT = Path(__file__).resolve().parents[2]
EDGE_IMAGE = "caddy:2.10.0-alpine"
DISPLAY_TOKEN = "task115-edge-display-token"
DISPLAY_SECRET = "task115-edge-qr-secret"
_TLS_CONTEXT = ssl._create_unverified_context()


@dataclass(frozen=True, slots=True)
class _Response:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class _LiveEdge:
    base_url: str
    engine: object
    spa_id: uuid.UUID
    session_id: uuid.UUID
    media_ref: str
    display_token: str
    cookies: dict[str, dict[str, str]]
    realtime_observations: list[dict[str, object]]
    backend_observations: list[str]


class _PreviewStore:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def read(self, *, key: str) -> bytes:
        self.keys.append(key)
        return b"synthetic-private-preview"


class _RealtimeHandler(BaseHTTPRequestHandler):
    server: "_RecordingHTTPServer"

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        raw_length = self.headers.get("Content-Length")
        length = int(raw_length) if raw_length else 0
        body = self.rfile.read(length)
        self.server.observations.append(
            {
                "path": self.path,
                "body_length": len(body),
                "x_forwarded_for": self.headers.get("X-Forwarded-For"),
                "authorization": self.headers.get("Authorization"),
            }
        )
        response = b'{"accepted":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(response)
        except BrokenPipeError:
            # Caddy closes the capped request after the upstream has received
            # the permitted prefix and the edge emits 413.
            pass

    def log_message(self, _format: str, *_args: object) -> None:
        return


class _RecordingHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, _RealtimeHandler)
        self.observations: list[dict[str, object]] = []


class _BackendObservationApp:
    """Record paths that actually cross the edge into the backend."""

    def __init__(self, app: object, observations: list[str]) -> None:
        self._app = app
        self._observations = observations

    async def __call__(self, scope: dict[str, object], receive: object, send: object) -> None:
        if scope.get("type") == "http":
            self._observations.append(str(scope.get("path")))
        await self._app(scope, receive, send)  # type: ignore[misc]


@pytest.fixture
def live_edge(monkeypatch: pytest.MonkeyPatch) -> Iterator[_LiveEdge]:
    """Run current backend/auth and Caddy against task-owned disposable state."""

    monkeypatch.setenv("REALTIME_RESULT_DISPLAY_MS", "15000")
    monkeypatch.setenv("REALTIME_SUCCESS_COOLDOWN_MS", "30000")
    monkeypatch.setenv("PROMO_QR_TICKET_SECRET", DISPLAY_SECRET)
    monkeypatch.setenv("DEPENDENCY_WAIT_SECONDS", "10")

    with disposable_postgresql_engine("task115_edge") as engine:
        marker = uuid.uuid4().hex
        credentials: dict[str, dict[str, str]] = {}
        staff_ids: dict[str, uuid.UUID] = {}
        with Session(engine) as session:
            revision = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE,
                validated_at=datetime.now(UTC),
                **PIPELINE_COMPATIBILITY,
            )
            target = IngestTargetRepository(session).configure_spa(
                name=f"task115-spa-{marker}",
                timezone="Asia/Dushanbe",
                serving_pipeline_revision_id=revision.id,
            )
            display_client = DisplayClientRepository(session).provision(
                spa_id=target.spa_id,
                name=f"task115-display-{marker}",
            )
            # Provision all three real staff roles used by the route matrix.
            for role in (StaffRole.OPERATOR, StaffRole.DEVELOPER, StaffRole.PHOTOGRAPHER):
                role_name = role.value
                username = f"task115-{role_name}-{marker}"
                password = f"task115-password-{marker}"
                principal = provision_staff_user(
                    session,
                    username=username,
                    password=password,
                    role=role,
                )
                staff_ids[role_name] = principal.staff_user_id
                credentials[role_name] = {"username": username, "password": password}
            session.commit()

            cookies: dict[str, dict[str, str]] = {}
            for role_name, account in credentials.items():
                browser_session = create_browser_session(
                    session,
                    username=account["username"],
                    password=account["password"],
                    ip_address="198.18.0.115",
                    ttl_seconds=3600,
                    limiter=LoginRateLimiter(limit=100, window_seconds=60),
                )
                cookies[role_name] = {
                    "fm_staff_session": browser_session.session_token,
                    "fm_staff_csrf": browser_session.csrf_token,
                }

            photo_ids = tuple(uuid.uuid4() for _ in range(4))
            now = datetime.now(UTC)
            for index, photo_id in enumerate(photo_ids):
                session.add(
                    Photo(
                        id=photo_id,
                        spa_id=target.spa_id,
                        visit_date=date(2026, 9, 7),
                        captured_at=now + timedelta(seconds=index),
                        captured_at_source="upload_started_at",
                        accepted_at=now,
                        admission_pipeline_revision_id=revision.id,
                        uploader_id=staff_ids["photographer"],
                        checksum_sha256=hashlib.sha256(
                            f"task115-photo-{marker}-{index}".encode()
                        ).digest(),
                        original_object_key=f"private/task115/{marker}/{index}.jpg",
                        original_byte_size=100,
                        width=10,
                        height=10,
                        is_active=True,
                    )
                )
                session.add(
                    PhotoPipelineState(
                        photo_id=photo_id,
                        pipeline_revision_id=revision.id,
                        status="ready",
                        attempt_count=1,
                        status_changed_at=now,
                        searchable_at=now,
                        preview_object_key=f"private/task115/{marker}/{index}.jpg",
                        thumbnail_object_key=f"private/task115/{marker}/{index}-thumb.jpg",
                    )
                )
            session.flush()

            attempt = PromoAttemptRepository(session).create_or_get(
                spa_id=target.spa_id,
                client_attempt_id=uuid.uuid4(),
                trigger_source="test",
                client_release="task115-edge",
                detector_id="mediapipe_blazeface_full_range",
                model_version="task115-edge",
                jpeg_quality=82,
                camera_device_id="task115-camera",
                reference_series_ready_at=now,
                local_detection_completed_ms=100,
                request_started_ms=200,
                proposal_count=4,
                settings_revision=1,
                visit_date=date(2026, 9, 7),
                pipeline_revision_id=revision.id,
                pipeline_code=PipelineCode.OPENCV_SFACE,
                query_source="reference",
                threshold=0.7,
                quality_settings={"version": 1},
                release_id="task115-edge",
                deadline_ms=3000,
            )
            attempts = PromoAttemptRepository(session)
            attempts.mark_search_started(attempt, now=now)
            result = attempts.publish_result(
                attempt,
                ResultAssembly(
                    outcome="result",
                    session_result_photo_ids=photo_ids,
                    teaser_photo_ids=photo_ids,
                    n=4,
                ),
                qr_ticket_secret=DISPLAY_SECRET,
                qr_issued_at=now,
                display_expires_at=now + timedelta(minutes=5),
            )
            session.commit()

            # The repository-generated token is the accepted value; keep the
            # constant above only as the fixture secret, never as credentials.
            display_token = display_client.token_value

        app = create_app()
        preview_store = _PreviewStore()
        app.state.promo_display_object_store = preview_store
        backend_port = _free_port()
        realtime_server = _RecordingHTTPServer(("127.0.0.1", 0))
        realtime_thread = threading.Thread(
            target=realtime_server.serve_forever,
            name="task115-realtime-upstream",
            daemon=True,
        )
        realtime_thread.start()

        import uvicorn

        backend_observations: list[str] = []
        backend_server = uvicorn.Server(
            uvicorn.Config(
                    _BackendObservationApp(app, backend_observations),
                host="127.0.0.1",
                port=backend_port,
                log_level="error",
                access_log=False,
                proxy_headers=True,
                forwarded_allow_ips="*",
            )
        )
        backend_thread = threading.Thread(
            target=backend_server.run,
            name="task115-current-backend",
            daemon=True,
        )
        backend_thread.start()

        edge_port = _free_port()
        # Keep all task-owned TLS/data files below the repository workspace.
        config_dir = tempfile.TemporaryDirectory(
            prefix=".task115-caddy-", dir=ROOT
        )
        config_path = Path(config_dir.name) / "Caddyfile"
        config = (ROOT / "deploy/Caddyfile").read_text()
        config = (
            "{\n"
            "\tadmin off\n"
            "\tauto_https disable_redirects\n"
            "\tskip_install_trust\n"
            "\tdefault_bind 127.0.0.1\n"
            "}\n\n"
            + config
        )
        config = config.replace("https://localhost:8443", f"https://localhost:{edge_port}")
        config = config.replace("backend:8000", f"127.0.0.1:{backend_port}")
        config = config.replace(
            "realtime:8002",
            f"127.0.0.1:{realtime_server.server_address[1]}",
        )
        config_path.write_text(config)
        caddy_process: subprocess.Popen[str] | None = None
        caddy_log = None
        try:
            _wait_http(f"http://127.0.0.1:{backend_port}", "/healthz", expected=200)
            caddy_binary = Path(config_dir.name) / "caddy"
            extractor = subprocess.run(
                ["docker", "create", EDGE_IMAGE],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            try:
                subprocess.run(
                    ["docker", "cp", f"{extractor}:/usr/bin/caddy", str(caddy_binary)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            finally:
                subprocess.run(["docker", "rm", extractor], check=False, capture_output=True)
            caddy_binary.chmod(0o755)
            caddy_log = (Path(config_dir.name) / "caddy.log").open("w")
            caddy_env = {
                **dict(os.environ),
                "XDG_DATA_HOME": f"{config_dir.name}/data",
                "XDG_CONFIG_HOME": f"{config_dir.name}/config",
            }
            subprocess.run(
                [str(caddy_binary), "validate", "--config", str(config_path), "--adapter", "caddyfile"],
                check=True,
                env=caddy_env,
                stdout=caddy_log,
                stderr=caddy_log,
            )
            caddy_process = subprocess.Popen(
                [
                    str(caddy_binary),
                    "run",
                    "--config",
                    str(config_path),
                    "--adapter",
                    "caddyfile",
                ],
                env=caddy_env,
                stdout=caddy_log,
                stderr=caddy_log,
                text=True,
            )
            _wait_http(f"https://localhost:{edge_port}", "/healthz", expected=200)
            yield _LiveEdge(
                base_url=f"https://localhost:{edge_port}",
                engine=engine,
                spa_id=target.spa_id,
                session_id=result.session_id,
                media_ref=derive_media_ref(
                    result.session_id,
                    photo_ids[0],
                    qr_ticket_secret=DISPLAY_SECRET,
                ),
                display_token=display_token,
                cookies=cookies,
                realtime_observations=realtime_server.observations,
                backend_observations=backend_observations,
            )
        except Exception:
            caddy_log_path = Path(config_dir.name) / "caddy.log"
            detail = caddy_log_path.read_text() if caddy_log_path.exists() else ""
            raise RuntimeError(detail)
        finally:
            if caddy_process is not None:
                caddy_process.terminate()
                try:
                    caddy_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    caddy_process.kill()
                    caddy_process.wait(timeout=5)
            if caddy_log is not None:
                caddy_log.close()
            config_dir.cleanup()
            realtime_server.shutdown()
            realtime_server.server_close()
            realtime_thread.join(timeout=5)
            backend_server.should_exit = True
            backend_thread.join(timeout=10)


def test_canonical_route_groups_are_named_without_prefix_stripping() -> None:
    caddy = (ROOT / "deploy/Caddyfile").read_text()
    normalized = " ".join(caddy.split())
    expected = (
        "/api/promo/*",
        "/api/serving/spas/*/active-visit-date",
        "/api/diagnostics/retention",
        "/staff/search-settings",
        "/staff/photo-inventory",
        "/staff/calibrations",
        "/staff/calibrations/*",
        "/staff/diagnostics-retention",
    )
    assert "@backend_canonical path" in normalized
    for path in expected:
        assert path in normalized
    assert "handle_path /api/promo/" not in caddy
    assert "handle_path /staff/" not in caddy
    assert "path /api/*" not in caddy


def test_live_caddy_forwards_promo_auth_media_and_ack(live_edge: _LiveEdge) -> None:
    auth = {"Authorization": f"Bearer {live_edge.display_token}"}
    unauthorized = _request(live_edge.base_url, "/api/promo/display/config")
    assert unauthorized.status == 401
    assert unauthorized.headers.get("cache-control") == "no-store"

    config = _request(
        live_edge.base_url,
        "/api/promo/display/config",
        headers=auth,
    )
    assert config.status == 200
    assert json.loads(config.body) == {
        "schema_version": 1,
        "result_display_ms": 15000,
        "success_cooldown_ms": 30000,
    }
    assert config.headers.get("cache-control") == "no-store"

    media = _request(
        live_edge.base_url,
        f"/api/promo/media/{live_edge.media_ref}",
        headers=auth,
    )
    assert media.status == 200
    assert media.body == b"synthetic-private-preview"
    assert media.headers.get("content-type", "").startswith("image/jpeg")
    assert media.headers.get("cache-control") == "no-store"

    assert _request(
        live_edge.base_url,
        "/api/promo/media/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        headers=auth,
    ).status == 404

    acknowledgement = _request(
        live_edge.base_url,
        f"/api/promo/sessions/{live_edge.session_id}/display",
        method="PUT",
        headers={**auth, "Content-Type": "application/json"},
        data=json.dumps(
            {
                "schema_version": 1,
                "status": "confirmed",
                "qr_fully_visible_elapsed_ms": 8421,
            }
        ).encode(),
    )
    assert acknowledgement.status == 200
    assert json.loads(acknowledgement.body)["status"] == "confirmed"
    assert acknowledgement.headers.get("cache-control") == "no-store"
    assert _request(
        live_edge.base_url,
        f"/api/promo/sessions/{uuid.uuid4()}/display",
        method="PUT",
        headers={**auth, "Content-Type": "application/json"},
        data=b'{"schema_version":1,"status":"failed"}',
    ).status == 404


def test_live_caddy_preserves_staff_roles_csrf_and_full_paths(live_edge: _LiveEdge) -> None:
    spa = str(live_edge.spa_id)
    route_paths = (
        "/staff/search-settings",
        "/staff/photo-inventory",
        "/staff/calibrations",
        f"/staff/calibrations/{uuid.uuid4()}",
        "/staff/diagnostics-retention",
        "/api/diagnostics/retention",
        f"/api/serving/spas/{spa}/active-visit-date",
    )
    for path in route_paths:
        assert _request(live_edge.base_url, path).status == 401

    operator = live_edge.cookies["operator"]
    developer = live_edge.cookies["developer"]
    photographer = live_edge.cookies["photographer"]
    cookies_by_role = {
        "operator": operator,
        "developer": developer,
        "photographer": photographer,
    }

    assert _request(
        live_edge.base_url, "/staff/search-settings", cookies=operator
    ).status == 200
    for cookies in (developer, photographer):
        assert _request(
            live_edge.base_url, "/staff/search-settings", cookies=cookies
        ).status == 403

    active_date_path = f"/api/serving/spas/{spa}/active-visit-date"
    assert _request(
        live_edge.base_url, active_date_path, cookies=operator
    ).status == 200
    for cookies in (developer, photographer):
        assert _request(
            live_edge.base_url, active_date_path, cookies=cookies
        ).status == 403
    assert _request(
        live_edge.base_url,
        active_date_path,
        method="PUT",
        cookies=operator,
        headers={"Content-Type": "application/json"},
        data=b'{"visit_date":"2026-09-07"}',
    ).status == 403
    active_update = _request(
        live_edge.base_url,
        active_date_path,
        method="PUT",
        cookies=operator,
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": operator["fm_staff_csrf"],
        },
        data=b'{"visit_date":"2026-09-07"}',
    )
    assert active_update.status == 200
    assert json.loads(active_update.body)["active_visit_date"] == "2026-09-07"

    for cookies in cookies_by_role.values():
        assert _request(
            live_edge.base_url, "/staff/photo-inventory", cookies=cookies
        ).status == 200

    assert _request(
        live_edge.base_url, "/staff/calibrations", cookies=developer
    ).status == 200
    for cookies in (operator, photographer):
        assert _request(
            live_edge.base_url, "/staff/calibrations", cookies=cookies
        ).status == 403
    assert _request(
        live_edge.base_url,
        "/staff/calibrations",
        method="POST",
        cookies=developer,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=b"",
    ).status == 403
    assert _request(
        live_edge.base_url, "/staff/calibrations/00000000-0000-0000-0000-000000000000", cookies=developer
    ).status == 404

    for path in ("/api/diagnostics/retention", "/staff/diagnostics-retention"):
        for cookies in (operator, developer):
            assert _request(live_edge.base_url, path, cookies=cookies).status == 200
        assert _request(live_edge.base_url, path, cookies=photographer).status == 403


def test_live_caddy_dispatches_realtime_and_keeps_body_caps(live_edge: _LiveEdge) -> None:
    headers = {
        "Authorization": "Bearer task115-realtime-fixture",
        "Content-Type": "application/octet-stream",
    }
    first = _request(
        live_edge.base_url,
        "/api/realtime/attempts",
        method="POST",
        headers=headers,
        data=b"small-request",
    )
    timing_id = uuid.uuid4()
    second = _request(
        live_edge.base_url,
        f"/api/realtime/attempts/{timing_id}/client-timing",
        method="POST",
        headers=headers,
        data=b"timing-request",
    )
    assert first.status == 200
    assert second.status == 200
    assert [item["path"] for item in live_edge.realtime_observations] == [
        "/api/realtime/attempts",
        f"/api/realtime/attempts/{timing_id}/client-timing",
    ]
    assert all(item["x_forwarded_for"] for item in live_edge.realtime_observations)

    before = len(live_edge.realtime_observations)
    over_realtime = _request(
        live_edge.base_url,
        "/api/realtime/attempts",
        method="POST",
        headers=headers,
        data=b"x" * (20 * 1024 * 1024 + 1),
    )
    assert over_realtime.status == 413
    # Caddy's request_body cap may stream the permitted prefix to the
    # upstream before reporting the over-cap request as 413.  It must never
    # pass bytes beyond the accepted 20 MiB limit.
    assert len(live_edge.realtime_observations) <= before + 1
    assert all(
        int(item["body_length"]) <= 20 * 1024 * 1024
        for item in live_edge.realtime_observations[before:]
    )

    # Send only the declared over-cap length.  The edge's early Content-Length
    # matcher must reject this before a client would need to upload the body.
    over_upload = _request_with_declared_content_length(
        live_edge.base_url,
        "/api/inventory/photos",
        content_length=11 * 1024 * 1024 + 1,
    )
    assert over_upload.status == 413
    assert "/api/inventory/photos" not in live_edge.backend_observations
    assert _request_without_content_length(
        live_edge.base_url, "/api/inventory/photos"
    ).status == 413

    for path in ("/api/internal/private-store", "/api/realtime/private-store"):
        response = _request(live_edge.base_url, path)
        # The current edge leaves unmatched paths as an empty response.  The
        # security property here is that neither path crosses into a public
        # backend owner or returns private-store data.
        assert response.status in {200, 404}
        assert response.body == b""
        assert path not in live_edge.backend_observations
    assert _request(live_edge.base_url, "/q").status in {401, 503}


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_http(base_url: str, path: str, *, expected: int) -> None:
    deadline = time.monotonic() + 30
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = _request(base_url, path)
            if response.status == expected:
                return
            last_error = RuntimeError(f"{base_url}{path} returned {response.status}")
        except Exception as error:
            last_error = error
        time.sleep(0.2)
    raise RuntimeError(f"timed out waiting for {base_url}{path}") from last_error


def _request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    data: bytes | None = None,
) -> _Response:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
    )
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    if cookies:
        request.add_header(
            "Cookie",
            "; ".join(f"{name}={value}" for name, value in cookies.items()),
        )
    try:
        with urllib.request.urlopen(request, context=_TLS_CONTEXT, timeout=30) as response:
            return _Response(
                response.status,
                {name.lower(): value for name, value in response.headers.items()},
                response.read(),
            )
    except urllib.error.HTTPError as error:
        return _Response(
            error.code,
            {name.lower(): value for name, value in error.headers.items()},
            error.read(),
        )


def _request_without_content_length(base_url: str, path: str) -> _Response:
    parsed = urllib.parse.urlsplit(base_url)
    connection = http.client.HTTPSConnection(
        parsed.hostname,
        parsed.port,
        context=_TLS_CONTEXT,
        timeout=30,
    )
    try:
        connection.putrequest("POST", path, skip_host=True)
        connection.putheader("Host", parsed.netloc)
        connection.putheader("Content-Type", "application/octet-stream")
        connection.endheaders()
        response = connection.getresponse()
        return _Response(
            response.status,
            {name.lower(): value for name, value in response.getheaders()},
            response.read(),
        )
    finally:
        connection.close()


def _request_with_declared_content_length(
    base_url: str, path: str, *, content_length: int
) -> _Response:
    parsed = urllib.parse.urlsplit(base_url)
    connection = http.client.HTTPSConnection(
        parsed.hostname,
        parsed.port,
        context=_TLS_CONTEXT,
        timeout=30,
    )
    try:
        connection.putrequest("POST", path, skip_host=True)
        connection.putheader("Host", parsed.netloc)
        connection.putheader("Content-Type", "application/octet-stream")
        connection.putheader("Content-Length", str(content_length))
        connection.putheader("Expect", "100-continue")
        connection.endheaders()
        response = connection.getresponse()
        return _Response(
            response.status,
            {name.lower(): value for name, value in response.getheaders()},
            response.read(),
        )
    finally:
        connection.close()

"""Two real Caddy hops; isolated TLS, no production DNS or services."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import threading
import time

import pytest
from starlette.requests import Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from face_moment.promo.qr_continuation import PhonePublicRateLimiter

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_HOST = "face-moment.ru"


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def proxy_chain(tmp_path: Path):
    limiter = PhonePublicRateLimiter(limit=60, window_seconds=60)
    now = datetime.now(timezone.utc)

    class Backend(BaseHTTPRequestHandler):
        def do_GET(self):
            result = {}

            async def observe(scope, receive, send):
                request = Request(scope)
                result.update(ip=request.client.host, origin=str(request.url).split(self.path)[0],
                              browser_origin=request.headers.get("origin"))

            async def noop(*args):
                pass

            scope = {"type": "http", "method": "GET", "path": self.path,
                     "query_string": b"", "scheme": "http", "server": ("backend", 8000),
                     "client": self.client_address,
                     "headers": [(k.lower().encode(), v.encode()) for k, v in self.headers.items()]}
            asyncio.run(ProxyHeadersMiddleware(observe, trusted_hosts="127.0.0.1")(scope, noop, noop))
            allowed = limiter.allow(ip_address=result["ip"], now=now)
            body = json.dumps(result).encode()
            self.send_response(200 if allowed else 429)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    thread = threading.Thread(target=backend.serve_forever, daemon=True)
    thread.start()
    processes = []
    logs = []
    try:
        binary = tmp_path / "caddy"
        container = subprocess.check_output(["docker", "create", "caddy:2.10.0-alpine"], text=True).strip()
        try:
            subprocess.run(["docker", "cp", f"{container}:/usr/bin/caddy", str(binary)], check=True, capture_output=True)
        finally:
            subprocess.run(["docker", "rm", container], check=True, capture_output=True)
        binary.chmod(0o755)
        inner_port, outer_port = _port(), _port()
        inner = (ROOT / "deploy/Caddyfile").read_text().replace(":8443", f":{inner_port}")
        inner = inner.replace("backend:8000", f"127.0.0.1:{backend.server_port}")
        inner = inner.replace("realtime:8002", f"127.0.0.1:{backend.server_port}")
        options = "\tadmin off\n\tauto_https disable_redirects\n\tskip_install_trust\n\tdefault_bind 127.0.0.1\n"
        inner = inner.replace("{\n", "{\n" + options, 1)
        outer = (ROOT / "deploy/frp/vps/Caddyfile").read_text()
        first, rest = outer.split("\n", 1)
        sites = first.removesuffix(" {").replace("}, ", f"}}:{outer_port}, ")
        outer = "{\n" + options + "}\n" + sites + f":{outer_port} {{\n\ttls internal\n" + rest
        outer = outer.replace("127.0.0.1:18443", f"127.0.0.1:{inner_port}")
        for name, config in (("inner", inner), ("outer", outer)):
            config_path = tmp_path / f"{name}.Caddyfile"
            config_path.write_text(config)
            env = {**os.environ, "FACE_MOMENT_PUBLIC_HOST": PUBLIC_HOST,
                   "FACE_MOMENT_FRP_HOST": "face-time.moment-studio.ru",
                   "FACE_MOMENT_FRP_PROXY_IP": "127.0.0.1",
                   "XDG_DATA_HOME": str(tmp_path / name / "data"),
                   "XDG_CONFIG_HOME": str(tmp_path / name / "config")}
            log = (tmp_path / f"{name}.log").open("w")
            logs.append(log)
            subprocess.run([str(binary), "validate", "--config", str(config_path), "--adapter", "caddyfile"],
                           env=env, stdout=log, stderr=log, check=True)
            processes.append(subprocess.Popen([str(binary), "run", "--config", str(config_path), "--adapter", "caddyfile"],
                                              env=env, stdout=log, stderr=log))

        def request(port=outer_port, peer="127.0.0.2", host=PUBLIC_HOST, path="/api/phone/session", **headers):
            connection = http.client.HTTPSConnection(host, port,
                context=ssl._create_unverified_context(), source_address=(peer, 0), timeout=3)
            connection._create_connection = lambda address, timeout, source_address: socket.create_connection(
                ("127.0.0.1", port), timeout, source_address)
            try:
                connection.request("GET", path, headers={"Host": host, "Origin": f"https://{PUBLIC_HOST}", **headers})
                response = connection.getresponse()
                body = response.read()
                return response.status, json.loads(body) if body else None
            finally:
                connection.close()

        for _ in range(60):
            try:
                if request(path="/healthz")[0] == 200:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(.1)
        else:
            pytest.fail("isolated Caddy chain did not become ready")
        yield request, inner_port
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for log in logs:
            log.close()
        backend.shutdown()
        backend.server_close()
        thread.join(timeout=2)


def test_public_origin_distinct_ip_budgets_and_spoof_rejection(proxy_chain):
    request, inner_port = proxy_chain
    status, body = request(**{"X-Forwarded-For": "198.51.100.99", "X-Forwarded-Host": "evil.example"})
    assert status == 200
    assert body == {"ip": "127.0.0.2", "origin": f"https://{PUBLIC_HOST}", "browser_origin": f"https://{PUBLIC_HOST}"}
    for _ in range(59):
        assert request()[0] == 200
    assert request()[0] == 429
    assert request(peer="127.0.0.3")[0] == 200
    # An untrusted direct connection cannot inject a forwarded IP either.
    status, body = request(port=inner_port, peer="127.0.0.4", **{"X-Forwarded-For": "198.51.100.99"})
    assert status == 200 and body["ip"] == "127.0.0.4"
    status, body = request(port=inner_port, peer="127.0.0.5", host="localhost")
    assert status == 200 and body["origin"] == "https://localhost"

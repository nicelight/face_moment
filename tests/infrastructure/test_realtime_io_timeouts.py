from __future__ import annotations

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from time import monotonic

from botocore.exceptions import ReadTimeoutError
import pytest
from sqlalchemy.exc import OperationalError

from face_moment.infrastructure.database import create_realtime_database_engine
from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import Settings


def test_realtime_sql_timeout_cancels_query_and_connection_recovers() -> None:
    engine = create_realtime_database_engine(
        Settings.from_env().database_url, deadline_ms=50
    )
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SHOW lock_timeout").scalar() == "3s"
            connection.rollback()
            started = monotonic()
            with pytest.raises(OperationalError, match="statement timeout"):
                connection.exec_driver_sql("SELECT pg_sleep(2)")
            assert monotonic() - started < 1.5
            connection.rollback()
            assert connection.exec_driver_sql("SELECT 1").scalar() == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("send_headers", [False, True])
def test_realtime_minio_stalled_headers_or_body_do_not_retry(send_headers: bool) -> None:
    release = Event()
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append(self.path)
            if send_headers:
                self.send_response(200)
                self.send_header("Content-Length", "10")
                self.end_headers()
                self.wfile.flush()
            release.wait(10)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = replace(
        Settings.from_env(),
        s3_endpoint_url=f"http://127.0.0.1:{server.server_port}",
        s3_access_key="local-fixture", s3_secret_key="local-fixture",
        s3_bucket="timeout-fixture",
    )
    try:
        started = monotonic()
        with pytest.raises(ReadTimeoutError):
            PrivateObjectStore(settings, realtime_io=True).read(key="stalled")
        assert monotonic() - started < 5
        assert len(requests) == 1
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)

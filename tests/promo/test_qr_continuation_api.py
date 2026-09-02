from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import itertools
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator
import uuid

import pytest
from fastapi import Response
from fastapi.routing import APIRoute
from starlette.requests import Request

from face_moment.entrypoints.backend import create_app
from face_moment.entrypoints import common as entrypoint_common
from face_moment.infrastructure.settings import Settings
from face_moment.promo import http as promo_http
from face_moment.promo import qr_continuation
from face_moment.promo.qr_continuation import (
    PhoneActivityView,
    PhoneContinuationService,
    PhoneMediaNotFoundError,
    PhonePublicRateLimiter,
    PhoneSessionView,
    PhoneTeaser,
    validate_phone_purchase_url,
)
from face_moment.promo.session import PromoSessionNotFoundError


ROOT = Path(__file__).resolve().parents[2]
TICKET = "A" * 43
PURCHASE_URL = "https://face.example.test/purchase"
START = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)
EXPECTED_ROUTES = {
    "/q",
    "/phone",
    "/api/phone/session",
    "/api/phone/activity",
    "/api/phone/media/{media_ref}",
}


class FakeDatabaseSession:
    def __init__(self) -> None:
        self.entries = 0
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakePhoneService:
    def __init__(self) -> None:
        self.session_id = uuid.uuid4()
        self.attempt_id = uuid.uuid4()
        self.photo_id = uuid.uuid4()
        self.first_open_expires_at = START + timedelta(minutes=30)
        self.first_opened_at: datetime | None = None
        self.last_seen_at: datetime | None = None
        self.calls: list[str] = []
        self.database: FakeDatabaseSession | None = None
        self.opened_handoffs: list[tuple[uuid.UUID, bool, int]] = []
        self.media_available = True
        self.immutable = {
            "session_id": self.session_id,
            "spa_name": "Fixture SPA",
            "visit_date": date(2026, 8, 28),
            "teaser_photo_ids": (self.photo_id, uuid.uuid4(), uuid.uuid4(), uuid.uuid4()),
            "n": 9,
        }

    def exchange_ticket(
        self, ticket: str, *, now: datetime | None = None
    ) -> tuple[object, bool]:
        self.calls.append("exchange")
        timestamp = _aware(now)
        if ticket != TICKET or timestamp >= self.first_open_expires_at:
            raise PromoSessionNotFoundError("unknown or late")
        if self.last_seen_at is not None and timestamp >= self.last_seen_at + timedelta(
            minutes=60
        ):
            raise PromoSessionNotFoundError("expired")
        first_open = self.first_opened_at is None
        if first_open:
            self.first_opened_at = timestamp
        self.last_seen_at = timestamp
        return SimpleNamespace(id=self.session_id, attempt_id=self.attempt_id), first_open

    def emit_opened(self, *, attempt_id: uuid.UUID, first_open: bool) -> None:
        assert self.database is not None
        self.opened_handoffs.append((attempt_id, first_open, self.database.commits))

    def validate_access(self, ticket: str, *, now: datetime | None = None) -> object:
        self.calls.append("shell")
        self._active(ticket, _aware(now))
        return SimpleNamespace(id=self.session_id)

    def read_session(
        self, ticket: str, *, now: datetime | None = None
    ) -> PhoneSessionView:
        self.calls.append("session")
        timestamp = _aware(now)
        self._active(ticket, timestamp)
        assert self.last_seen_at is not None
        deadline = self.last_seen_at + timedelta(minutes=60)
        teaser = PhoneTeaser(
            photo_id=str(self.photo_id),
            media_url="/api/phone/media/fixture-media",
        )
        return PhoneSessionView(
            session_id=str(self.session_id),
            spa_name="Fixture SPA",
            visit_date="2026-08-28",
            teaser=teaser,
            n=9,
            purchase_url=PURCHASE_URL,
            idle_expires_at=deadline,
            idle_expires_in_ms=int((deadline - timestamp).total_seconds() * 1000),
        )

    def record_activity(
        self, ticket: str, *, now: datetime | None = None
    ) -> PhoneActivityView:
        self.calls.append("activity")
        timestamp = _aware(now)
        self._active(ticket, timestamp)
        self.last_seen_at = timestamp
        deadline = timestamp + timedelta(minutes=60)
        return PhoneActivityView(deadline, 3_600_000)

    def read_media(
        self, ticket: str, media_ref: str, *, now: datetime | None = None
    ) -> bytes:
        self.calls.append("media")
        self._active(ticket, _aware(now))
        if not self.media_available or media_ref != "fixture-media":
            raise PhoneMediaNotFoundError(media_ref)
        return b"fixture-jpeg"

    def _active(self, ticket: str, timestamp: datetime) -> None:
        if ticket != TICKET or self.last_seen_at is None:
            raise PromoSessionNotFoundError("not open")
        if timestamp >= self.last_seen_at + timedelta(minutes=60):
            raise PromoSessionNotFoundError("expired")


def _aware(value: datetime | None) -> datetime:
    assert value is not None and value.tzinfo is not None
    return value.astimezone(timezone.utc)


def _settings(*, limit: int = 100, purchase_url: str | None = PURCHASE_URL) -> object:
    return SimpleNamespace(
        database_url="postgresql+psycopg://unused/unused",
        s3_endpoint_url="http://unused",
        s3_access_key="unused",
        s3_secret_key="unused",
        s3_bucket="unused",
        promo_qr_ticket_secret="fixture-secret",
        phone_public_rate_limit=limit,
        phone_public_rate_window_seconds=60,
        phone_purchase_url=purchase_url,
    )


def _request(
    path: str,
    *,
    method: str = "GET",
    query: str = "",
    ticket: str | None = None,
    ip: str = "198.18.0.10",
    forwarded_for: str | None = None,
    origin: str | None = None,
    json_body: object | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = [
        (b"x-forwarded-for", (forwarded_for or ip).encode("ascii")),
    ]
    body = b""
    if ticket is not None:
        headers.append((b"cookie", f"fm_promo_access={ticket}".encode("ascii")))
    if origin is not None:
        headers.append((b"origin", origin.encode("ascii")))
    if json_body is not None:
        headers.append((b"content-type", b"application/json"))
        body = json.dumps(json_body).encode("utf-8")

    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": query.encode("ascii"),
            "headers": headers,
            "client": (ip, 12345),
            "server": ("central.example.test", 443),
        },
        receive,
    )


def _route(app: object, path: str, method: str) -> object:
    return next(
        route.endpoint
        for route in app.routes  # type: ignore[attr-defined]
        if isinstance(route, APIRoute)
        and route.path == path
        and method in route.methods
    )


def _install_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    limit: int = 100,
    purchase_url: str | None = PURCHASE_URL,
) -> tuple[object, FakePhoneService, FakeDatabaseSession, dict[str, datetime]]:
    app = create_app()
    service = FakePhoneService()
    database = FakeDatabaseSession()
    service.database = database
    clock = {"now": START}
    settings = _settings(limit=limit, purchase_url=purchase_url)

    monkeypatch.setattr(
        promo_http.Settings,
        "from_env",
        classmethod(lambda _cls: settings),
    )

    @contextmanager
    def database_session(_settings_value: object) -> Iterator[FakeDatabaseSession]:
        database.entries += 1
        yield database

    monkeypatch.setattr(promo_http, "_database_session", database_session)
    monkeypatch.setattr(
        promo_http,
        "PhoneContinuationService",
        lambda *_args, **_kwargs: service,
    )
    app.state.promo_phone_clock = lambda: clock["now"]
    app.state.promo_phone_object_store = SimpleNamespace()
    return app, service, database, clock


def _invoke(
    app: object,
    path: str,
    *,
    method: str = "GET",
    request: Request,
) -> Response:
    endpoint = _route(app, path, method)
    if path == "/api/phone/media/{media_ref}":
        return endpoint(request, "fixture-media")  # type: ignore[operator]
    if method == "POST":
        return asyncio.run(endpoint(request))  # type: ignore[operator]
    return endpoint(request)  # type: ignore[operator]


def test_exact_routes_settings_and_forwarded_client_boundary_are_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    paths = {
        route.path for route in app.routes if isinstance(route, APIRoute)
    }
    assert EXPECTED_ROUTES <= paths

    monkeypatch.setenv("PHONE_PUBLIC_RATE_LIMIT", "17")
    monkeypatch.setenv("PHONE_PUBLIC_RATE_WINDOW_SECONDS", "23")
    monkeypatch.setenv("PHONE_PURCHASE_URL", PURCHASE_URL)
    settings = Settings.from_env()
    assert settings.phone_public_rate_limit == 17
    assert settings.phone_public_rate_window_seconds == 23
    assert settings.phone_purchase_url == PURCHASE_URL

    caddy = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    assert "@phone_continuation path /q /phone /api/phone/*" in caddy
    assert "handle @phone_continuation" in caddy
    assert "header_up X-Forwarded-For {remote_host}" in caddy
    assert "header_up X-Forwarded-Proto {http.request.scheme}" in caddy


def test_runtime_disables_query_bearing_access_logs_and_trusts_one_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(_app: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setenv("FACE_MOMENT_TRUSTED_PROXY_IP", "172.29.81.2")
    monkeypatch.setattr("uvicorn.run", fake_run)
    entrypoint_common.run(create_app(), 8000)
    assert captured["access_log"] is False
    assert captured["proxy_headers"] is True
    assert captured["forwarded_allow_ips"] == "172.29.81.2"

    monkeypatch.setenv("FACE_MOMENT_TRUSTED_PROXY_IP", "*")
    with pytest.raises(RuntimeError, match="one exact IP address"):
        entrypoint_common.run(create_app(), 8000)


def test_phone_limiter_ignores_untrusted_raw_forwarded_client_header() -> None:
    request = _request(
        "/q",
        ip="198.18.0.41",
        forwarded_for="203.0.113.99",
    )
    assert promo_http._client_ip(request) == "198.18.0.41"


@pytest.mark.parametrize(
    ("path", "method", "request_factory"),
    [
        ("/q", "GET", lambda ip: _request("/q", query=f"ticket={TICKET}", ip=ip)),
        ("/phone", "GET", lambda ip: _request("/phone", ticket=TICKET, ip=ip)),
        (
            "/api/phone/session",
            "GET",
            lambda ip: _request("/api/phone/session", ticket=TICKET, ip=ip),
        ),
        (
            "/api/phone/activity",
            "POST",
            lambda ip: _request(
                "/api/phone/activity",
                method="POST",
                ticket=TICKET,
                ip=ip,
                origin="https://central.example.test",
                json_body={"schema_version": 1},
            ),
        ),
        (
            "/api/phone/media/{media_ref}",
            "GET",
            lambda ip: _request(
                "/api/phone/media/fixture-media", ticket=TICKET, ip=ip
            ),
        ),
    ],
)
def test_every_public_phone_route_returns_429_before_a_second_disclosure(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    method: str,
    request_factory: object,
) -> None:
    app, service, _database, _clock = _install_fixture(monkeypatch, limit=1)
    service.exchange_ticket(TICKET, now=START)
    before = len(service.calls)
    first = _invoke(app, path, method=method, request=request_factory("198.18.0.11"))  # type: ignore[operator]
    assert first.status_code != 429
    calls_after_first = len(service.calls)
    second = _invoke(app, path, method=method, request=request_factory("198.18.0.11"))  # type: ignore[operator]
    assert second.status_code == 429
    assert second.body == b""
    assert second.headers["cache-control"] == "no-store"
    assert second.headers["referrer-policy"] == "no-referrer"
    assert len(service.calls) == calls_after_first
    assert calls_after_first >= before


def test_forwarded_clients_receive_separate_shared_limiter_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _service, _database, _clock = _install_fixture(monkeypatch, limit=1)
    exchange = _route(app, "/q", "GET")
    first = exchange(  # type: ignore[operator]
        _request("/q", query=f"ticket={TICKET}", ip="198.18.0.21")
    )
    second = exchange(  # type: ignore[operator]
        _request("/q", query=f"ticket={TICKET}", ip="198.18.0.22")
    )
    assert first.status_code == 303
    assert second.status_code == 303


def test_multi_phone_exchange_passive_read_activity_and_exact_idle_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, service, database, clock = _install_fixture(monkeypatch)
    immutable_before = dict(service.immutable)
    exchange = _route(app, "/q", "GET")

    first = exchange(  # type: ignore[operator]
        _request("/q", query=f"ticket={TICKET}", ip="198.18.0.31")
    )
    assert first.status_code == 303
    assert first.headers["location"] == "/phone"
    cookie = first.headers["set-cookie"]
    assert "fm_promo_access=" in cookie
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "Path=/" in cookie
    assert "Max-Age" not in cookie and "Expires" not in cookie and "Domain" not in cookie

    clock["now"] = START + timedelta(minutes=5)
    repeated = exchange(  # type: ignore[operator]
        _request("/q", query=f"ticket={TICKET}", ip="198.18.0.32")
    )
    assert repeated.status_code == 303
    assert service.first_opened_at == START
    assert service.last_seen_at == START + timedelta(minutes=5)
    assert database.commits == 2
    assert service.opened_handoffs == [
        (service.attempt_id, True, 1),
        (service.attempt_id, False, 2),
    ]
    clock["now"] = START + timedelta(minutes=10)
    passive = _invoke(
        app,
        "/api/phone/session",
        request=_request("/api/phone/session", ticket=TICKET, ip="198.18.0.31"),
    )
    payload = json.loads(passive.body)
    assert passive.status_code == 200
    assert payload == {
        "schema_version": 1,
        "session_id": str(service.session_id),
        "spa_name": "Fixture SPA",
        "visit_date": "2026-08-28",
        "teaser": {
            "photo_id": str(service.photo_id),
            "media_url": "/api/phone/media/fixture-media",
        },
        "n": 9,
        "purchase_url": PURCHASE_URL,
        "idle_expires_at": "2026-08-28T09:05:00.000Z",
        "idle_expires_in_ms": 3_300_000,
    }
    assert service.last_seen_at == START + timedelta(minutes=5)

    clock["now"] = START + timedelta(minutes=20)
    activity = _invoke(
        app,
        "/api/phone/activity",
        method="POST",
        request=_request(
            "/api/phone/activity",
            method="POST",
            ticket=TICKET,
            ip="198.18.0.32",
            origin="https://central.example.test",
            json_body={"schema_version": 1},
        ),
    )
    assert activity.status_code == 200
    assert json.loads(activity.body)["idle_expires_in_ms"] == 3_600_000
    assert service.last_seen_at == START + timedelta(minutes=20)
    assert service.immutable == immutable_before

    clock["now"] = START + timedelta(minutes=80)
    expired = _invoke(
        app,
        "/api/phone/session",
        request=_request("/api/phone/session", ticket=TICKET, ip="198.18.0.31"),
    )
    assert expired.status_code == 401
    assert expired.body == b""
    assert "Max-Age=0" in expired.headers["set-cookie"]
    assert service.immutable == immutable_before


def test_ticket_exchange_does_not_emit_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, service, database, _clock = _install_fixture(monkeypatch)

    def fail_commit() -> None:
        raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(database, "commit", fail_commit)
    response = _route(app, "/q", "GET")(  # type: ignore[operator]
        _request("/q", query=f"ticket={TICKET}")
    )

    assert response.status_code == 500
    assert database.rollbacks == 1
    assert service.opened_handoffs == []


def test_safe_redirect_validation_activity_and_media_failures_are_non_disclosing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, service, _database, _clock = _install_fixture(monkeypatch)
    exchange = _route(app, "/q", "GET")
    invalid = exchange(  # type: ignore[operator]
        _request(
            "/q",
            query=f"ticket={TICKET}&purchase_url=https://attacker.invalid",
        )
    )
    assert invalid.status_code == 303
    assert invalid.headers["location"] == PURCHASE_URL
    assert "set-cookie" not in invalid.headers

    missing = _invoke(
        app,
        "/api/phone/session",
        request=_request("/api/phone/session"),
    )
    assert missing.status_code == 401 and missing.body == b""

    service.exchange_ticket(TICKET, now=START)
    forbidden = _invoke(
        app,
        "/api/phone/activity",
        method="POST",
        request=_request(
            "/api/phone/activity",
            method="POST",
            ticket=TICKET,
            origin="https://attacker.invalid",
            json_body={"schema_version": 1},
        ),
    )
    assert forbidden.status_code == 403 and forbidden.body == b""
    last_seen = service.last_seen_at
    invalid_json = _invoke(
        app,
        "/api/phone/activity",
        method="POST",
        request=_request(
            "/api/phone/activity",
            method="POST",
            ticket=TICKET,
            origin="https://central.example.test",
            json_body={"schema_version": 2, "extra": True},
        ),
    )
    assert invalid_json.status_code == 422 and service.last_seen_at == last_seen

    media = _invoke(
        app,
        "/api/phone/media/{media_ref}",
        request=_request("/api/phone/media/fixture-media", ticket=TICKET),
    )
    assert media.status_code == 200 and media.body == b"fixture-jpeg"
    assert media.headers["content-type"] == "image/jpeg"
    service.media_available = False
    disappeared = _invoke(
        app,
        "/api/phone/media/{media_ref}",
        request=_request("/api/phone/media/fixture-media", ticket=TICKET),
    )
    assert disappeared.status_code == 404 and disappeared.body == b""
    assert service.immutable["n"] == 9


def test_percent_encoded_non_ascii_unknown_media_ref_returns_empty_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_row = SimpleNamespace(
        id=uuid.UUID("00000000-0000-4000-8000-000000000081"),
        teaser_photo_ids=[uuid.UUID("00000000-0000-4000-8000-000000000001")],
    )

    class SessionRepository:
        def read_browser_access(
            self, _ticket: str, *, now: datetime | None = None
        ) -> object:
            return session_row

    service = PhoneContinuationService.__new__(PhoneContinuationService)
    service._sessions = SessionRepository()
    service._qr_ticket_secret = b"fixture-secret"

    app = create_app()
    database = FakeDatabaseSession()
    monkeypatch.setattr(
        promo_http.Settings,
        "from_env",
        classmethod(lambda _cls: _settings()),
    )

    @contextmanager
    def database_session(_settings_value: object) -> Iterator[FakeDatabaseSession]:
        yield database

    monkeypatch.setattr(promo_http, "_database_session", database_session)
    monkeypatch.setattr(promo_http, "_phone_service", lambda *_args, **_kwargs: service)
    app.state.promo_phone_clock = lambda: START

    response = _route(app, "/api/phone/media/{media_ref}", "GET")(
        _request("/api/phone/media/%C3%A9", ticket=TICKET),
        "é",
    )

    assert response.status_code == 404
    assert response.body == b""
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_missing_or_invalid_purchase_target_returns_503_before_service_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, service, _database, _clock = _install_fixture(
        monkeypatch, purchase_url=None
    )
    response = _invoke(
        app,
        "/api/phone/session",
        request=_request("/api/phone/session", ticket=TICKET),
    )
    assert response.status_code == 503 and response.body == b""
    assert service.calls == []
    for candidate in (None, "", "http://face.example.test", "https://user@host/path"):
        with pytest.raises(ValueError):
            validate_phone_purchase_url(candidate)


@pytest.mark.parametrize(
    "purchase_url",
    (
        "https://face.example.test:bad/purchase",
        "https://face.example.test:99999/purchase",
        "https://example .com/purchase",
        "https://example%.com/purchase",
        "https://999.999.999.999/purchase",
        "https://example\u0085.com/purchase",
        "https://1\u06623.test/purchase",
        "https://example\u2066.com/purchase",
        "https://example\u202e.com/purchase",
        "https://９９９.９９９.９９９.９９９/purchase",
    ),
)
def test_browser_invalid_purchase_target_returns_503_before_any_disclosure(
    monkeypatch: pytest.MonkeyPatch,
    purchase_url: str,
) -> None:
    app, service, _database, _clock = _install_fixture(
        monkeypatch,
        purchase_url=purchase_url,
    )
    limiter_calls: list[str] = []
    monkeypatch.setattr(
        promo_http,
        "_phone_rate_limiter",
        lambda *_args, **_kwargs: limiter_calls.append("limiter"),
    )

    exchange = _invoke(
        app,
        "/q",
        request=_request("/q", query=f"ticket={TICKET}"),
    )
    session = _invoke(
        app,
        "/api/phone/session",
        request=_request("/api/phone/session", ticket=TICKET),
    )

    assert exchange.status_code == 503 and exchange.body == b""
    assert "location" not in exchange.headers
    assert "set-cookie" not in exchange.headers
    assert session.status_code == 503 and session.body == b""
    assert "set-cookie" not in session.headers
    assert limiter_calls == []
    assert _database.entries == 0
    assert service.calls == []
    with pytest.raises(ValueError):
        validate_phone_purchase_url(purchase_url)


def test_purchase_target_rejects_all_control_hosts_and_invalid_numeric_ipv4() -> None:
    invalid_hosts = [
        "256.0.0.1",
        "1.256.0.1",
        "1.2.256.1",
        "1.2.3.256",
        "1.2.3.4.5",
        "1..2.3",
    ]
    invalid_hosts.extend(
        f"example{chr(codepoint)}.test"
        for codepoint in (*range(0x00, 0x20), *range(0x7F, 0xA0))
    )

    for hostname in invalid_hosts:
        with pytest.raises(ValueError):
            validate_phone_purchase_url(f"https://{hostname}/purchase")


@pytest.mark.parametrize(
    "purchase_url",
    (
        "https://пример.рф/purchase",
        "https://１２７.０.０.１/purchase",
    ),
)
def test_purchase_target_accepts_browser_normalized_unicode_hosts(
    purchase_url: str,
) -> None:
    assert validate_phone_purchase_url(purchase_url) == purchase_url


@pytest.mark.parametrize("availability", itertools.product((False, True), repeat=4))
def test_phone_assembly_uses_first_available_issued_teaser_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    availability: tuple[bool, bool, bool, bool],
) -> None:
    photo_ids = tuple(uuid.uuid4() for _ in range(4))
    row = SimpleNamespace(
        id=uuid.uuid4(),
        spa_id=uuid.uuid4(),
        visit_date=date(2026, 8, 28),
        teaser_photo_ids=list(photo_ids),
        session_result_photo_ids=list(photo_ids) + [uuid.uuid4(), uuid.uuid4()],
        n=6,
        browser_idle_expires_at=START + timedelta(minutes=60),
    )
    snapshot = (
        tuple(row.teaser_photo_ids),
        tuple(row.session_result_photo_ids),
        row.n,
    )

    class SessionRepository:
        def read_browser_access(self, _ticket: str, *, now: datetime) -> object:
            return row

    class SpaRepository:
        def __init__(self, _session: object) -> None:
            pass

        def resolve_ingest_target(self, _spa_id: uuid.UUID) -> object:
            return SimpleNamespace(name="Soft-delete Fixture SPA")

    available = {
        photo_id for photo_id, is_available in zip(photo_ids, availability) if is_available
    }

    def projection(
        _session: object, *, photo_id: uuid.UUID, spa_id: uuid.UUID
    ) -> object | None:
        assert spa_id == row.spa_id
        if photo_id not in available:
            return None
        return SimpleNamespace(
            preview_object_key=f"private/{photo_id}.jpg",
            photo_is_active=False,
        )

    class Store:
        def read(self, *, key: str) -> bytes:
            return f"jpeg:{key}".encode("ascii")

    monkeypatch.setattr(
        qr_continuation,
        "PromoSessionRepository",
        lambda *_args, **_kwargs: SessionRepository(),
    )
    monkeypatch.setattr(qr_continuation, "IngestTargetRepository", SpaRepository)
    monkeypatch.setattr(qr_continuation, "read_photo_processing_projection", projection)

    service = PhoneContinuationService(
        SimpleNamespace(),  # type: ignore[arg-type]
        qr_ticket_secret="fixture-secret",
        purchase_url=PURCHASE_URL,
        object_store=Store(),
    )
    view = service.read_session(TICKET, now=START)
    expected = next((photo_id for photo_id in photo_ids if photo_id in available), None)
    assert (None if view.teaser is None else view.teaser.photo_id) == (
        None if expected is None else str(expected)
    )
    assert view.n == 6
    assert (
        tuple(row.teaser_photo_ids),
        tuple(row.session_result_photo_ids),
        row.n,
    ) == snapshot

    if expected is not None:
        assert view.teaser is not None
        media_ref = view.teaser.media_url.rsplit("/", maxsplit=1)[1]
        assert service.read_media(TICKET, media_ref, now=START).startswith(b"jpeg:")
    else:
        with pytest.raises(PhoneMediaNotFoundError):
            service.read_media(TICKET, "x" * 43, now=START)

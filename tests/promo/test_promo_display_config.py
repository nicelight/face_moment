from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Iterator
import uuid

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

from face_moment.entrypoints.backend import create_app
from face_moment.infrastructure.settings import Settings
from face_moment.promo.display_config import (
    DisplayConfiguration,
    InvalidDisplayConfigurationError,
    read_display_configuration,
)
from face_moment.promo import http as promo_http
from face_moment.serving_control.display_client_auth import DisplayClientPrincipal


def test_display_configuration_keeps_two_positive_values_independent() -> None:
    settings = SimpleNamespace(
        realtime_result_display_ms=1_500,
        realtime_success_cooldown_ms=2_500,
    )

    configuration = read_display_configuration(settings)

    assert configuration == DisplayConfiguration(
        result_display_ms=1_500,
        success_cooldown_ms=2_500,
    )
    assert configuration.as_response() == {
        "schema_version": 1,
        "result_display_ms": 1_500,
        "success_cooldown_ms": 2_500,
    }


@pytest.mark.parametrize(
    "settings",
    (
        SimpleNamespace(realtime_result_display_ms=0, realtime_success_cooldown_ms=2),
        SimpleNamespace(realtime_result_display_ms=1, realtime_success_cooldown_ms=-1),
        SimpleNamespace(realtime_result_display_ms=True, realtime_success_cooldown_ms=2),
        SimpleNamespace(realtime_result_display_ms=1),
    ),
)
def test_missing_or_invalid_value_is_not_replaced_by_the_other_duration(
    settings: object,
) -> None:
    with pytest.raises(InvalidDisplayConfigurationError):
        read_display_configuration(settings)


def _config_route(app) -> APIRoute:
    return next(
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == "/api/promo/display/config"
    )


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/promo/display/config",
            "headers": [(b"authorization", b"Bearer fixture-display-token")],
            "client": ("127.0.0.1", 1234),
            "scheme": "https",
            "server": ("central.example.test", 443),
        }
    )


def test_authenticated_config_route_returns_exact_no_store_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    route = _config_route(app)
    session = object()

    settings = SimpleNamespace(
        database_url="postgresql+psycopg://unused",
        realtime_rate_limit=10,
        realtime_rate_window_seconds=60,
        realtime_result_display_ms=111,
        realtime_success_cooldown_ms=222,
    )

    @contextmanager
    def database(_settings: object) -> Iterator[object]:
        yield session

    monkeypatch.setattr(
        promo_http.Settings,
        "from_env",
        classmethod(lambda cls: settings),
    )
    monkeypatch.setattr(promo_http, "_database_session", database)
    monkeypatch.setattr(
        promo_http,
        "authenticate_display_client",
        lambda *_args, **_kwargs: DisplayClientPrincipal(uuid.uuid4(), uuid.uuid4()),
    )

    response = route.endpoint(_request())

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.media_type == "application/json"
    assert response.body == (
        b'{"schema_version":1,"result_display_ms":111,"success_cooldown_ms":222}'
    )


@pytest.mark.parametrize(
    ("missing_variable", "missing_attribute"),
    (
        ("REALTIME_RESULT_DISPLAY_MS", "realtime_result_display_ms"),
        ("REALTIME_SUCCESS_COOLDOWN_MS", "realtime_success_cooldown_ms"),
    ),
)
def test_authenticated_config_route_returns_503_for_missing_binding(
    monkeypatch: pytest.MonkeyPatch,
    missing_variable: str,
    missing_attribute: str,
) -> None:
    app = create_app()
    route = _config_route(app)
    for name, value in {
        "DATABASE_URL": "postgresql+psycopg://unused",
        "S3_ENDPOINT_URL": "http://unused",
        "S3_ACCESS_KEY": "fixture-access",
        "S3_SECRET_KEY": "fixture-secret",
        "S3_BUCKET": "fixture-bucket",
        "POSTGRESQL_CAPACITY_VIEW_PATH": "/fixture/postgresql",
        "MINIO_CAPACITY_VIEW_PATH": "/fixture/minio",
        "REALTIME_RESULT_DISPLAY_MS": "111",
        "REALTIME_SUCCESS_COOLDOWN_MS": "222",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(missing_variable)

    settings = Settings.from_env()
    assert getattr(settings, missing_attribute) is None

    @contextmanager
    def database(_settings: object) -> Iterator[object]:
        yield object()

    monkeypatch.setattr(
        promo_http.Settings,
        "from_env",
        classmethod(lambda cls: settings),
    )
    monkeypatch.setattr(promo_http, "_database_session", database)
    monkeypatch.setattr(
        promo_http,
        "authenticate_display_client",
        lambda *_args, **_kwargs: DisplayClientPrincipal(uuid.uuid4(), uuid.uuid4()),
    )

    with pytest.raises(HTTPException) as error:
        route.endpoint(_request())

    assert error.value.status_code == 503
    assert error.value.headers == {"Cache-Control": "no-store"}


def test_invalid_config_returns_no_store_503_without_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    route = _config_route(app)
    settings = SimpleNamespace(
        database_url="postgresql+psycopg://unused",
        realtime_rate_limit=10,
        realtime_rate_window_seconds=60,
        realtime_result_display_ms=111,
        realtime_success_cooldown_ms=0,
    )

    @contextmanager
    def database(_settings: object) -> Iterator[object]:
        yield object()

    monkeypatch.setattr(
        promo_http.Settings,
        "from_env",
        classmethod(lambda cls: settings),
    )
    monkeypatch.setattr(promo_http, "_database_session", database)
    monkeypatch.setattr(
        promo_http,
        "authenticate_display_client",
        lambda *_args, **_kwargs: DisplayClientPrincipal(uuid.uuid4(), uuid.uuid4()),
    )

    with pytest.raises(HTTPException) as error:
        route.endpoint(_request())

    assert error.value.status_code == 503
    assert error.value.headers == {"Cache-Control": "no-store"}

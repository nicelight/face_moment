from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
import uuid

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

from face_moment.entrypoints.backend import create_app
from face_moment.promo import PromoMediaNotFoundError, derive_media_ref, resolve_teaser_media
from face_moment.promo import display_media
from face_moment.promo import http as promo_http
from face_moment.serving_control.display_client_auth import (
    DisplayClientPrincipal,
    DisplayClientRateLimitError,
    InvalidDisplayClientCredentials,
)


SECRET = "task076-disposable-secret"


class _ObjectStore:
    def __init__(self, payload: bytes = b"jpeg-preview") -> None:
        self.payload = payload
        self.keys: list[str] = []

    def read(self, *, key: str) -> bytes:
        self.keys.append(key)
        return self.payload


class _DatabaseSession:
    def __init__(self, row: object, preview_key: str | None) -> None:
        self.row = row
        self.preview_key = preview_key

    def scalars(self, _statement: object) -> list[object]:
        return [self.row]

    def scalar(self, _statement: object) -> str | None:
        return self.preview_key


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [(b"authorization", b"Bearer fixture-token")],
            "client": ("127.0.0.1", 1234),
            "scheme": "https",
            "server": ("central.example.test", 443),
        }
    )


def _media_route(app) -> APIRoute:
    route = next(
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path == "/api/promo/media/{media_ref}"
    )
    return route


def test_media_reference_is_opaque_and_authorized_projection_reads_private_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    spa_id = uuid.uuid4()
    row = SimpleNamespace(id=session_id, spa_id=spa_id, teaser_photo_ids=[photo_id])
    media_ref = derive_media_ref(session_id, photo_id, qr_ticket_secret=SECRET)
    store = _ObjectStore()
    projection_calls: list[dict[str, object]] = []

    def read_projection(*_args, **kwargs):
        projection_calls.append(kwargs)
        return SimpleNamespace(
            searchable=True,
            preview_object_key="private/task076/preview.jpg",
        )

    monkeypatch.setattr(
        display_media,
        "read_photo_processing_projection",
        read_projection,
    )
    body = resolve_teaser_media(
        _DatabaseSession(row, "private/task076/preview.jpg"),
        spa_id=spa_id,
        media_ref=media_ref,
        qr_ticket_secret=SECRET,
        object_store=store,  # type: ignore[arg-type]
    )

    assert len(media_ref) == 43
    assert str(photo_id) not in media_ref
    assert body == b"jpeg-preview"
    assert store.keys == ["private/task076/preview.jpg"]
    assert projection_calls == [{"photo_id": photo_id, "spa_id": spa_id}]

    with pytest.raises(PromoMediaNotFoundError):
        resolve_teaser_media(
            _DatabaseSession(row, "private/task076/preview.jpg"),
            spa_id=spa_id,
            media_ref="é" * 43,
            qr_ticket_secret=SECRET,
            object_store=store,  # type: ignore[arg-type]
        )

    with pytest.raises(PromoMediaNotFoundError):
        resolve_teaser_media(
            _DatabaseSession(row, "private/task076/preview.jpg"),
            spa_id=uuid.uuid4(),
            media_ref=derive_media_ref(
                uuid.uuid4(), photo_id, qr_ticket_secret=SECRET
            ),
            qr_ticket_secret=SECRET,
            object_store=store,  # type: ignore[arg-type]
        )


def test_missing_projection_or_object_is_404_owned_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    row = SimpleNamespace(id=session_id, spa_id=uuid.uuid4(), teaser_photo_ids=[photo_id])
    media_ref = derive_media_ref(session_id, photo_id, qr_ticket_secret=SECRET)
    monkeypatch.setattr(
        display_media,
        "read_photo_processing_projection",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(PromoMediaNotFoundError):
        resolve_teaser_media(
            _DatabaseSession(row, None),
            spa_id=row.spa_id,
            media_ref=media_ref,
            qr_ticket_secret=SECRET,
            object_store=_ObjectStore(),  # type: ignore[arg-type]
        )


def test_issued_media_survives_soft_delete_while_preview_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    spa_id = uuid.uuid4()
    row = SimpleNamespace(id=session_id, spa_id=spa_id, teaser_photo_ids=[photo_id])
    media_ref = derive_media_ref(session_id, photo_id, qr_ticket_secret=SECRET)
    store = _ObjectStore()
    monkeypatch.setattr(
        display_media,
        "read_photo_processing_projection",
        lambda *_args, **_kwargs: SimpleNamespace(
            searchable=False,
            photo_is_active=False,
            preview_object_key="private/task076/soft-deleted-preview.jpg",
        ),
    )

    assert resolve_teaser_media(
        _DatabaseSession(row, "private/task076/soft-deleted-preview.jpg"),
        spa_id=spa_id,
        media_ref=media_ref,
        qr_ticket_secret=SECRET,
        object_store=store,  # type: ignore[arg-type]
    ) == b"jpeg-preview"
    assert store.keys == ["private/task076/soft-deleted-preview.jpg"]


def test_object_store_not_found_is_404_but_technical_failure_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    spa_id = uuid.uuid4()
    row = SimpleNamespace(id=session_id, spa_id=spa_id, teaser_photo_ids=[photo_id])
    media_ref = derive_media_ref(session_id, photo_id, qr_ticket_secret=SECRET)
    monkeypatch.setattr(
        display_media,
        "read_photo_processing_projection",
        lambda *_args, **_kwargs: SimpleNamespace(
            searchable=True,
            preview_object_key="private/task076/missing.jpg",
        ),
    )

    class MissingStore:
        def read(self, *, key: str) -> bytes:
            raise ClientError(
                {
                    "Error": {"Code": "NoSuchKey", "Message": "missing"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "GetObject",
            )

    with pytest.raises(PromoMediaNotFoundError):
        resolve_teaser_media(
            _DatabaseSession(row, "private/task076/missing.jpg"),
            spa_id=spa_id,
            media_ref=media_ref,
            qr_ticket_secret=SECRET,
            object_store=MissingStore(),  # type: ignore[arg-type]
        )

    class MissingBucketStore:
        def read(self, *, key: str) -> bytes:
            raise ClientError(
                {
                    "Error": {"Code": "NoSuchBucket", "Message": "missing bucket"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "GetObject",
            )

    with pytest.raises(ClientError) as missing_bucket:
        resolve_teaser_media(
            _DatabaseSession(row, "private/task076/missing.jpg"),
            spa_id=spa_id,
            media_ref=media_ref,
            qr_ticket_secret=SECRET,
            object_store=MissingBucketStore(),  # type: ignore[arg-type]
        )
    assert missing_bucket.value.response["Error"]["Code"] == "NoSuchBucket"

    class FailingStore:
        def read(self, *, key: str) -> bytes:
            raise RuntimeError("synthetic object-store outage")

    with pytest.raises(RuntimeError, match="synthetic object-store outage"):
        resolve_teaser_media(
            _DatabaseSession(row, "private/task076/missing.jpg"),
            spa_id=spa_id,
            media_ref=media_ref,
            qr_ticket_secret=SECRET,
            object_store=FailingStore(),  # type: ignore[arg-type]
        )


def test_backend_registers_exact_media_route_with_auth_no_store_and_standard_failures(monkeypatch) -> None:
    app = create_app()
    route = _media_route(app)
    assert route.methods == {"GET"}

    class SettingsFixture:
        database_url = "postgresql+psycopg://unused"
        promo_qr_ticket_secret = SECRET
        realtime_rate_limit = 10
        realtime_rate_window_seconds = 60
        s3_endpoint_url = "http://unused"
        s3_access_key = "unused"
        s3_secret_key = "unused"
        s3_bucket = "unused"

    @contextmanager
    def database(_settings):
        yield object()

    monkeypatch.setattr(promo_http.Settings, "from_env", classmethod(lambda cls: SettingsFixture()))
    monkeypatch.setattr(promo_http, "_database_session", database)
    monkeypatch.setattr(
        promo_http,
        "authenticate_display_client",
        lambda *_args, **_kwargs: DisplayClientPrincipal(uuid.uuid4(), uuid.uuid4()),
    )
    monkeypatch.setattr(promo_http, "resolve_teaser_media", lambda *_args, **_kwargs: b"jpeg")
    app.state.promo_display_object_store = _ObjectStore()

    response = route.endpoint(_request("/api/promo/media/" + "r" * 43), "r" * 43)
    assert response.status_code == 200
    assert response.media_type == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"

    monkeypatch.setattr(
        promo_http,
        "authenticate_display_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(InvalidDisplayClientCredentials()),
    )
    with pytest.raises(HTTPException) as error:
        route.endpoint(_request("/api/promo/media/" + "r" * 43), "r" * 43)
    assert error.value.status_code == 401
    assert error.value.headers == {"Cache-Control": "no-store"}

    monkeypatch.setattr(
        promo_http,
        "authenticate_display_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(DisplayClientRateLimitError()),
    )
    with pytest.raises(HTTPException) as error:
        route.endpoint(_request("/api/promo/media/" + "r" * 43), "r" * 43)
    assert error.value.status_code == 429
    assert error.value.headers == {"Cache-Control": "no-store"}

    monkeypatch.setattr(
        promo_http,
        "authenticate_display_client",
        lambda *_args, **_kwargs: DisplayClientPrincipal(uuid.uuid4(), uuid.uuid4()),
    )
    for resolver_error, expected_status in (
        (PromoMediaNotFoundError("missing"), 404),
        (RuntimeError("technical failure"), 500),
    ):
        monkeypatch.setattr(
            promo_http,
            "resolve_teaser_media",
            lambda *_args, _error=resolver_error, **_kwargs: (_ for _ in ()).throw(_error),
        )
        with pytest.raises(HTTPException) as error:
            route.endpoint(_request("/api/promo/media/" + "r" * 43), "r" * 43)
        assert error.value.status_code == expected_status
        assert error.value.headers == {"Cache-Control": "no-store"}

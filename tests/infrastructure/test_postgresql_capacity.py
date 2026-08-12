from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import os

import pytest

from face_moment.infrastructure import capacity
from face_moment.infrastructure.capacity import observe_capacity
from face_moment.infrastructure.settings import Settings


def _settings(monkeypatch: pytest.MonkeyPatch, *, view_path: str) -> Settings:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://task033:task033@postgres/task033")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio.invalid")
    monkeypatch.setenv("S3_ACCESS_KEY", "task033-access")
    monkeypatch.setenv("S3_SECRET_KEY", "task033-secret")
    monkeypatch.setenv("S3_BUCKET", "task033-private")
    monkeypatch.setenv("POSTGRESQL_CAPACITY_VIEW_PATH", view_path)
    monkeypatch.setenv("POSTGRESQL_CAPACITY_LOW_THRESHOLD_BYTES", "4096")
    return Settings.from_env()


def _statvfs(*, available_bytes: int) -> os.statvfs_result:
    block_size = 1024
    return os.statvfs_result(
        (block_size, block_size, 100, 0, available_bytes // block_size, 0, 0, 0, 0, 0)
    )


def test_postgresql_capacity_reports_normal_low_and_unavailable_without_path_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "task033-forbidden-path-data-credential-marker"
    settings = _settings(monkeypatch, view_path=f"/run/{marker}")
    start = datetime.now(UTC)

    monkeypatch.setattr(capacity.os, "statvfs", lambda _: _statvfs(available_bytes=8192))
    normal = observe_capacity(
        settings.postgresql_capacity_view_path,
        low_threshold_bytes=settings.postgresql_capacity_low_threshold_bytes,
    )

    monkeypatch.setattr(capacity.os, "statvfs", lambda _: _statvfs(available_bytes=2048))
    low = observe_capacity(
        settings.postgresql_capacity_view_path,
        low_threshold_bytes=settings.postgresql_capacity_low_threshold_bytes,
    )

    def unavailable(_: str) -> os.statvfs_result:
        raise OSError(f"synthetic failure contains {marker}")

    monkeypatch.setattr(capacity.os, "statvfs", unavailable)
    unavailable_result = observe_capacity(
        settings.postgresql_capacity_view_path,
        low_threshold_bytes=settings.postgresql_capacity_low_threshold_bytes,
    )
    end = datetime.now(UTC)

    assert asdict(normal) == {
        "status": "ok",
        "available_bytes": 8192,
        "low_threshold_bytes": 4096,
        "observed_at": normal.observed_at,
        "error": None,
    }
    assert asdict(low) == {
        "status": "low",
        "available_bytes": 2048,
        "low_threshold_bytes": 4096,
        "observed_at": low.observed_at,
        "error": None,
    }
    assert asdict(unavailable_result) == {
        "status": "unavailable",
        "available_bytes": None,
        "low_threshold_bytes": 4096,
        "observed_at": unavailable_result.observed_at,
        "error": "capacity observation unavailable",
    }
    for observation in (normal, low, unavailable_result):
        assert start <= observation.observed_at <= end
        assert observation.observed_at.tzinfo is UTC
        assert marker not in str(asdict(observation))


def test_postgresql_capacity_configuration_requires_a_positive_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch, view_path="/run/task033-postgresql-view")

    assert settings.postgresql_capacity_view_path == "/run/task033-postgresql-view"
    assert settings.postgresql_capacity_low_threshold_bytes == 4096
    with pytest.raises(ValueError, match="positive"):
        observe_capacity(settings.postgresql_capacity_view_path, low_threshold_bytes=0)

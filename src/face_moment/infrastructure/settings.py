from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    dependency_wait_seconds: float
    staff_session_ttl_seconds: int
    staff_login_rate_limit: int
    staff_login_rate_window_seconds: int

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=_required("DATABASE_URL"),
            s3_endpoint_url=_required("S3_ENDPOINT_URL"),
            s3_access_key=_required("S3_ACCESS_KEY"),
            s3_secret_key=_required("S3_SECRET_KEY"),
            s3_bucket=_required("S3_BUCKET"),
            dependency_wait_seconds=float(
                os.environ.get("DEPENDENCY_WAIT_SECONDS", "60")
            ),
            staff_session_ttl_seconds=_positive_int(
                "STAFF_SESSION_TTL_SECONDS", "28800"
            ),
            staff_login_rate_limit=_positive_int("STAFF_LOGIN_RATE_LIMIT", "10"),
            staff_login_rate_window_seconds=_positive_int(
                "STAFF_LOGIN_RATE_WINDOW_SECONDS", "60"
            ),
        )


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required setting is missing: {name}")
    return value


def _positive_int(name: str, default: str) -> int:
    value = os.environ.get(name, default)
    try:
        parsed = int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer") from error
    if parsed <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return parsed

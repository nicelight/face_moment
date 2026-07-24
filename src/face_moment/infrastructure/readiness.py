from __future__ import annotations

import time
from collections.abc import Callable

from face_moment.infrastructure.database import assert_database_ready
from face_moment.infrastructure.object_store import assert_bucket_ready
from face_moment.infrastructure.settings import Settings


def wait_for_dependencies(
    settings: Settings,
    *,
    require_bucket: bool,
    check_interval: float = 1.0,
) -> None:
    deadline = time.monotonic() + settings.dependency_wait_seconds
    last_error: Exception | None = None
    checks: list[Callable[[], None]] = [
        lambda: assert_database_ready(settings.database_url)
    ]
    if require_bucket:
        checks.append(lambda: assert_bucket_ready(settings))

    while time.monotonic() < deadline:
        try:
            for check in checks:
                check()
            return
        except Exception as error:
            last_error = error
            time.sleep(check_interval)

    raise RuntimeError("Runtime dependencies did not become ready") from last_error


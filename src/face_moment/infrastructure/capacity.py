from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

CapacityStatus = Literal["ok", "low", "unavailable"]


@dataclass(frozen=True, slots=True)
class CapacityObservation:
    status: CapacityStatus
    available_bytes: int | None
    low_threshold_bytes: int
    observed_at: datetime
    error: str | None


def observe_capacity(
    view_path: str,
    *,
    low_threshold_bytes: int,
) -> CapacityObservation:
    """Read free capacity from one configured read-only filesystem view."""
    if low_threshold_bytes <= 0:
        raise ValueError("low_threshold_bytes must be positive")

    observed_at = datetime.now(UTC)
    try:
        filesystem = os.statvfs(view_path)
    except OSError:
        return CapacityObservation(
            status="unavailable",
            available_bytes=None,
            low_threshold_bytes=low_threshold_bytes,
            observed_at=observed_at,
            error="capacity observation unavailable",
        )

    available_bytes = filesystem.f_bavail * filesystem.f_frsize
    return CapacityObservation(
        status="low" if available_bytes < low_threshold_bytes else "ok",
        available_bytes=available_bytes,
        low_threshold_bytes=low_threshold_bytes,
        observed_at=observed_at,
        error=None,
    )

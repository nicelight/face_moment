from __future__ import annotations

from typing import Protocol


class FaceEngine(Protocol):
    @property
    def ready(self) -> bool:
        """Return whether warmup completed."""

    def warmup(self) -> None:
        """Prepare the engine before readiness may be reported."""


class FakeFaceEngine:
    """Deterministic Foundation seam; it never loads or runs a model."""

    def __init__(self) -> None:
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def warmup(self) -> None:
        self._ready = True


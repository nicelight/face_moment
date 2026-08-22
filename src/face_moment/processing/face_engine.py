from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from face_moment.processing.reference_query import (
        PreparedReferenceQuery,
        ReferenceQualityObservation,
    )


class FaceEngine(Protocol):
    @property
    def ready(self) -> bool:
        """Return whether warmup completed."""

    def warmup(self) -> None:
        """Prepare the engine before readiness may be reported."""

    def process_photo(self, photo: NDArray[np.uint8]) -> tuple[object, ...]:
        """Process one decoded Photo into this engine's native face results."""

    def inspect_reference_crop(
        self,
        crop: NDArray[np.uint8],
        quality_settings: Mapping[str, object],
    ) -> ReferenceQualityObservation:
        """Inspect one crop through this engine's admitted native path."""

    def prepare_reference_query(
        self, crop: NDArray[np.uint8]
    ) -> PreparedReferenceQuery | None:
        """Prepare one native embedding, or reject an unacceptable crop."""


class FakeFaceEngine:
    """Deterministic Foundation seam; it never loads or runs a model."""

    def __init__(self) -> None:
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def warmup(self) -> None:
        self._ready = True

    def process_photo(self, photo: NDArray[np.uint8]) -> tuple[object, ...]:
        raise RuntimeError("FakeFaceEngine cannot process a Photo")

    def inspect_reference_crop(
        self,
        crop: NDArray[np.uint8],
        quality_settings: Mapping[str, object],
    ) -> ReferenceQualityObservation:
        raise RuntimeError("FakeFaceEngine cannot inspect a reference crop")

    def prepare_reference_query(
        self, crop: NDArray[np.uint8]
    ) -> PreparedReferenceQuery | None:
        raise RuntimeError("FakeFaceEngine cannot prepare a reference query")

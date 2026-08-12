from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, cast

import cv2
import numpy as np
from numpy.typing import NDArray

_PREVIEW_KIND = "preview"
_THUMBNAIL_KIND = "thumbnail"


class PrivateDerivativeObjectStore(Protocol):
    """Private binary storage needed by the processing-owned derivative boundary."""

    def put(self, *, key: str, body: bytes) -> None: ...

    def read(self, *, key: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class DerivativeEncoding:
    """Positive JPEG bounds supplied by the deployment composition root."""

    maximum_edge: int
    jpeg_quality: int

    def __post_init__(self) -> None:
        if self.maximum_edge <= 0:
            raise ValueError("maximum_edge must be positive")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be in 1..100")


@dataclass(frozen=True, slots=True)
class DerivativeEncodingConfig:
    """Explicit encoding configuration for the only two required derivatives."""

    preview: DerivativeEncoding
    thumbnail: DerivativeEncoding


@dataclass(frozen=True, slots=True)
class PrivatePhotoDerivatives:
    """Stable private locations for one Photo/revision derivative pair."""

    preview_object_key: str
    thumbnail_object_key: str


class InvalidPrivatePhotoError(ValueError):
    """The private original cannot be decoded into a JPEG derivative."""


def derivative_object_key(
    *,
    photo_id: uuid.UUID,
    pipeline_revision_id: uuid.UUID,
    artifact_kind: str,
) -> str:
    """Return the private deterministic key for one allowed derivative kind."""

    if artifact_kind not in {_PREVIEW_KIND, _THUMBNAIL_KIND}:
        raise ValueError("artifact_kind must be preview or thumbnail")
    return f"private/derivatives/{photo_id}/{pipeline_revision_id}/{artifact_kind}.jpg"


class PrivatePhotoDerivativeCreator:
    """Create replaceable private preview and thumbnail bytes for one Photo."""

    def __init__(
        self,
        object_store: PrivateDerivativeObjectStore,
        *,
        encoding: DerivativeEncodingConfig,
    ) -> None:
        self._object_store = object_store
        self._encoding = encoding

    def create(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
        original_object_key: str,
    ) -> PrivatePhotoDerivatives:
        """Read the original once and replace the two deterministic private objects."""

        original = self._decode(self._object_store.read(key=original_object_key))
        preview_key = derivative_object_key(
            photo_id=photo_id,
            pipeline_revision_id=pipeline_revision_id,
            artifact_kind=_PREVIEW_KIND,
        )
        thumbnail_key = derivative_object_key(
            photo_id=photo_id,
            pipeline_revision_id=pipeline_revision_id,
            artifact_kind=_THUMBNAIL_KIND,
        )
        self._object_store.put(
            key=preview_key,
            body=self._encode(original, self._encoding.preview),
        )
        self._object_store.put(
            key=thumbnail_key,
            body=self._encode(original, self._encoding.thumbnail),
        )
        return PrivatePhotoDerivatives(
            preview_object_key=preview_key,
            thumbnail_object_key=thumbnail_key,
        )

    @staticmethod
    def _decode(original_bytes: bytes) -> NDArray[np.uint8]:
        decoded = cv2.imdecode(
            np.frombuffer(original_bytes, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if decoded is None:
            raise InvalidPrivatePhotoError("private original cannot be decoded")
        return cast(NDArray[np.uint8], decoded)

    @staticmethod
    def _encode(image: NDArray[np.uint8], encoding: DerivativeEncoding) -> bytes:
        bounded = _bound_image(image, maximum_edge=encoding.maximum_edge)
        encoded, output = cv2.imencode(
            ".jpg",
            bounded,
            [int(cv2.IMWRITE_JPEG_QUALITY), encoding.jpeg_quality],
        )
        if not encoded:
            raise InvalidPrivatePhotoError("private derivative JPEG encoding failed")
        return bytes(output)


def _bound_image(image: NDArray[np.uint8], *, maximum_edge: int) -> NDArray[np.uint8]:
    height, width = image.shape[:2]
    longest_edge = max(height, width)
    if longest_edge <= maximum_edge:
        return image
    if width >= height:
        size = (maximum_edge, max(1, height * maximum_edge // width))
    else:
        size = (max(1, width * maximum_edge // height), maximum_edge)
    return cast(
        NDArray[np.uint8],
        cv2.resize(image, size, interpolation=cv2.INTER_AREA),
    )

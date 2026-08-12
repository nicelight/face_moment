from __future__ import annotations

import hashlib
import uuid

import cv2
import numpy as np

from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket
from face_moment.infrastructure.settings import Settings
from face_moment.processing.derivatives import (
    DerivativeEncoding,
    DerivativeEncodingConfig,
    PrivatePhotoDerivativeCreator,
    derivative_object_key,
)


def _synthetic_jpeg() -> bytes:
    image = np.zeros((12, 20, 3), dtype=np.uint8)
    image[:, :10] = (12, 35, 220)
    image[:, 10:] = (210, 145, 25)
    encoded, payload = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 96])
    assert encoded
    return bytes(payload)


def _dimensions(payload: bytes) -> tuple[int, int]:
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    height, width = image.shape[:2]
    return width, height


def test_private_derivative_creation_is_deterministic_and_owner_cleaned() -> None:
    settings = Settings.from_env()
    ensure_bucket(settings)
    object_store = PrivateObjectStore(settings)
    marker = uuid.uuid4().hex
    photo_id = uuid.uuid4()
    pipeline_revision_id = uuid.uuid4()
    original_key = f"task021/{marker}/original.jpg"
    sentinel_key = f"task021/{marker}/sentinel.bin"
    derivative_prefix = f"private/derivatives/{photo_id}/{pipeline_revision_id}/"
    expected_keys = {
        derivative_object_key(
            photo_id=photo_id,
            pipeline_revision_id=pipeline_revision_id,
            artifact_kind="preview",
        ),
        derivative_object_key(
            photo_id=photo_id,
            pipeline_revision_id=pipeline_revision_id,
            artifact_kind="thumbnail",
        ),
    }
    original = _synthetic_jpeg()
    original_checksum = hashlib.sha256(original).digest()
    creator = PrivatePhotoDerivativeCreator(
        object_store,
        encoding=DerivativeEncodingConfig(
            preview=DerivativeEncoding(maximum_edge=8, jpeg_quality=65),
            thumbnail=DerivativeEncoding(maximum_edge=4, jpeg_quality=45),
        ),
    )

    try:
        object_store.put(key=original_key, body=original)
        object_store.put(key=sentinel_key, body=b"task021-synthetic-sentinel")

        first = creator.create(
            photo_id=photo_id,
            pipeline_revision_id=pipeline_revision_id,
            original_object_key=original_key,
        )
        first_checksums = {
            key: hashlib.sha256(object_store.read(key=key)).hexdigest()
            for key in expected_keys
        }
        second = creator.create(
            photo_id=photo_id,
            pipeline_revision_id=pipeline_revision_id,
            original_object_key=original_key,
        )
        second_checksums = {
            key: hashlib.sha256(object_store.read(key=key)).hexdigest()
            for key in expected_keys
        }

        assert first == second
        assert {first.preview_object_key, first.thumbnail_object_key} == expected_keys
        assert object_store.list_keys(prefix=derivative_prefix) == expected_keys
        assert first_checksums == second_checksums
        assert _dimensions(object_store.read(key=first.preview_object_key)) == (8, 4)
        assert _dimensions(object_store.read(key=first.thumbnail_object_key)) == (4, 2)
        assert hashlib.sha256(object_store.read(key=original_key)).digest() == original_checksum
        assert object_store.read(key=sentinel_key) == b"task021-synthetic-sentinel"
        assert all(not key.startswith("http") for key in expected_keys)
        assert all(marker not in key for key in expected_keys)
    finally:
        for key in expected_keys | {original_key, sentinel_key}:
            object_store.delete(key=key)

    assert object_store.list_keys(prefix=f"task021/{marker}/") == set()
    assert object_store.list_keys(prefix=derivative_prefix) == set()

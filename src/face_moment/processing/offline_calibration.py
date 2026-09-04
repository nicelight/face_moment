"""Processing-owned verified-input boundary for diagnostics Calibration runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
from typing import Protocol, cast
import uuid

import cv2
import numpy as np
from numpy.typing import NDArray
from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository


class CalibrationObjectStore(Protocol):
    def read(self, *, key: str) -> bytes: ...


class CalibrationPhotoAdapter(Protocol):
    @property
    def pipeline_revision_id(self) -> uuid.UUID: ...

    def process_photo(self, photo: NDArray[np.uint8]) -> Sequence[object]: ...


class CalibrationDatasetUnavailableError(LookupError):
    """A frozen original is missing or no longer matches its recorded digest."""


class CalibrationOfflineInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OfflineCalibrationResult:
    pipeline_revision_id: uuid.UUID
    photo_face_counts: tuple[tuple[uuid.UUID, int], ...]
    attempt_ids: tuple[uuid.UUID, ...]


def freeze_calibration_photos(
    session: Session, *, photo_ids: Sequence[uuid.UUID]
) -> tuple[uuid.UUID, tuple[dict[str, str], ...]]:
    """Resolve selected inventory identities through the processing boundary."""

    if not photo_ids or len(set(photo_ids)) != len(photo_ids):
        raise CalibrationOfflineInputError("photo selection must contain unique Photo UUIDs")
    photos: list[Photo] = []
    for photo_id in photo_ids:
        if not isinstance(photo_id, uuid.UUID):
            raise CalibrationOfflineInputError("photo selection contains a non-UUID")
        photo = session.get(Photo, photo_id)
        if photo is None:
            raise CalibrationOfflineInputError("selected Photo is missing")
        photos.append(photo)
    spa_ids = {photo.spa_id for photo in photos}
    if len(spa_ids) != 1:
        raise CalibrationOfflineInputError("selected Photos must belong to one SPA")
    return next(iter(spa_ids)), tuple(
        {"photo_id": str(photo.id), "sha256": photo.checksum_sha256.hex()}
        for photo in photos
    )


def evaluate_frozen_calibration(
    session: Session,
    *,
    photo_snapshot: Sequence[Mapping[str, object]],
    attempt_ids: Sequence[uuid.UUID],
    sface_revision_id: uuid.UUID,
    buffalo_revision_id: uuid.UUID,
    sface_adapter: CalibrationPhotoAdapter,
    buffalo_adapter: CalibrationPhotoAdapter,
    object_store: CalibrationObjectStore,
) -> tuple[OfflineCalibrationResult, OfflineCalibrationResult]:
    """Read each frozen original once and feed both direct adapters identically."""

    sface = PipelineRevisionRepository(session).resolve_eligible(sface_revision_id)
    buffalo = PipelineRevisionRepository(session).resolve_eligible(buffalo_revision_id)
    if sface.pipeline_code is not PipelineCode.OPENCV_SFACE or buffalo.pipeline_code is not PipelineCode.INSIGHTFACE_BUFFALO_M:
        raise CalibrationOfflineInputError("Calibration requires one SFace and one Buffalo M revision")
    if sface_adapter.pipeline_revision_id != sface.id or buffalo_adapter.pipeline_revision_id != buffalo.id:
        raise CalibrationOfflineInputError("configured Calibration adapter does not match frozen revision")
    if len(set(attempt_ids)) != len(attempt_ids) or any(not isinstance(value, uuid.UUID) for value in attempt_ids):
        raise CalibrationOfflineInputError("Attempt selection must contain unique UUIDs")

    sface_counts: list[tuple[uuid.UUID, int]] = []
    buffalo_counts: list[tuple[uuid.UUID, int]] = []
    for frozen_photo in photo_snapshot:
        photo_id, expected_digest = _frozen_photo_identity(frozen_photo)
        photo = session.get(Photo, photo_id)
        if photo is None or photo.checksum_sha256.hex() != expected_digest:
            raise CalibrationDatasetUnavailableError("dataset_unavailable")
        try:
            payload = object_store.read(key=photo.original_object_key)
        except (KeyError, OSError) as error:
            raise CalibrationDatasetUnavailableError("dataset_unavailable") from error
        if hashlib.sha256(payload).hexdigest() != expected_digest:
            raise CalibrationDatasetUnavailableError("dataset_unavailable")
        decoded = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            raise CalibrationDatasetUnavailableError("dataset_unavailable")
        image = cast(NDArray[np.uint8], decoded)
        sface_counts.append((photo_id, len(sface_adapter.process_photo(image))))
        buffalo_counts.append((photo_id, len(buffalo_adapter.process_photo(image))))
    selected_attempts = tuple(attempt_ids)
    return (
        OfflineCalibrationResult(sface.id, tuple(sface_counts), selected_attempts),
        OfflineCalibrationResult(buffalo.id, tuple(buffalo_counts), selected_attempts),
    )


def result_bundle_from_offline(
    *,
    sface: OfflineCalibrationResult,
    buffalo: OfflineCalibrationResult,
) -> dict[str, object]:
    """Return bounded, embedding-free separate revision outcomes for one run."""

    return {
        "pipeline_results": [
            _result_value(sface),
            _result_value(buffalo),
        ]
    }


def _result_value(result: OfflineCalibrationResult) -> dict[str, object]:
    return {
        "pipeline_revision_id": str(result.pipeline_revision_id),
        "attempt_ids": [str(attempt_id) for attempt_id in result.attempt_ids],
        "photos": [
            {"photo_id": str(photo_id), "face_count": face_count}
            for photo_id, face_count in result.photo_face_counts
        ],
    }


def _frozen_photo_identity(value: Mapping[str, object]) -> tuple[uuid.UUID, str]:
    photo_id = value.get("photo_id")
    digest = value.get("sha256")
    if not isinstance(photo_id, str) or not isinstance(digest, str):
        raise CalibrationDatasetUnavailableError("dataset_unavailable")
    try:
        parsed_id = uuid.UUID(photo_id)
    except ValueError as error:
        raise CalibrationDatasetUnavailableError("dataset_unavailable") from error
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise CalibrationDatasetUnavailableError("dataset_unavailable")
    return parsed_id, digest

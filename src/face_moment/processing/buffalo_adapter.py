from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import numpy as np
from insightface.app.common import Face
from insightface.model_zoo import get_model
from numpy.typing import NDArray

from face_moment.processing.revisions import EligiblePipelineRevision, PipelineCode
from face_moment.processing.reference_query import (
    PreparedReferenceQuery,
    ReferenceQualityObservation,
)
from face_moment.processing.terminal_publication import TerminalFace


class SCRFDDetector(Protocol):
    def detect(
        self,
        photo: NDArray[np.uint8],
        max_num: int = 0,
        metric: str = "default",
    ) -> tuple[NDArray[np.float32], NDArray[np.float32] | None]: ...


class BuffaloRecognizer(Protocol):
    def get(self, photo: NDArray[np.uint8], face: Face) -> NDArray[np.float32]: ...


class BuffaloAdapterError(ValueError):
    """The configured Buffalo M adapter cannot accept this Photo or revision."""


class BuffaloRevisionMismatchError(BuffaloAdapterError):
    pass


class BuffaloModelAssetMismatchError(BuffaloAdapterError):
    pass


class BuffaloEmbeddingDimensionMismatchError(BuffaloAdapterError):
    pass


class InvalidBuffaloPhotoError(BuffaloAdapterError, TypeError):
    pass


@dataclass(frozen=True, slots=True)
class BuffaloModelAssets:
    """Configured SCRFD/Buffalo M model paths and immutable identity."""

    detector_path: Path
    detector_id: str
    detector_version: str
    recognizer_path: Path
    recognizer_id: str
    recognizer_version: str
    preprocessing_version: str
    alignment_version: str
    normalization_version: str
    embedding_dimension: int

    def weights_sha256(self) -> str:
        digest = hashlib.sha256()
        for asset_path in (self.detector_path, self.recognizer_path):
            content = asset_path.read_bytes()
            digest.update(len(content).to_bytes(8, byteorder="big"))
            digest.update(content)
        return digest.hexdigest()

    def verify_revision(self, revision: EligiblePipelineRevision) -> None:
        if revision.pipeline_code is not PipelineCode.INSIGHTFACE_BUFFALO_M:
            raise BuffaloRevisionMismatchError(str(revision.pipeline_code))
        if revision.embedding_dimension != self.embedding_dimension:
            raise BuffaloEmbeddingDimensionMismatchError(
                f"expected {self.embedding_dimension}, got {revision.embedding_dimension}"
            )
        if (
            revision.detector_id != self.detector_id
            or revision.detector_version != self.detector_version
            or revision.recognizer_id != self.recognizer_id
            or revision.recognizer_version != self.recognizer_version
            or revision.preprocessing_version != self.preprocessing_version
            or revision.alignment_version != self.alignment_version
            or revision.normalization_version != self.normalization_version
            or revision.weights_sha256 != self.weights_sha256()
        ):
            raise BuffaloModelAssetMismatchError(str(revision.id))


@dataclass(frozen=True, slots=True)
class BuffaloPhotoFace:
    """One native InsightFace face and its normed Buffalo M embedding."""

    pipeline_revision_id: uuid.UUID
    native_face: Face
    embedding: NDArray[np.float32]


class BuffaloPhotoAdapter:
    """Direct configured SCRFD/Buffalo M implementation for one revision."""

    def __init__(
        self,
        *,
        revision: EligiblePipelineRevision,
        assets: BuffaloModelAssets,
        detector: SCRFDDetector,
        recognizer: BuffaloRecognizer,
    ) -> None:
        assets.verify_revision(revision)
        self._revision = revision
        self._assets = assets
        self._detector = detector
        self._recognizer = recognizer

    @classmethod
    def from_configured_assets(
        cls,
        *,
        revision: EligiblePipelineRevision,
        assets: BuffaloModelAssets,
    ) -> BuffaloPhotoAdapter:
        assets.verify_revision(revision)
        detector = get_model(str(assets.detector_path), download=False)
        recognizer = get_model(str(assets.recognizer_path), download=False)
        if (
            detector is None
            or getattr(detector, "taskname", None) != "detection"
            or recognizer is None
            or getattr(recognizer, "taskname", None) != "recognition"
        ):
            raise BuffaloModelAssetMismatchError(str(revision.id))
        return cls(
            revision=revision,
            assets=assets,
            detector=cast(SCRFDDetector, detector),
            recognizer=cast(BuffaloRecognizer, recognizer),
        )

    @property
    def ready(self) -> bool:
        return True

    @property
    def pipeline_revision_id(self) -> uuid.UUID:
        return self._revision.id

    def warmup(self) -> None:
        self._assets.verify_revision(self._revision)

    def process_photo(
        self, photo: NDArray[np.uint8]
    ) -> tuple[BuffaloPhotoFace, ...]:
        self._assets.verify_revision(self._revision)
        self._validate_photo(photo)

        native_detections, native_landmarks = self._detector.detect(photo)
        if native_detections.size == 0 or native_landmarks is None:
            return ()

        faces: list[BuffaloPhotoFace] = []
        for index, native_detection in enumerate(native_detections):
            native_face = Face(
                bbox=native_detection[:4],
                kps=native_landmarks[index],
                det_score=native_detection[4],
            )
            self._recognizer.get(photo, native_face)
            native_embedding = native_face.normed_embedding
            if native_embedding is None:
                raise BuffaloEmbeddingDimensionMismatchError("missing native embedding")
            embedding = np.asarray(native_embedding, dtype=np.float32).reshape(-1)
            if embedding.size != self._revision.embedding_dimension:
                raise BuffaloEmbeddingDimensionMismatchError(
                    f"expected {self._revision.embedding_dimension}, got {embedding.size}"
                )
            if not np.isfinite(embedding).all():
                raise BuffaloEmbeddingDimensionMismatchError(
                    "native normed_embedding must be finite"
                )
            faces.append(
                BuffaloPhotoFace(
                    pipeline_revision_id=self._revision.id,
                    native_face=native_face,
                    embedding=embedding,
                )
            )
        return tuple(faces)

    def inspect_reference_crop(
        self,
        crop: NDArray[np.uint8],
        quality_settings: Mapping[str, object],
    ) -> ReferenceQualityObservation:
        del quality_settings
        faces = self.process_photo(crop)
        if not faces:
            return ReferenceQualityObservation(
                reference_quality_score=0.0,
                native_face_count=0,
                gate_observations=(),
            )
        score = max(float(face.native_face.det_score) for face in faces)
        return ReferenceQualityObservation(
            reference_quality_score=score,
            native_face_count=len(faces),
            gate_observations=(("native_detection_confidence", score),),
        )

    def prepare_reference_query(
        self, crop: NDArray[np.uint8]
    ) -> PreparedReferenceQuery | None:
        faces = self.process_photo(crop)
        if not faces:
            return None
        face = max(faces, key=lambda item: float(item.native_face.det_score))
        return PreparedReferenceQuery(
            pipeline_revision_id=self._revision.id,
            embedding=face.embedding,
        )

    def process_for_terminal(
        self, photo: NDArray[np.uint8]
    ) -> tuple[TerminalFace, ...]:
        """Adapt this revision's native results for terminal publication."""

        return tuple(
            TerminalFace(
                face_index=index,
                bbox_x=float(face.native_face.bbox[0]),
                bbox_y=float(face.native_face.bbox[1]),
                bbox_w=float(face.native_face.bbox[2] - face.native_face.bbox[0]),
                bbox_h=float(face.native_face.bbox[3] - face.native_face.bbox[1]),
                landmarks_json=[
                    [float(x), float(y)] for x, y in face.native_face.kps
                ],
                detection_confidence=float(face.native_face.det_score),
                embedding=tuple(float(value) for value in face.embedding),
            )
            for index, face in enumerate(self.process_photo(photo))
        )

    @staticmethod
    def _validate_photo(photo: NDArray[np.uint8]) -> None:
        if (
            not isinstance(photo, np.ndarray)
            or photo.dtype != np.uint8
            or photo.ndim != 3
            or photo.shape[2] != 3
        ):
            raise InvalidBuffaloPhotoError("Buffalo M requires a decoded BGR Photo")

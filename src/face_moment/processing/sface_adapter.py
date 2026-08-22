from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from face_moment.processing.revisions import EligiblePipelineRevision, PipelineCode
from face_moment.processing.reference_query import (
    PreparedReferenceQuery,
    ReferenceQualityObservation,
)
from face_moment.processing.terminal_publication import TerminalFace


class YuNetDetector(Protocol):
    def setInputSize(self, size: tuple[int, int]) -> None: ...

    def detect(
        self, photo: NDArray[np.uint8]
    ) -> tuple[bool, NDArray[np.float32] | None]: ...


class SFaceRecognizer(Protocol):
    def alignCrop(
        self, photo: NDArray[np.uint8], detection: NDArray[np.float32]
    ) -> NDArray[np.uint8]: ...

    def feature(self, aligned: NDArray[np.uint8]) -> NDArray[np.float32]: ...


class SFaceAdapterError(ValueError):
    """The configured SFace adapter cannot accept this Photo or revision."""


class SFaceRevisionMismatchError(SFaceAdapterError):
    pass


class ModelAssetMismatchError(SFaceAdapterError):
    pass


class EmbeddingDimensionMismatchError(SFaceAdapterError):
    pass


class InvalidSFacePhotoError(SFaceAdapterError, TypeError):
    pass


@dataclass(frozen=True, slots=True)
class SFaceModelAssets:
    """Configured YuNet/SFace model paths and their immutable identity."""

    detector_path: Path
    detector_id: str
    detector_version: str
    recognizer_path: Path
    recognizer_id: str
    recognizer_version: str
    preprocessing_version: str
    alignment_version: str
    normalization_version: str

    def weights_sha256(self) -> str:
        digest = hashlib.sha256()
        for asset_path in (self.detector_path, self.recognizer_path):
            content = asset_path.read_bytes()
            digest.update(len(content).to_bytes(8, byteorder="big"))
            digest.update(content)
        return digest.hexdigest()

    def verify_revision(self, revision: EligiblePipelineRevision) -> None:
        if revision.pipeline_code is not PipelineCode.OPENCV_SFACE:
            raise SFaceRevisionMismatchError(str(revision.pipeline_code))
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
            raise ModelAssetMismatchError(str(revision.id))


@dataclass(frozen=True, slots=True)
class SFacePhotoFace:
    """One native YuNet detection and normalized SFace embedding."""

    pipeline_revision_id: uuid.UUID
    native_detection: NDArray[np.float32]
    embedding: NDArray[np.float32]


class SFacePhotoAdapter:
    """Direct OpenCV YuNet/FaceRecognizerSF implementation for one revision."""

    def __init__(
        self,
        *,
        revision: EligiblePipelineRevision,
        assets: SFaceModelAssets,
        detector: YuNetDetector,
        recognizer: SFaceRecognizer,
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
        assets: SFaceModelAssets,
    ) -> SFacePhotoAdapter:
        assets.verify_revision(revision)
        detector = cast(
            YuNetDetector,
            cv2.FaceDetectorYN.create(
                str(assets.detector_path),
                "",
                (320, 320),
            ),
        )
        recognizer = cast(
            SFaceRecognizer,
            cv2.FaceRecognizerSF.create(str(assets.recognizer_path), ""),
        )
        return cls(
            revision=revision,
            assets=assets,
            detector=detector,
            recognizer=recognizer,
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
    ) -> tuple[SFacePhotoFace, ...]:
        self._assets.verify_revision(self._revision)
        self._validate_photo(photo)

        height, width, _ = photo.shape
        self._detector.setInputSize((width, height))
        detected, native_detections = self._detector.detect(photo)
        if not detected or native_detections is None:
            return ()

        faces: list[SFacePhotoFace] = []
        for native_detection in native_detections:
            aligned = self._recognizer.alignCrop(photo, native_detection)
            feature = self._recognizer.feature(aligned)
            embedding = np.asarray(feature, dtype=np.float32).reshape(-1)
            if embedding.size != self._revision.embedding_dimension:
                raise EmbeddingDimensionMismatchError(
                    f"expected {self._revision.embedding_dimension}, got {embedding.size}"
                )
            norm = float(np.linalg.norm(embedding))
            if not np.isfinite(embedding).all() or not np.isfinite(norm) or norm == 0:
                raise EmbeddingDimensionMismatchError("embedding must be finite and non-zero")
            faces.append(
                SFacePhotoFace(
                    pipeline_revision_id=self._revision.id,
                    native_detection=native_detection,
                    embedding=embedding / norm,
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
        score = max(self._detection_confidence(face.native_detection) for face in faces)
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
        face = max(
            faces,
            key=lambda item: self._detection_confidence(item.native_detection),
        )
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
                bbox_x=float(face.native_detection[0]),
                bbox_y=float(face.native_detection[1]),
                bbox_w=float(face.native_detection[2]),
                bbox_h=float(face.native_detection[3]),
                landmarks_json=[
                    [
                        float(face.native_detection[4 + landmark * 2]),
                        float(face.native_detection[5 + landmark * 2]),
                    ]
                    for landmark in range(5)
                ],
                detection_confidence=float(face.native_detection[14]),
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
            raise InvalidSFacePhotoError("SFace requires a decoded BGR Photo")

    @staticmethod
    def _detection_confidence(detection: NDArray[np.float32]) -> float:
        if detection.size <= 14:
            raise InvalidSFacePhotoError("SFace detection lacks confidence")
        return float(detection[14])

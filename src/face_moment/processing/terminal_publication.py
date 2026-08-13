from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from numbers import Real

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.derivatives import PrivatePhotoDerivatives
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace, ProcessingRuntimeStatus
from face_moment.processing.revisions import PipelineRevision

_PROCESSING = "processing"
_READY = "ready"
_NO_FACES = "no_faces"
_TERMINAL_STATES = frozenset({_READY, _NO_FACES, "failed"})
_PHOTO_PROCESSING = "photo_processing"
_IDLE = "idle"
_LANDMARK_COUNT = 5


@dataclass(frozen=True, slots=True)
class TerminalFace:
    """One complete adapter-owned face result ready for terminal persistence."""

    face_index: int
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    landmarks_json: object
    detection_confidence: float
    embedding: tuple[float, ...]
    quality_score: float | None = None
    blur_score: float | None = None
    brightness_score: float | None = None
    pose_yaw: float | None = None
    pose_pitch: float | None = None
    pose_roll: float | None = None


class TerminalPublicationRepository:
    """Processing-owned atomic terminal state and complete face-set publication."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def publish_ready(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
        faces: tuple[TerminalFace, ...],
        derivatives: PrivatePhotoDerivatives,
    ) -> PhotoPipelineState:
        """Replace the complete face set and publish one ready result atomically."""

        state = self._locked_state(
            photo_id=photo_id, pipeline_revision_id=pipeline_revision_id
        )
        if state.status in _TERMINAL_STATES:
            return state
        self._require_processing(state)
        if not faces:
            raise ValueError("ready publication requires at least one face")

        revision = self._session.get(PipelineRevision, pipeline_revision_id)
        if revision is None or revision.validated_at is None:
            raise LookupError("pipeline revision is not eligible")
        photo = self._session.get(Photo, photo_id)
        if photo is None:
            raise LookupError("photo is missing")
        self._validate_faces(
            faces,
            embedding_dimension=revision.embedding_dimension,
            photo_width=photo.width,
            photo_height=photo.height,
        )

        self._session.execute(
            delete(PhotoFace).where(
                PhotoFace.photo_id == photo_id,
                PhotoFace.pipeline_revision_id == pipeline_revision_id,
            )
        )
        self._session.add_all(
            [
                PhotoFace(
                    photo_id=photo_id,
                    pipeline_revision_id=pipeline_revision_id,
                    face_index=face.face_index,
                    bbox_x=face.bbox_x,
                    bbox_y=face.bbox_y,
                    bbox_w=face.bbox_w,
                    bbox_h=face.bbox_h,
                    landmarks_json=face.landmarks_json,
                    detection_confidence=face.detection_confidence,
                    quality_score=face.quality_score,
                    blur_score=face.blur_score,
                    brightness_score=face.brightness_score,
                    pose_yaw=face.pose_yaw,
                    pose_pitch=face.pose_pitch,
                    pose_roll=face.pose_roll,
                    embedding=list(face.embedding),
                )
                for face in sorted(faces, key=lambda item: item.face_index)
            ]
        )
        now = datetime.now(timezone.utc)
        state.status = _READY
        state.status_changed_at = now
        state.searchable_at = now
        state.last_error = None
        state.preview_object_key = derivatives.preview_object_key
        state.thumbnail_object_key = derivatives.thumbnail_object_key
        self._finish_processing_operation()
        self._session.flush()
        self._session.refresh(state)
        return state

    def publish_no_faces(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> PhotoPipelineState:
        """Publish a successful no-face terminal result without derivatives."""

        state = self._locked_state(
            photo_id=photo_id, pipeline_revision_id=pipeline_revision_id
        )
        if state.status in _TERMINAL_STATES:
            return state
        self._require_processing(state)
        self._session.execute(
            delete(PhotoFace).where(
                PhotoFace.photo_id == photo_id,
                PhotoFace.pipeline_revision_id == pipeline_revision_id,
            )
        )
        state.status = _NO_FACES
        state.status_changed_at = datetime.now(timezone.utc)
        state.searchable_at = None
        state.last_error = None
        state.preview_object_key = None
        state.thumbnail_object_key = None
        self._finish_processing_operation()
        self._session.flush()
        self._session.refresh(state)
        return state

    def _locked_state(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> PhotoPipelineState:
        state = self._session.scalar(
            select(PhotoPipelineState)
            .where(
                PhotoPipelineState.photo_id == photo_id,
                PhotoPipelineState.pipeline_revision_id == pipeline_revision_id,
            )
            .with_for_update()
        )
        if state is None:
            raise LookupError("processing state is missing")
        return state

    @staticmethod
    def _require_processing(state: PhotoPipelineState) -> None:
        if state.status != _PROCESSING:
            raise LookupError("processing claim is not active")

    @staticmethod
    def _validate_faces(
        faces: tuple[TerminalFace, ...],
        *,
        embedding_dimension: int,
        photo_width: int,
        photo_height: int,
    ) -> None:
        face_indexes = {face.face_index for face in faces}
        if len(face_indexes) != len(faces) or min(face_indexes) < 0:
            raise ValueError("face indexes must be unique non-negative values")
        for face in faces:
            if len(face.embedding) != embedding_dimension:
                raise ValueError("embedding dimension does not match pipeline revision")
            embedding_norm = math.sqrt(sum(value * value for value in face.embedding))
            if not math.isclose(embedding_norm, 1.0, rel_tol=1e-5, abs_tol=1e-5):
                raise ValueError("embedding must be normalized")
            required_values = (
                face.bbox_x,
                face.bbox_y,
                face.bbox_w,
                face.bbox_h,
                face.detection_confidence,
                *face.embedding,
            )
            optional_values = (
                face.quality_score,
                face.blur_score,
                face.brightness_score,
                face.pose_yaw,
                face.pose_pitch,
                face.pose_roll,
            )
            if not all(math.isfinite(value) for value in required_values):
                raise ValueError("face values must be finite")
            if not all(
                value is None or math.isfinite(value) for value in optional_values
            ):
                raise ValueError("optional face values must be finite")
            if face.bbox_w <= 0 or face.bbox_h <= 0:
                raise ValueError("face bounds must be positive")
            if (
                face.bbox_x < 0
                or face.bbox_y < 0
                or face.bbox_x + face.bbox_w > photo_width
                or face.bbox_y + face.bbox_h > photo_height
            ):
                raise ValueError("face bounds must fit within the photo")
            TerminalPublicationRepository._validate_landmarks(face.landmarks_json)

    @staticmethod
    def _validate_landmarks(landmarks_json: object) -> None:
        if (
            not isinstance(landmarks_json, (list, tuple))
            or len(landmarks_json) != _LANDMARK_COUNT
        ):
            raise ValueError("face landmarks must contain five coordinate pairs")
        for landmark in landmarks_json:
            if not isinstance(landmark, (list, tuple)) or len(landmark) != 2:
                raise ValueError("face landmarks must contain five coordinate pairs")
            if not all(
                isinstance(value, Real)
                and not isinstance(value, bool)
                and math.isfinite(value)
                for value in landmark
            ):
                raise ValueError("face landmarks must be finite")

    def _finish_processing_operation(self) -> None:
        runtime = self._session.scalar(
            select(ProcessingRuntimeStatus)
            .where(ProcessingRuntimeStatus.singleton_id == 1)
            .with_for_update()
        )
        if runtime is None:
            raise RuntimeError("processing runtime status is missing")
        if runtime.current_operation != _PHOTO_PROCESSING:
            raise LookupError("processing runtime operation is not active")
        runtime.current_operation = _IDLE
        runtime.operation_started_at = None

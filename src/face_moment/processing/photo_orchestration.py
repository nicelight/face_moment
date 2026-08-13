from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Protocol, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from sqlalchemy.orm import Session

from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.derivatives import (
    PrivateDerivativeObjectStore,
    PrivatePhotoDerivativeCreator,
    PrivatePhotoDerivatives,
)
from face_moment.processing.revisions import (
    EligiblePipelineRevision,
    PipelineCode,
    PipelineRevisionRepository,
)
from face_moment.processing.terminal_publication import (
    TerminalFace,
    TerminalPublicationRepository,
)
from face_moment.processing.worker_claims import WorkerClaimRepository


class TerminalPhotoAdapter(Protocol):
    """Exact-revision adapter boundary returning terminal-ready faces."""

    @property
    def pipeline_revision_id(self) -> uuid.UUID: ...

    def process_for_terminal(
        self, photo: NDArray[np.uint8]
    ) -> tuple[TerminalFace, ...]: ...


class PhotoProcessingOrchestrator:
    """Compose one already-claimed Photo through existing processing owners."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        object_store: PrivateDerivativeObjectStore,
        sface_adapter: TerminalPhotoAdapter,
        buffalo_adapter: TerminalPhotoAdapter,
        derivative_creator: PrivatePhotoDerivativeCreator,
    ) -> None:
        self._session_factory = session_factory
        self._object_store = object_store
        self._sface_adapter = sface_adapter
        self._buffalo_adapter = buffalo_adapter
        self._derivative_creator = derivative_creator

    def process_claimed(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> str:
        """Run one claimed Photo without owning claim or terminal policy."""

        try:
            original_object_key, revision, decoded_photo = self._load_inputs(
                photo_id=photo_id,
                pipeline_revision_id=pipeline_revision_id,
            )
            faces = self._adapter_for(revision).process_for_terminal(decoded_photo)
            if not faces:
                return self._publish_no_faces(
                    photo_id=photo_id,
                    pipeline_revision_id=pipeline_revision_id,
                )
            derivatives = self._derivative_creator.create(
                photo_id=photo_id,
                pipeline_revision_id=pipeline_revision_id,
                original_object_key=original_object_key,
            )
            return self._publish_ready(
                photo_id=photo_id,
                pipeline_revision_id=pipeline_revision_id,
                faces=faces,
                derivatives=derivatives,
            )
        except Exception:
            return self._record_failure(
                photo_id=photo_id,
                pipeline_revision_id=pipeline_revision_id,
            )

    def _load_inputs(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> tuple[str, EligiblePipelineRevision, NDArray[np.uint8]]:
        with self._session_factory() as session:
            photo = session.get(Photo, photo_id)
            if photo is None:
                raise LookupError("claimed Photo is missing")
            revision = PipelineRevisionRepository(session).resolve_eligible(
                pipeline_revision_id
            )
            original_object_key = photo.original_object_key

        decoded = cv2.imdecode(
            np.frombuffer(
                self._object_store.read(key=original_object_key), dtype=np.uint8
            ),
            cv2.IMREAD_COLOR,
        )
        if decoded is None:
            raise ValueError("private original cannot be decoded")
        return original_object_key, revision, cast(NDArray[np.uint8], decoded)

    def _adapter_for(
        self, revision: EligiblePipelineRevision
    ) -> TerminalPhotoAdapter:
        if revision.pipeline_code is PipelineCode.OPENCV_SFACE:
            adapter = self._sface_adapter
        elif revision.pipeline_code is PipelineCode.INSIGHTFACE_BUFFALO_M:
            adapter = self._buffalo_adapter
        else:
            raise ValueError(f"unsupported pipeline code: {revision.pipeline_code}")
        if adapter.pipeline_revision_id != revision.id:
            raise LookupError("configured adapter does not match claimed revision")
        return adapter

    def _publish_ready(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
        faces: tuple[TerminalFace, ...],
        derivatives: PrivatePhotoDerivatives,
    ) -> str:
        with self._session_factory() as session:
            state = TerminalPublicationRepository(session).publish_ready(
                photo_id=photo_id,
                pipeline_revision_id=pipeline_revision_id,
                faces=faces,
                derivatives=derivatives,
            )
            session.commit()
            return state.status

    def _publish_no_faces(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> str:
        with self._session_factory() as session:
            state = TerminalPublicationRepository(session).publish_no_faces(
                photo_id=photo_id,
                pipeline_revision_id=pipeline_revision_id,
            )
            session.commit()
            return state.status

    def _record_failure(
        self,
        *,
        photo_id: uuid.UUID,
        pipeline_revision_id: uuid.UUID,
    ) -> str:
        with self._session_factory() as session:
            state = WorkerClaimRepository(session).record_failure(
                photo_id=photo_id,
                pipeline_revision_id=pipeline_revision_id,
            )
            session.commit()
            return state.status

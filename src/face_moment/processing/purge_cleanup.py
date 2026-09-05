from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace


class PrivateDerivativeDeletion(Protocol):
    """The private object deletion capability used only by purge cleanup."""

    def delete(self, *, key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class ProcessingPurgeCleanupResult:
    """The processing-owned work staged by one inventory purge step."""

    photo_id: uuid.UUID
    derivative_object_keys: tuple[str, ...]
    deleted_face_count: int
    deleted_state_count: int


class ProcessingPurgeCleanup:
    """Remove processing-owned derivatives and rows for one supplied Photo.

    The inventory orchestrator authorizes the inactive Photo and owns the
    surrounding transaction. This boundary deliberately never loads or writes
    inventory-owned Photo state, purge progress, worker state, or foreign rows.
    """

    def __init__(self, session: Session, object_store: PrivateDerivativeDeletion) -> None:
        self._session = session
        self._object_store = object_store

    def cleanup(self, *, photo_id: uuid.UUID) -> ProcessingPurgeCleanupResult:
        """Delete private derivatives and stage all owned row removals.

        Object deletion precedes the caller-owned database commit. If that
        commit is interrupted, the retained state rows make the same idempotent
        object deletes and row cleanup safely repeatable.
        """

        derivative_keys = self._derivative_object_keys(photo_id=photo_id)
        for key in derivative_keys:
            self._object_store.delete(key=key)

        deleted_face_count = self._session.execute(
            delete(PhotoFace).where(PhotoFace.photo_id == photo_id)
        ).rowcount
        deleted_state_count = self._session.execute(
            delete(PhotoPipelineState).where(PhotoPipelineState.photo_id == photo_id)
        ).rowcount
        self._session.flush()
        return ProcessingPurgeCleanupResult(
            photo_id=photo_id,
            derivative_object_keys=derivative_keys,
            deleted_face_count=deleted_face_count,
            deleted_state_count=deleted_state_count,
        )

    def _derivative_object_keys(self, *, photo_id: uuid.UUID) -> tuple[str, ...]:
        rows = self._session.execute(
            select(
                PhotoPipelineState.preview_object_key,
                PhotoPipelineState.thumbnail_object_key,
            ).where(PhotoPipelineState.photo_id == photo_id)
        )
        return tuple(
            sorted(
                {
                    key
                    for preview_key, thumbnail_key in rows
                    for key in (preview_key, thumbnail_key)
                    if key is not None
                }
            )
        )

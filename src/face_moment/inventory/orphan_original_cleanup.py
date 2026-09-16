"""Operator-triggered cleanup of unowned files in known private-store namespaces."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
import uuid

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.diagnostics.evidence import referenced_capture_object_keys
from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.initial_pending import owned_derivative_identities
from face_moment.promo.advertising import owned_advertising_object_keys


_ADMISSION_LOCK = 62_401_876_320
_CLEANUP_LOCK = 62_401_876_321


class OriginalCleanupRunningError(RuntimeError):
    """Another original cleanup is already running."""


class OriginalCleanupUploadPausedError(RuntimeError):
    """A cleanup is currently excluding new original uploads."""


@dataclass(frozen=True)
class OriginalCleanupResult:
    scanned: int
    deleted: int


@contextmanager
def admission_storage_guard(session: Session) -> Iterator[None]:
    """Keep a shared lock from before a Photo/ad upload through its DB commit."""

    bind = session.get_bind()
    if not isinstance(bind, Engine):
        raise RuntimeError("photo admission requires an engine-bound session")
    with bind.connect() as connection, connection.begin():
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_xact_lock_shared(:key)"),
            {"key": _ADMISSION_LOCK},
        )
        if not acquired:
            raise OriginalCleanupUploadPausedError
        yield


def cleanup_orphan_originals(
    session: Session, object_store: PrivateObjectStore
) -> OriginalCleanupResult:
    """Delete provably unowned objects while Photo/ad uploads are excluded."""

    scanned = 0
    deleted = 0
    with session.begin():
        acquired = session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": _CLEANUP_LOCK},
        )
        if not acquired:
            raise OriginalCleanupRunningError
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADMISSION_LOCK})
        for keys in object_store.list_key_pages(prefix="candidates/"):
            if not keys:
                continue
            candidate_references = set(
                session.scalars(
                    select(Photo.original_object_key).where(Photo.original_object_key.in_(keys))
                )
            )
            for key in keys:
                scanned += 1
                if key not in candidate_references:
                    object_store.delete(key=key)
                    deleted += 1

        for keys in object_store.list_key_pages(prefix="advertising/"):
            scanned += len(keys)
            advertising_identities = {key: _advertising_identity(key) for key in keys}
            media_ids = [identity[1] for identity in advertising_identities.values() if identity is not None]
            advertising_references = owned_advertising_object_keys(session, media_ids)
            for key, identity in advertising_identities.items():
                if identity is not None and key not in advertising_references:
                    object_store.delete(key=key)
                    deleted += 1

        for keys in object_store.list_key_pages(prefix="private/derivatives/"):
            scanned += len(keys)
            derivative_identities = {key: _derivative_identity(key) for key in keys}
            photo_ids = [identity[0] for identity in derivative_identities.values() if identity is not None]
            owned_pairs = owned_derivative_identities(session, photo_ids)
            for key, identity in derivative_identities.items():
                if identity is not None and identity not in owned_pairs:
                    object_store.delete(key=key)
                    deleted += 1

        for keys in object_store.list_key_pages(prefix="diagnostics/captures/"):
            scanned += len(keys)
            capture_attempts = {key: _capture_attempt_id(key) for key in keys}
            attempt_ids = [attempt_id for attempt_id in capture_attempts.values() if attempt_id is not None]
            diagnostic_references = referenced_capture_object_keys(session, attempt_ids)
            for key, attempt_id in capture_attempts.items():
                if attempt_id is not None and key not in diagnostic_references:
                    object_store.delete(key=key)
                    deleted += 1
    return OriginalCleanupResult(scanned=scanned, deleted=deleted)


def _advertising_identity(key: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    parts = key.split("/")
    if len(parts) != 3 or parts[0] != "advertising":
        return None
    try:
        spa_id, media_id = uuid.UUID(parts[1]), uuid.UUID(parts[2])
    except ValueError:
        return None
    return (spa_id, media_id) if key == f"advertising/{spa_id}/{media_id}" else None


def _derivative_identity(key: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    parts = key.split("/")
    if len(parts) != 5 or parts[:2] != ["private", "derivatives"]:
        return None
    if parts[4] not in {"preview.jpg", "thumbnail.jpg"}:
        return None
    try:
        photo_id, revision_id = uuid.UUID(parts[2]), uuid.UUID(parts[3])
    except ValueError:
        return None
    return (photo_id, revision_id) if key == f"private/derivatives/{photo_id}/{revision_id}/{parts[4]}" else None


def _capture_attempt_id(key: str) -> uuid.UUID | None:
    parts = key.split("/")
    if len(parts) != 4 or parts[:2] != ["diagnostics", "captures"]:
        return None
    index = parts[3].removesuffix(".jpg")
    if not parts[3].endswith(".jpg") or not index.isascii() or not index.isdecimal():
        return None
    try:
        attempt_id = uuid.UUID(parts[2])
    except ValueError:
        return None
    return attempt_id if key == f"diagnostics/captures/{attempt_id}/{int(index)}.jpg" else None

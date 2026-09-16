"""Operator-triggered cleanup of original candidates without a Photo row."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.inventory.photo_persistence import Photo


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
    """Keep a shared database lock from before MinIO put through Photo commit."""

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
    """Delete only unreferenced candidate originals while admissions are excluded."""

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
            referenced = set(
                session.scalars(
                    select(Photo.original_object_key).where(Photo.original_object_key.in_(keys))
                )
            )
            for key in keys:
                scanned += 1
                if key not in referenced:
                    object_store.delete(key=key)
                    deleted += 1
    return OriginalCleanupResult(scanned=scanned, deleted=deleted)

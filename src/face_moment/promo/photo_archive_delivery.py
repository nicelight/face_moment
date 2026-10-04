"""Promo-owned bearer authorization and ready-link signing.

@docs .memory-bank/domains/photo-orders.md#исполнение-и-выдача
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import uuid

from sqlalchemy.orm import Session

from face_moment.promo.photo_orders import PhotoOrder, PhotoOrderRepository


class ArchiveUnavailableError(ValueError):
    pass


class ArchiveExpiredError(ValueError):
    pass


def _signature(*, order_id: uuid.UUID, ready_at: datetime, secret: str) -> str:
    if not secret:
        raise ValueError('Archive signing secret is not configured')
    message = f'{order_id}\n{ready_at.astimezone(timezone.utc).isoformat(timespec="microseconds")}'
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def archive_download_url(order: PhotoOrder, *, secret: str, now: datetime) -> str | None:
    """Order-status consumer uses this only after its owner-profile check."""
    if (order.archive_status != 'ready' or order.ready_at is None or
            order.archive_object_key is None or
            not (order.total_kopecks == 0 or order.payment_status == 'succeeded') or
            now >= order.ready_at + timedelta(days=3)):
        return None
    token = _signature(order_id=order.id, ready_at=order.ready_at, secret=secret)
    return f'/api/public/archives/{order.id}?token={token}'


def authorized_archive_key(session: Session, *, order_id: uuid.UUID, token: str,
                           secret: str, now: datetime) -> str:
    order = PhotoOrderRepository(session).find_for_archive(order_id=order_id)
    if (order is None or order.archive_status != 'ready' or order.ready_at is None or
            order.archive_object_key is None or
            not (order.total_kopecks == 0 or order.payment_status == 'succeeded')):
        raise ArchiveUnavailableError()
    expected = _signature(order_id=order.id, ready_at=order.ready_at, secret=secret)
    # Compare bytes to reject non-ASCII caller input without exceptions/leaks.
    if not hmac.compare_digest(expected.encode(), token.encode()):
        raise ArchiveUnavailableError()
    if now >= order.ready_at + timedelta(days=3):
        raise ArchiveExpiredError()
    return order.archive_object_key

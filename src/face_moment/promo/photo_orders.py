"""Promo-owned frozen order command; caller commits/rolls back order and profile.

@docs .memory-bank/domains/photo-orders.md
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.infrastructure.database import Base
from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.promo.browser_search_profile import BrowserSearchProfileRepository
from face_moment.promo.photo_quote import quote_selected_photos
from face_moment.promo.public_photo_search import PublicProfileRequiredError


class PhotoOrder(Base):
    __tablename__ = 'photo_orders'
    __table_args__ = (
        UniqueConstraint('profile_id', 'client_request_id', name='uq_photo_order_profile_request'),
        CheckConstraint("archive_status IN ('requested','preparing','ready','failed')", name='ck_photo_order_archive_status'),
        CheckConstraint("payment_status IN ('not_required','pending','succeeded','canceled')", name='ck_photo_order_payment_status'),
        CheckConstraint("payment_method IS NULL OR payment_method IN ('bank_card','sbp')", name='ck_photo_order_payment_method'),
        CheckConstraint("total_kopecks >= 0 AND total_kopecks = trunc(total_kopecks) AND total_kopecks < 'Infinity'::numeric", name='ck_photo_order_total'),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('face_moment.browser_search_profiles.id', ondelete='RESTRICT'), nullable=False)
    client_request_id: Mapped[str] = mapped_column(Text, nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    total_kopecks: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archive_status: Mapped[str] = mapped_column(String(16), nullable=False)
    archive_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archive_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    payment_idempotence_key: Mapped[str] = mapped_column(String(36), nullable=False)
    payment_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_status: Mapped[str] = mapped_column(String(16), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PhotoOrderConflictError(ValueError):
    """The transport maps reuse of client_request_id with another payload to 409."""


class PhotoOrderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_for_archive(self, *, order_id: uuid.UUID) -> PhotoOrder | None:
        """Server-internal read; bearer service must validate entitlement/signature."""
        return self.session.get(PhotoOrder, order_id)

    def find(self, *, cookie_token: str, order_id: uuid.UUID) -> PhotoOrder | None:
        """Owner read; the returned model remains server-internal, including private key."""
        profile = BrowserSearchProfileRepository(self.session).find(cookie_token)
        if profile is None:
            return None
        return self.session.scalar(select(PhotoOrder).where(
            PhotoOrder.id == order_id, PhotoOrder.profile_id == profile.id))

    def create(self, *, cookie_token: str, result_id: uuid.UUID,
               photo_ids: Sequence[uuid.UUID], client_request_id: str,
               object_store: PrivateObjectStore, email: str | None = None,
               payment_method: str | None = None) -> PhotoOrder:
        """Freeze accepted provider quote once; replay does not consult changed state.

        No commit, provider, mail, or ZIP side effect. On any error caller must
        roll back. The same profile lock used by search serializes its order
        requests through commit and keeps current-gallery validation coherent.
        """
        if not isinstance(client_request_id, str) or not client_request_id.strip():
            raise ValueError('client_request_id required')
        if len(set(photo_ids)) != len(photo_ids):
            raise ValueError('distinct photo IDs required')
        request = {'result_id': str(result_id), 'photo_ids': sorted(str(i) for i in photo_ids),
                   'email': email, 'payment_method': payment_method}
        digest = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        profile = BrowserSearchProfileRepository(self.session).find(cookie_token, lock=True)
        if profile is None:
            raise PublicProfileRequiredError
        existing = self.session.scalar(select(PhotoOrder).where(
            PhotoOrder.profile_id == profile.id, PhotoOrder.client_request_id == client_request_id))
        if existing is not None:
            if existing.request_digest != digest:
                raise PhotoOrderConflictError('client_request_id payload conflict')
            return existing
        quote = quote_selected_photos(self.session, cookie_token=cookie_token,
            result_id=result_id, photo_ids=photo_ids, object_store=object_store)
        paid = quote['total_kopecks'] > 0
        if paid:
            if (not isinstance(email, str) or len(email) > 320 or
                    email.count('@') != 1 or any(c.isspace() for c in email) or
                    not all(email.split('@'))):
                raise ValueError('paid email required')
            if payment_method not in ('bank_card', 'sbp'):
                raise ValueError('paid method must be bank_card or sbp')
        now = datetime.now(timezone.utc)
        order_id = uuid.uuid4()
        record = PhotoOrder(id=order_id, profile_id=profile.id,
            client_request_id=client_request_id, request_digest=digest,
            items=quote['items'], total_kopecks=Decimal(quote['total_kopecks']),
            email=email if paid else None, payment_method=payment_method if paid else None,
            created_at=now, archive_status='requested', archive_object_key=None,
            ready_at=None, archive_failure_reason=None, provider_payment_id=None,
            payment_idempotence_key=str(order_id), payment_requested_at=None,
            payment_status='pending' if paid else 'not_required', paid_at=None)
        self.session.add(record)
        if paid:
            profile.email = email
        profile.last_visit_at = now
        self.session.flush()
        return record

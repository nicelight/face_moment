"""Promo-owned initiation of one payment for a frozen ready paid archive.

@docs .memory-bank/contracts/photo-purchase-api.md#юkassa-и-email
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import urlsplit
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.promo.browser_search_profile import BrowserSearchProfileRepository
from face_moment.promo.photo_orders import PhotoOrder
from face_moment.promo.photo_orders import PhotoOrderRepository
from face_moment.promo.public_photo_search import PublicProfileRequiredError, PublicResultNotFoundError


class PaymentNotReadyError(ValueError):
    """An existing order cannot begin provider payment in its current state."""


class PaymentConfigurationError(RuntimeError):
    """Required provider or receipt configuration is unavailable."""


class PaymentProviderError(RuntimeError):
    """Provider request or response failed without exposing private details."""


class PaymentReconciliationRequiredError(RuntimeError):
    """The original provider idempotency window is no longer safe to replay."""


@dataclass(frozen=True)
class CreatedPayment:
    provider_id: str
    confirmation_url: str


class PaymentProvider(Protocol):
    def configured(self) -> bool: ...
    def create_payment(self, *, idempotence_key: str, payload: dict[str, Any]) -> CreatedPayment: ...
    def get_payment(self, payment_id: str) -> dict[str, Any]: ...


def _rub(kopecks: int) -> str:
    return f'{kopecks // 100}.{kopecks % 100:02d}'


def _https_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme == 'https' and bool(parsed.hostname)
    except ValueError:
        return False


def _receipt(order: PhotoOrder, *, description: str, vat_code: int,
             payment_subject: str, payment_mode: str,
             tax_system_code: int | None) -> dict[str, Any]:
    if not order.email or not description or vat_code != 1 or payment_subject != 'service' or payment_mode != 'full_payment':
        raise PaymentConfigurationError
    counts: Counter[int] = Counter()
    for item in order.items:
        unit = item['unit_kopecks']
        if not isinstance(unit, int) or isinstance(unit, bool) or unit < 0:
            raise PaymentConfigurationError
        if unit > 0:
            counts[unit] += 1
    if not counts or len(counts) > 4 or sum(unit * count for unit, count in counts.items()) != order.total_kopecks:
        raise PaymentConfigurationError
    items = [{'description': description, 'quantity': str(count),
              'amount': {'value': _rub(unit), 'currency': 'RUB'},
              'vat_code': vat_code, 'payment_subject': payment_subject,
              'payment_mode': payment_mode}
             for unit, count in sorted(counts.items(), reverse=True)]
    receipt: dict[str, Any] = {'customer': {'email': order.email}, 'items': items}
    if tax_system_code is not None:
        if tax_system_code != 2:
            raise PaymentConfigurationError
        receipt['tax_system_code'] = tax_system_code
    return receipt


class PhotoPaymentInitiator:
    def __init__(self, session_factory: Callable[[], Session], store: PrivateObjectStore,
                 provider: PaymentProvider, *, return_url: str | None, receipt_description: str | None,
                 receipt_vat_code: int | None, receipt_payment_subject: str | None,
                 receipt_payment_mode: str | None, receipt_tax_system_code: int | None) -> None:
        self.session_factory = session_factory
        self.store = store
        self.provider = provider
        self.return_url = return_url
        self.receipt_description = receipt_description
        self.receipt_vat_code = receipt_vat_code
        self.receipt_payment_subject = receipt_payment_subject
        self.receipt_payment_mode = receipt_payment_mode
        self.receipt_tax_system_code = receipt_tax_system_code

    def _owned_locked(self, session: Session, cookie_token: str, order_id: uuid.UUID) -> PhotoOrder:
        profile = BrowserSearchProfileRepository(session).find(cookie_token)
        if profile is None:
            raise PublicProfileRequiredError
        order = session.scalar(select(PhotoOrder).where(PhotoOrder.id == order_id,
            PhotoOrder.profile_id == profile.id).with_for_update())
        if order is None:
            raise PublicResultNotFoundError
        return order

    def _ready(self, order: PhotoOrder, now: datetime) -> None:
        if (order.archive_status != 'ready' or order.ready_at is None or
                order.archive_object_key is None or order.total_kopecks <= 0 or
                order.payment_status != 'pending' or
                now >= order.ready_at + timedelta(days=3)):
            raise PaymentNotReadyError
        if not self.store.exists(key=order.archive_object_key):
            raise PaymentNotReadyError

    def _configured(self) -> None:
        if (not self.provider.configured() or not _https_url(self.return_url) or
                not self.receipt_description or self.receipt_vat_code != 1 or
                self.receipt_payment_subject != 'service' or
                self.receipt_payment_mode != 'full_payment' or
                self.receipt_tax_system_code not in (None, 2)):
            raise PaymentConfigurationError

    def start(self, *, cookie_token: str, order_id: uuid.UUID,
              now: datetime | None = None) -> str:
        current = now or datetime.now(timezone.utc)
        # Record the first possible provider attempt durably before network IO.
        # An uncertain response can then be replayed with the same key only
        # while YooKassa's 24-hour idempotency guarantee remains in force.
        with self.session_factory() as session:
            order = self._owned_locked(session, cookie_token, order_id)
            self._ready(order, current)
            self._configured()
            if order.payment_requested_at is not None:
                if current >= order.payment_requested_at + timedelta(hours=24):
                    raise PaymentReconciliationRequiredError
            else:
                order.payment_requested_at = current
                session.commit()

        # Re-lock after the durable attempt marker. Concurrent calls use one
        # frozen payload/key; only the recorded matching provider ID can win.
        with self.session_factory() as session:
            order = self._owned_locked(session, cookie_token, order_id)
            self._ready(order, current)
            if order.payment_requested_at is None or current >= order.payment_requested_at + timedelta(hours=24):
                raise PaymentReconciliationRequiredError
            receipt = _receipt(order, description=self.receipt_description or '',
                vat_code=self.receipt_vat_code or 0,
                payment_subject=self.receipt_payment_subject or '',
                payment_mode=self.receipt_payment_mode or '',
                tax_system_code=self.receipt_tax_system_code)
            payload = {'amount': {'value': _rub(int(order.total_kopecks)), 'currency': 'RUB'},
                'capture': True, 'payment_method_data': {'type': order.payment_method},
                'confirmation': {'type': 'redirect', 'return_url': self.return_url},
                'metadata': {'order_id': str(order.id)}, 'receipt': receipt}
            payment = self.provider.create_payment(
                idempotence_key=order.payment_idempotence_key, payload=payload)
            if order.provider_payment_id is not None and order.provider_payment_id != payment.provider_id:
                raise PaymentReconciliationRequiredError
            order.provider_payment_id = payment.provider_id
            session.commit()
            return payment.confirmation_url


class PhotoPaymentConfirmer:
    """Promo's single provider-truth transition for webhook and owner refresh."""

    def __init__(self, session_factory: Callable[[], Session], provider: PaymentProvider) -> None:
        self.session_factory = session_factory
        self.provider = provider

    def confirm(self, payment_id: str, *, now: datetime | None = None) -> None:
        with self.session_factory() as session:
            order = session.scalar(select(PhotoOrder).where(PhotoOrder.provider_payment_id == payment_id))
            if order is None or order.payment_status == 'succeeded':
                return
        provider_payment = self.provider.get_payment(payment_id)
        with self.session_factory() as session:
            order = session.scalar(select(PhotoOrder).where(
                PhotoOrder.provider_payment_id == payment_id).with_for_update())
            if order is None or order.payment_status == 'succeeded':
                return
            amount = provider_payment.get('amount')
            metadata = provider_payment.get('metadata')
            if (provider_payment.get('id') != order.provider_payment_id or
                    not isinstance(amount, dict) or
                    amount != {'value': _rub(int(order.total_kopecks)), 'currency': 'RUB'} or
                    not isinstance(metadata, dict) or metadata.get('order_id') != str(order.id)):
                return
            if provider_payment.get('status') == 'succeeded' and provider_payment.get('paid') is True:
                order.payment_status = 'succeeded'
                order.paid_at = now or datetime.now(timezone.utc)
            elif provider_payment.get('status') == 'canceled' and provider_payment.get('paid') is False:
                order.payment_status = 'canceled'
            session.commit()

    def refresh_owned(self, *, cookie_token: str, order_id: uuid.UUID) -> None:
        with self.session_factory() as session:
            order = PhotoOrderRepository(session).find(cookie_token=cookie_token, order_id=order_id)
            if order is None or order.payment_status != 'pending' or order.provider_payment_id is None:
                return
            payment_id = order.provider_payment_id
        self.confirm(payment_id)

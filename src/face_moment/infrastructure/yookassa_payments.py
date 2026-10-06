"""Authenticated YooKassa create-payment transport; no order decisions."""
from __future__ import annotations

import base64
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from face_moment.promo.photo_payment import CreatedPayment, PaymentProviderError, _https_url


class YooKassaPayments:
    def __init__(self, shop_id: str | None, secret_key: str | None,
                 *, endpoint: str = 'https://api.yookassa.ru/v3/payments',
                 timeout_seconds: float = 10.0) -> None:
        self.shop_id = shop_id
        self.secret_key = secret_key
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def configured(self) -> bool:
        return bool(self.shop_id and self.secret_key)

    def get_payment(self, payment_id: str) -> dict[str, Any]:
        if not self.configured():
            raise PaymentProviderError('Provider is unavailable')
        credentials = base64.b64encode(f'{self.shop_id}:{self.secret_key}'.encode()).decode('ascii')
        request = Request(f'{self.endpoint}/{quote(payment_id, safe="")}',
            headers={'Authorization': f'Basic {credentials}'}, method='GET')
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status != 200:
                    raise PaymentProviderError('Provider payment result is unavailable')
                result = json.loads(response.read(65537))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            raise PaymentProviderError('Provider payment result is unavailable') from error
        if not isinstance(result, dict):
            raise PaymentProviderError('Provider payment result is invalid')
        return result

    def create_payment(self, *, idempotence_key: str, payload: dict[str, Any]) -> CreatedPayment:
        if not self.configured():
            raise PaymentProviderError('Provider is unavailable')
        credentials = base64.b64encode(f'{self.shop_id}:{self.secret_key}'.encode()).decode('ascii')
        request = Request(self.endpoint,
            data=json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
            headers={'Authorization': f'Basic {credentials}',
                     'Idempotence-Key': idempotence_key,
                     'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status != 200:
                    raise PaymentProviderError('Provider rejected payment')
                result = json.loads(response.read(65537))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            raise PaymentProviderError('Provider payment result is unavailable') from error
        if not isinstance(result, dict):
            raise PaymentProviderError('Provider payment result is invalid')
        confirmation = result.get('confirmation')
        amount = result.get('amount')
        metadata = result.get('metadata')
        if (not isinstance(result.get('id'), str) or not result['id'] or
                result.get('status') != 'pending' or
                not isinstance(amount, dict) or amount != payload['amount'] or
                not isinstance(metadata, dict) or metadata.get('order_id') != payload['metadata']['order_id'] or
                not isinstance(confirmation, dict) or confirmation.get('type') != 'redirect' or
                not isinstance(confirmation.get('confirmation_url'), str) or
                not _https_url(confirmation['confirmation_url'])):
            raise PaymentProviderError('Provider payment result is invalid')
        return CreatedPayment(provider_id=result['id'], confirmation_url=confirmation['confirmation_url'])

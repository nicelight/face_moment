"""Public payment initiation route; admission and transport only."""
from __future__ import annotations

from collections.abc import Callable
import json
from typing import cast
import uuid

from fastapi import FastAPI, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

from face_moment.promo.photo_order_http import _admit
from face_moment.promo.photo_payment import (
    PaymentConfigurationError, PaymentNotReadyError, PaymentProviderError,
    PaymentReconciliationRequiredError, PhotoPaymentConfirmer, PhotoPaymentInitiator,
)
from face_moment.promo.public_photo_search import PublicProfileRequiredError, PublicResultNotFoundError
from face_moment.promo.public_search_http import PUBLIC_HEADERS, _failure


def register_photo_payment_route(app: FastAPI, *, session_factory: Callable[[], Session]) -> None:
    @app.post('/api/public/payments/yookassa')
    async def confirm_payment(request: Request) -> Response:
        if request.url.scheme != 'https':
            raise _failure(403)
        try:
            payload = await request.json()
            if (not isinstance(payload, dict) or set(payload) != {'type', 'event', 'object'} or
                    payload['type'] != 'notification' or
                    payload['event'] not in ('payment.succeeded', 'payment.canceled') or
                    not isinstance(payload['object'], dict) or
                    not isinstance(payload['object'].get('id'), str) or not payload['object']['id']):
                raise ValueError('invalid payment notification')
        except (ValueError, TypeError) as error:
            raise _failure(422) from error
        confirmer = request.app.state.role_state.get('photo_payment_confirmer')
        if confirmer is None:
            raise _failure(503)
        try:
            await run_in_threadpool(cast(PhotoPaymentConfirmer, confirmer).confirm, payload['object']['id'])
        except PaymentProviderError as error:
            raise _failure(502) from error
        except Exception as error:
            raise _failure(500) from error
        return JSONResponse({'schema_version': 1}, headers=PUBLIC_HEADERS)

    @app.post('/api/public/orders/{order_id}/payment')
    async def initiate_payment(request: Request, order_id: str) -> Response:
        token = _admit(request, mutation=True)
        try:
            identity = uuid.UUID(order_id)
        except ValueError as error:
            raise _failure(404) from error
        try:
            raw = await request.body()
            if raw and json.loads(raw) != {}:
                raise ValueError('payment body must be empty')
        except (ValueError, TypeError) as error:
            raise _failure(422) from error
        payment = request.app.state.role_state.get('photo_payment_initiator')
        if payment is None:
            raise _failure(503)

        def start() -> str:
            return cast(PhotoPaymentInitiator, payment).start(cookie_token=token, order_id=identity)

        try:
            confirmation_url = await run_in_threadpool(start)
        except PublicProfileRequiredError as error:
            raise _failure(401) from error
        except PublicResultNotFoundError as error:
            raise _failure(404) from error
        except PaymentNotReadyError as error:
            raise _failure(409) from error
        except (PaymentConfigurationError, PaymentReconciliationRequiredError) as error:
            raise _failure(503) from error
        except PaymentProviderError as error:
            raise _failure(502) from error
        except Exception as error:
            raise _failure(500) from error
        return JSONResponse({'schema_version': 1, 'confirmation_url': confirmation_url},
                            headers=PUBLIC_HEADERS)

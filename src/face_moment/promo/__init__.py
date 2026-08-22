"""Promo-owned Attempt persistence boundary."""

from face_moment.promo.attempt import (
    PromoAttempt,
    PromoAttemptNotFoundError,
    PromoAttemptRepository,
)
from face_moment.promo.result_assembly import ResultAssembly, assemble_result
from face_moment.promo.session import (
    FIRST_OPEN_TTL,
    PromoSession,
    PromoSessionNotFoundError,
    PromoSessionRepository,
    ResultSessionResponse,
    derive_qr_ticket,
    hash_qr_ticket,
)
from face_moment.promo.realtime_orchestration import (
    RealtimeOrchestrator,
    RealtimeProcessingOutcome,
)

__all__ = [
    "PromoAttempt",
    "PromoAttemptNotFoundError",
    "PromoAttemptRepository",
    "ResultAssembly",
    "assemble_result",
    "RealtimeOrchestrator",
    "RealtimeProcessingOutcome",
    "FIRST_OPEN_TTL",
    "PromoSession",
    "PromoSessionNotFoundError",
    "PromoSessionRepository",
    "ResultSessionResponse",
    "derive_qr_ticket",
    "hash_qr_ticket",
]

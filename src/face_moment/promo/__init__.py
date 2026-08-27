"""Promo-owned Attempt persistence boundary."""

from face_moment.promo.attempt import (
    PromoAttempt,
    PromoAttemptNotFoundError,
    PromoAttemptRepository,
)
from face_moment.promo.result_assembly import ResultAssembly, assemble_result
from face_moment.promo.session import (
    BROWSER_IDLE_TTL,
    FIRST_OPEN_TTL,
    PromoBrowserAccessExpiredError,
    PromoSession,
    PromoSessionNotFoundError,
    PromoSessionRepository,
    ResultSessionResponse,
    derive_qr_ticket,
    hash_qr_ticket,
)
from face_moment.promo.realtime_orchestration import (
    RealtimeAttemptExecution,
    RealtimeOrchestrator,
    RealtimeProcessingOutcome,
    execute_realtime_attempt,
)
from face_moment.promo.display_media import (
    PromoMediaNotFoundError,
    derive_media_ref,
    resolve_teaser_media,
)
from face_moment.promo.display_outcome import (
    DisplayOutcome,
    DisplayOutcomeRepository,
    DisplayReport,
    DisplayReportConflictError,
    InvalidDisplayReportError,
    PromoDisplaySessionNotFoundError,
    parse_display_report,
)
from face_moment.promo.display_config import (
    DisplayConfiguration,
    InvalidDisplayConfigurationError,
    read_display_configuration,
)

__all__ = [
    "PromoAttempt",
    "PromoAttemptNotFoundError",
    "PromoAttemptRepository",
    "ResultAssembly",
    "assemble_result",
    "RealtimeOrchestrator",
    "RealtimeAttemptExecution",
    "RealtimeProcessingOutcome",
    "execute_realtime_attempt",
    "FIRST_OPEN_TTL",
    "BROWSER_IDLE_TTL",
    "PromoBrowserAccessExpiredError",
    "PromoSession",
    "PromoSessionNotFoundError",
    "PromoSessionRepository",
    "ResultSessionResponse",
    "derive_qr_ticket",
    "hash_qr_ticket",
    "PromoMediaNotFoundError",
    "derive_media_ref",
    "resolve_teaser_media",
    "DisplayOutcome",
    "DisplayOutcomeRepository",
    "DisplayReport",
    "DisplayReportConflictError",
    "InvalidDisplayReportError",
    "PromoDisplaySessionNotFoundError",
    "parse_display_report",
    "DisplayConfiguration",
    "InvalidDisplayConfigurationError",
    "read_display_configuration",
]

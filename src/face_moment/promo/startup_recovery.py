from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from face_moment.promo.attempt import PromoAttemptRepository


class RealtimeStartupRecoveryRepository:
    """Promo-owned realtime restart recovery inside the caller's transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def recover(self, *, now: datetime | None = None) -> int:
        """Interrupt stale Attempts once, leaving terminal history unchanged."""

        return PromoAttemptRepository(self._session).interrupt_stale(now=now)

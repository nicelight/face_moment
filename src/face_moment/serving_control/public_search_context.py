"""Immutable settings for public selected-venue search, without Promo dates."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from face_moment.serving_control.ingest_target import Spa

from face_moment.serving_control.realtime_context import (
    CalibrationServingSnapshot, RealtimeContextRepository, RealtimeReadinessClosedError,
)


@dataclass(frozen=True, slots=True)
class PublicSearchContext:
    pipeline_revision_id: uuid.UUID
    venues: tuple[CalibrationServingSnapshot, ...]

    @property
    def min_query_face_quality(self) -> float:
        return max(venue.min_query_face_quality for venue in self.venues)


def read_public_search_context(
    session: Session, *, venue_ids: Sequence[uuid.UUID],
    admitted_pipeline_revision_id: uuid.UUID,
) -> PublicSearchContext:
    """Freeze active venue settings against the already warmed shared revision."""
    ids = tuple(venue_ids)
    if not 1 <= len(ids) <= 3 or len(set(ids)) != len(ids):
        raise ValueError("select 1–3 distinct venues")
    if any(not isinstance(value, uuid.UUID) for value in ids):
        raise ValueError("venue IDs must be UUIDs")
    # Stable lock order agrees across concurrent multi-venue reads.
    repository = RealtimeContextRepository(session)
    snapshots = {
        venue_id: repository.read_calibration_serving_snapshot(spa_id=venue_id)
        for venue_id in sorted(ids)
    }
    if any(item.pipeline_revision_id != admitted_pipeline_revision_id
           for item in snapshots.values()):
        raise RealtimeReadinessClosedError(("model_revision",))
    return PublicSearchContext(
        pipeline_revision_id=admitted_pipeline_revision_id,
        venues=tuple(snapshots[value] for value in ids),
    )


@dataclass(frozen=True, slots=True)
class PublicVenue:
    id: uuid.UUID
    name: str
    is_free: bool


def read_public_venues(session: Session) -> tuple[PublicVenue, ...]:
    """Immutable public owner projection; no model-health or Photo data."""
    return tuple(PublicVenue(row.id, row.name, row.is_free) for row in session.execute(
        select(Spa.id, Spa.name, Spa.is_free).where(Spa.active.is_(True)).order_by(Spa.name, Spa.id)))

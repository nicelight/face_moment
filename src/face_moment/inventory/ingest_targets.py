"""Inventory-owned authorization and response assembly for ingest targets."""

from __future__ import annotations

from typing import Literal, TypedDict

from sqlalchemy.orm import Session

from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import InvalidSessionError, get_current_principal
from face_moment.serving_control import IngestTargetRepository


class IngestTargetProjection(TypedDict):
    spa_id: str
    name: str
    timezone: str


class IngestTargetContext(TypedDict):
    schema_version: Literal[1]
    spas: list[IngestTargetProjection]


class PhotographerAccessDeniedError(PermissionError):
    """The authenticated staff principal cannot read photographer targets."""


def read_ingest_target_context(
    database_session: Session,
    *,
    session_token: str | None,
) -> IngestTargetContext:
    """Authorize the photographer read and consume serving-control projections."""
    principal = get_current_principal(database_session, session_token=session_token)
    if principal.role is not StaffRole.PHOTOGRAPHER:
        raise PhotographerAccessDeniedError

    targets = IngestTargetRepository(
        database_session
    ).list_active_eligible_ingest_targets()
    return {
        "schema_version": 1,
        "spas": [
            {
                "spa_id": str(target.spa_id),
                "name": target.name,
                "timezone": target.timezone,
            }
            for target in targets
        ],
    }


__all__ = [
    "IngestTargetContext",
    "InvalidSessionError",
    "PhotographerAccessDeniedError",
    "read_ingest_target_context",
]

"""Manual, venue-scoped edits of the current serving model's similarity threshold."""

import math
import uuid

from sqlalchemy.orm import Session

from face_moment.platform.auth.sessions import (
    authenticate_unsafe_staff_request, get_current_principal,
)
from face_moment.serving_control.active_search_date import _authorize, _load_accessible_spa
from face_moment.serving_control.realtime_context import (
    CalibrationRecommendationConflictError, CalibrationServingSnapshot,
    RealtimeContextRepository,
)


def read_similarity_threshold(
    session: Session, *, spa_id: uuid.UUID, session_token: str | None,
) -> CalibrationServingSnapshot:
    principal = get_current_principal(session, session_token=session_token)
    _authorize(principal.role)
    _load_accessible_spa(session, spa_id)
    return RealtimeContextRepository(session).read_calibration_serving_snapshot(spa_id=spa_id)


def save_similarity_threshold(
    session: Session, *, spa_id: uuid.UUID, threshold: float,
    pipeline_revision_id: uuid.UUID, settings_revision: int,
    session_token: str | None, csrf_cookie_token: str | None,
    csrf_header_token: str | None,
) -> CalibrationServingSnapshot:
    principal = authenticate_unsafe_staff_request(
        session, session_token=session_token, csrf_cookie_token=csrf_cookie_token,
        csrf_header_token=csrf_header_token,
    )
    _authorize(principal.role)
    if isinstance(threshold, bool) or not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise ValueError("threshold must be a finite cosine similarity in [-1, 1]")
    _load_accessible_spa(session, spa_id)
    owner = RealtimeContextRepository(session)
    # The owner holds the venue row lock through comparison, update and commit.
    current = owner.read_calibration_serving_snapshot(spa_id=spa_id)
    if (current.settings_revision != settings_revision
            or current.pipeline_revision_id != pipeline_revision_id):
        raise CalibrationRecommendationConflictError("serving settings changed")
    owner.update_reference_settings(
        spa_id=spa_id, pipeline_code=current.pipeline_code,
        reference_threshold=threshold, min_query_face_quality=current.min_query_face_quality,
        quality_settings=current.quality_settings, calibration_id=None,
    )
    return owner.read_calibration_serving_snapshot(spa_id=spa_id)

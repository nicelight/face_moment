"""Per-venue photographer YuNet and browser BlazeFace settings."""

from datetime import datetime, timezone
import math
from typing import Literal
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.platform.auth.sessions import authenticate_unsafe_staff_request
from face_moment.serving_control.active_search_date import (
    ActiveSearchDateAccessDeniedError,
    ActiveSearchDateSpaNotFoundError,
    _authorize,
)
from face_moment.serving_control.ingest_target import Spa

DetectorKind = Literal["photo_yunet", "capture_blazeface"]


def update_detector_threshold(
    session: Session, *, spa_id: uuid.UUID, detector: DetectorKind,
    threshold: float, session_token: str | None,
    csrf_cookie_token: str | None, csrf_header_token: str | None,
) -> float:
    principal = authenticate_unsafe_staff_request(
        session, session_token=session_token, csrf_cookie_token=csrf_cookie_token,
        csrf_header_token=csrf_header_token,
    )
    _authorize(principal.role)
    if isinstance(threshold, bool) or not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("detector threshold must be in (0, 1]")
    spa = session.scalar(select(Spa).where(Spa.id == spa_id).with_for_update())
    if spa is None:
        raise ActiveSearchDateSpaNotFoundError(str(spa_id))
    if not spa.active:
        raise ActiveSearchDateAccessDeniedError
    if detector == "photo_yunet":
        spa.photo_yunet_threshold = threshold
    elif detector == "capture_blazeface":
        spa.capture_blazeface_threshold = threshold
    else:
        raise ValueError("unknown detector")
    spa.settings_revision += 1
    spa.settings_updated_at = datetime.now(timezone.utc)
    session.flush()
    return threshold


def read_capture_detector_threshold(session: Session, *, spa_id: uuid.UUID) -> float:
    """Read only the authenticated display principal's active venue."""
    value = session.scalar(select(Spa.capture_blazeface_threshold).where(
        Spa.id == spa_id, Spa.active.is_(True),
    ))
    if value is None:
        raise ActiveSearchDateSpaNotFoundError(str(spa_id))
    return value

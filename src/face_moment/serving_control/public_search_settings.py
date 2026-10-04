"""Serving-control-owned profile threshold, independent of Photo search settings."""
from __future__ import annotations

import math

from sqlalchemy import CheckConstraint, Float, Integer, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.infrastructure.database import Base
from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import authenticate_unsafe_staff_request, get_current_principal


class PublicSearchSettings(Base):
    __tablename__ = "public_search_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_public_search_settings_singleton"),
        CheckConstraint("profile_similarity_threshold >= -1 AND profile_similarity_threshold <= 1",
                        name="ck_public_search_settings_threshold"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_similarity_threshold: Mapped[float] = mapped_column(Float, nullable=False)


class PublicSearchSettingsAccessDeniedError(PermissionError):
    pass


def read_profile_similarity_threshold(session: Session) -> float:
    """Published immutable scalar projection for promo admission."""
    return float(session.execute(select(PublicSearchSettings.profile_similarity_threshold)
                                 .where(PublicSearchSettings.id == 1)).scalar_one())


def read_public_search_settings(session: Session, *, session_token: str | None) -> float:
    principal = get_current_principal(session, session_token=session_token)
    if principal.role != StaffRole.DEVELOPER:
        raise PublicSearchSettingsAccessDeniedError("Developer required")
    return read_profile_similarity_threshold(session)


def save_public_search_settings(
    session: Session, *, threshold: float, session_token: str | None,
    csrf_cookie_token: str | None, csrf_header_token: str | None,
) -> float:
    principal = authenticate_unsafe_staff_request(session, session_token=session_token,
        csrf_cookie_token=csrf_cookie_token, csrf_header_token=csrf_header_token)
    if principal.role != StaffRole.DEVELOPER:
        raise PublicSearchSettingsAccessDeniedError("Developer required")
    if isinstance(threshold, bool) or not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise ValueError("profile threshold must be finite in [-1,1]")
    record = session.execute(select(PublicSearchSettings).where(PublicSearchSettings.id == 1)
                             .with_for_update()).scalar_one()
    record.profile_similarity_threshold = threshold
    session.flush()
    return threshold

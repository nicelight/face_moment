"""Serving-control-owned global tariff and immutable purchase projection.

@docs .memory-bank/domains/photo-orders.md
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, localcontext

from sqlalchemy import CheckConstraint, DateTime, Integer, Numeric, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.infrastructure.database import Base
from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import authenticate_unsafe_staff_request, get_current_principal


class PhotoTariff(Base):
    __tablename__ = "photo_tariff"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_photo_tariff_singleton"),
        CheckConstraint("base_kopecks > 0 AND base_kopecks = trunc(base_kopecks) AND base_kopecks < 'Infinity'::numeric", name="ck_photo_tariff_base"),
        CheckConstraint("1 >= d1 AND d1 >= d2 AND d2 >= d3 AND d3 > 0", name="ck_photo_tariff_coefficients"),
        CheckConstraint("round(base_kopecks * d3) >= 1", name="ck_photo_tariff_paid_unit"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    base_kopecks: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    d1: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    d2: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    d3: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class PhotoTariffSnapshot:
    base_kopecks: int
    d1: Decimal
    d2: Decimal
    d3: Decimal
    updated_at: datetime


class PhotoTariffAccessDeniedError(PermissionError):
    pass


class PhotoTariffUnavailableError(RuntimeError):
    pass


def read_photo_tariff_snapshot(session: Session) -> PhotoTariffSnapshot:
    """Public immutable projection; an unprovisioned tariff cannot supply a price."""
    row = session.execute(select(PhotoTariff.base_kopecks, PhotoTariff.d1,
        PhotoTariff.d2, PhotoTariff.d3, PhotoTariff.updated_at).where(PhotoTariff.id == 1)).one_or_none()
    if row is None:
        raise PhotoTariffUnavailableError("Global photo tariff has not been provisioned")
    return PhotoTariffSnapshot(int(row.base_kopecks), row.d1, row.d2, row.d3, row.updated_at)


def read_photo_tariff(session: Session, *, session_token: str | None) -> PhotoTariffSnapshot:
    principal = get_current_principal(session, session_token=session_token)
    if principal.role not in (StaffRole.OPERATOR, StaffRole.DEVELOPER):
        raise PhotoTariffAccessDeniedError("Operator or developer required")
    return read_photo_tariff_snapshot(session)


def save_photo_tariff(
    session: Session, *, base_kopecks: int, d1: Decimal, d2: Decimal, d3: Decimal,
    session_token: str | None, csrf_cookie_token: str | None, csrf_header_token: str | None,
) -> PhotoTariffSnapshot:
    principal = authenticate_unsafe_staff_request(session, session_token=session_token,
        csrf_cookie_token=csrf_cookie_token, csrf_header_token=csrf_header_token)
    if principal.role not in (StaffRole.OPERATOR, StaffRole.DEVELOPER):
        raise PhotoTariffAccessDeniedError("Operator or developer required")
    if type(base_kopecks) is not int or base_kopecks <= 0:
        raise ValueError("Base must be positive integer kopecks")
    if any(not isinstance(d, Decimal) or not d.is_finite() for d in (d1, d2, d3)):
        raise ValueError("Coefficients must be finite decimals")
    if not Decimal(1) >= d1 >= d2 >= d3 > 0:
        raise ValueError("Coefficients must satisfy 1 >= d1 >= d2 >= d3 > 0")
    with localcontext() as context:
        context.prec = len(str(base_kopecks)) + len(d3.as_tuple().digits) + 2
        if Decimal(base_kopecks) * d3 < Decimal("0.5"):
            raise ValueError("Each rounded paid unit must be at least one kopeck")
    values = dict(base_kopecks=Decimal(base_kopecks), d1=d1, d2=d2, d3=d3,
                  updated_at=datetime.now(timezone.utc))
    session.execute(insert(PhotoTariff).values(id=1, **values)
        .on_conflict_do_update(index_elements=[PhotoTariff.id], set_=values))
    session.flush()
    return read_photo_tariff_snapshot(session)

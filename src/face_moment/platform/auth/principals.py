from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from argon2.low_level import Type
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    String,
    Text,
    Uuid,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import func

from face_moment.infrastructure.database import Base

_MAX_USERNAME_LENGTH = 255
_PASSWORD_HASHER = PasswordHasher(type=Type.ID)


class StaffRole(StrEnum):
    PHOTOGRAPHER = "photographer"
    OPERATOR = "operator"
    DEVELOPER = "developer"


class StaffUser(Base):
    __tablename__ = "staff_users"
    __table_args__ = (
        CheckConstraint(
            "username = lower(username)",
            name="ck_staff_users_username_normalized",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(_MAX_USERNAME_LENGTH), nullable=False, unique=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[StaffRole] = mapped_column(
        Enum(
            StaffRole,
            name="staff_role",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda roles: [role.value for role in roles],
        ),
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


@dataclass(frozen=True, slots=True)
class StaffPrincipal:
    staff_user_id: uuid.UUID
    username: str
    role: StaffRole


class InvalidUsernameError(ValueError):
    pass


class InvalidPasswordError(ValueError):
    pass


class DuplicateUsernameError(ValueError):
    pass


class StaffUserNotFoundError(ValueError):
    pass


def normalize_username(username: str) -> str:
    normalized = username.strip().casefold()
    if not normalized or len(normalized) > _MAX_USERNAME_LENGTH:
        raise InvalidUsernameError("username must contain 1 to 255 characters")
    return normalized


def provision_staff_user(
    session: Session,
    *,
    username: str,
    password: str,
    role: StaffRole,
) -> StaffPrincipal:
    normalized_username = normalize_username(username)
    if not password:
        raise InvalidPasswordError("password must not be empty")

    staff_user = StaffUser(
        username=normalized_username,
        password_hash=_PASSWORD_HASHER.hash(password),
        role=role,
        active=True,
    )
    session.add(staff_user)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateUsernameError(normalized_username) from error
    session.refresh(staff_user)
    return StaffPrincipal(
        staff_user_id=staff_user.id,
        username=staff_user.username,
        role=staff_user.role,
    )


def verify_password(encoded_hash: str, password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(encoded_hash, password)
    except VerificationError:
        return False


def reset_staff_password(
    session: Session,
    *,
    username: str,
    password: str,
    now: datetime,
) -> StaffPrincipal:
    if not password:
        raise InvalidPasswordError("password must not be empty")
    staff_user = _staff_user_by_username(session, username)
    staff_user.password_hash = _PASSWORD_HASHER.hash(password)
    staff_user.password_changed_at = now.astimezone(timezone.utc)
    return _principal_from_staff_user(staff_user)


def deactivate_staff_user(
    session: Session,
    *,
    username: str,
    now: datetime,
) -> StaffPrincipal:
    staff_user = _staff_user_by_username(session, username)
    if staff_user.active:
        staff_user.active = False
        staff_user.deactivated_at = now.astimezone(timezone.utc)
    return _principal_from_staff_user(staff_user)


def _staff_user_by_username(session: Session, username: str) -> StaffUser:
    normalized_username = normalize_username(username)
    staff_user = session.scalar(
        select(StaffUser).where(StaffUser.username == normalized_username)
    )
    if staff_user is None:
        raise StaffUserNotFoundError
    return staff_user


def _principal_from_staff_user(staff_user: StaffUser) -> StaffPrincipal:
    return StaffPrincipal(
        staff_user_id=staff_user.id,
        username=staff_user.username,
        role=staff_user.role,
    )

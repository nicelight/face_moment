"""Backend startup synchronization for owner-supplied staff credentials."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.platform.auth.principals import (
    DuplicateUsernameError,
    StaffRole,
    StaffUser,
    provision_staff_user,
    verify_password,
)
from face_moment.platform.auth.sessions import reset_staff_password_and_revoke_sessions


_STAFF_ENVIRONMENT = (
    ("photographer", StaffRole.PHOTOGRAPHER, "STAFF_PHOTOGRAPHER_PASSWORD"),
    ("operator", StaffRole.OPERATOR, "STAFF_OPERATOR_PASSWORD"),
    ("developer", StaffRole.DEVELOPER, "STAFF_DEVELOPER_PASSWORD"),
)


class StaffEnvironmentConfigurationError(RuntimeError):
    """The configured fixed staff account conflicts with durable account state."""


def sync_staff_users_from_environment(
    session: Session,
    *,
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> None:
    """Apply non-empty fixed staff passwords supplied to the backend.

    Empty or absent variables intentionally do nothing. Existing account
    activity and roles are never changed by this synchronization.
    """

    source = os.environ if environment is None else environment
    configured = tuple(
        (username, role, password)
        for username, role, variable in _STAFF_ENVIRONMENT
        if (password := source.get(variable, ""))
    )
    if not configured:
        return

    users: dict[str, StaffUser | None] = {}
    for username, expected_role, _ in configured:
        user = session.scalar(
            select(StaffUser)
            .where(StaffUser.username == username)
            .with_for_update()
        )
        if user is not None and user.role != expected_role:
            raise StaffEnvironmentConfigurationError(
                "configured staff account role mismatch"
            )
        users[username] = user

    current_time = (
        datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)
    )
    for username, role, password in configured:
        user = users[username]
        if user is None:
            try:
                provision_staff_user(
                    session,
                    username=username,
                    password=password,
                    role=role,
                )
            except DuplicateUsernameError as error:
                raise StaffEnvironmentConfigurationError(
                    "configured staff account could not be provisioned"
                ) from error
        elif not verify_password(user.password_hash, password):
            reset_staff_password_and_revoke_sessions(
                session,
                username=username,
                password=password,
                now=current_time,
            )

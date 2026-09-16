from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.platform.auth.environment import (
    StaffEnvironmentConfigurationError,
    sync_staff_users_from_environment,
)
from face_moment.platform.auth.principals import (
    StaffRole,
    StaffUser,
    deactivate_staff_user,
    provision_staff_user,
    verify_password,
)
from face_moment.platform.auth.sessions import (
    InvalidSessionError,
    LoginRateLimiter,
    create_browser_session,
    get_current_principal,
)
from tests.disposable_postgresql import disposable_postgresql_engine


_NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def staff_environment_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    with disposable_postgresql_engine("staff_environment") as engine:
        for variable in (
            "STAFF_PHOTOGRAPHER_PASSWORD",
            "STAFF_OPERATOR_PASSWORD",
            "STAFF_DEVELOPER_PASSWORD",
        ):
            monkeypatch.delenv(variable, raising=False)
        yield engine


def _staff_row(engine: Engine, username: str) -> dict[str, object]:
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text(
                    "SELECT id, password_hash, role, active, password_changed_at, "
                    "deactivated_at FROM face_moment.staff_users "
                    "WHERE username = :username"
                ),
                {"username": username},
            )
            .mappings()
            .one()
        )


def _active_session_count(engine: Engine, username: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text(
                    "SELECT count(*) FROM face_moment.staff_sessions "
                    "WHERE staff_user_id = (SELECT id FROM face_moment.staff_users "
                    "WHERE username = :username) AND revoked_at IS NULL"
                ),
                {"username": username},
            ).scalar_one()
        )


def test_backend_startup_applies_configured_fixed_accounts(
    staff_environment_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STAFF_PHOTOGRAPHER_PASSWORD", "env-photographer")
    monkeypatch.setenv("STAFF_OPERATOR_PASSWORD", "env-operator")
    monkeypatch.setenv("STAFF_DEVELOPER_PASSWORD", "env-developer")
    monkeypatch.setattr(
        "face_moment.entrypoints.common.wait_for_dependencies",
        lambda _settings, require_bucket: None,
    )

    async def run_lifespan() -> None:
        app = create_app()
        async with app.router.lifespan_context(app):
            with Session(staff_environment_engine) as session:
                users = session.scalars(
                    select(StaffUser).order_by(StaffUser.username)
                ).all()
                assert [(user.username, user.role.value, user.active) for user in users] == [
                    ("developer", "developer", True),
                    ("operator", "operator", True),
                    ("photographer", "photographer", True),
                ]
                assert verify_password(users[0].password_hash, "env-developer")
                assert verify_password(users[1].password_hash, "env-operator")
                assert verify_password(users[2].password_hash, "env-photographer")

    asyncio.run(run_lifespan())


def test_unset_and_empty_environment_does_not_mutate_existing_account(
    staff_environment_engine: Engine,
) -> None:
    with Session(staff_environment_engine) as session:
        provision_staff_user(
            session,
            username="operator",
            password="manual-password",
            role=StaffRole.OPERATOR,
        )
        before = _staff_row(staff_environment_engine, "operator")
        sync_staff_users_from_environment(
            session,
            environment={
                "STAFF_PHOTOGRAPHER_PASSWORD": "",
                "STAFF_OPERATOR_PASSWORD": "",
                "STAFF_DEVELOPER_PASSWORD": "",
            },
        )
        after = _staff_row(staff_environment_engine, "operator")

    assert after == before


def test_same_password_preserves_hash_timestamp_and_session(
    staff_environment_engine: Engine,
) -> None:
    with Session(staff_environment_engine) as session:
        provision_staff_user(
            session,
            username="operator",
            password="same-password",
            role=StaffRole.OPERATOR,
        )
        browser_session = create_browser_session(
            session,
            username="operator",
            password="same-password",
            ip_address="127.0.0.1",
            ttl_seconds=3600,
            limiter=LoginRateLimiter(limit=10, window_seconds=60),
            now=_NOW,
        )
        before = _staff_row(staff_environment_engine, "operator")
        sync_staff_users_from_environment(
            session,
            environment={"STAFF_OPERATOR_PASSWORD": "same-password"},
            now=_NOW,
        )
        after = _staff_row(staff_environment_engine, "operator")
        assert get_current_principal(
            session,
            session_token=browser_session.session_token,
            now=_NOW,
        ).username == "operator"

    assert after["password_hash"] == before["password_hash"]
    assert after["password_changed_at"] == before["password_changed_at"]
    assert _active_session_count(staff_environment_engine, "operator") == 1


def test_changed_password_revokes_old_session_and_requires_new_password(
    staff_environment_engine: Engine,
) -> None:
    with Session(staff_environment_engine) as session:
        provision_staff_user(
            session,
            username="operator",
            password="old-password",
            role=StaffRole.OPERATOR,
        )
        browser_session = create_browser_session(
            session,
            username="operator",
            password="old-password",
            ip_address="127.0.0.1",
            ttl_seconds=3600,
            limiter=LoginRateLimiter(limit=10, window_seconds=60),
            now=_NOW,
        )
        before = _staff_row(staff_environment_engine, "operator")
        sync_staff_users_from_environment(
            session,
            environment={"STAFF_OPERATOR_PASSWORD": "new-password"},
            now=_NOW,
        )
        after = _staff_row(staff_environment_engine, "operator")
        with pytest.raises(InvalidSessionError):
            get_current_principal(
                session,
                session_token=browser_session.session_token,
                now=_NOW,
            )

    assert after["password_hash"] != before["password_hash"]
    assert after["password_changed_at"] == _NOW
    assert verify_password(str(after["password_hash"]), "new-password")
    assert not verify_password(str(after["password_hash"]), "old-password")
    assert _active_session_count(staff_environment_engine, "operator") == 0


def test_role_mismatch_fails_without_reactivating_or_changing_role(
    staff_environment_engine: Engine,
) -> None:
    with Session(staff_environment_engine) as session:
        provision_staff_user(
            session,
            username="operator",
            password="existing-password",
            role=StaffRole.DEVELOPER,
        )
        before = _staff_row(staff_environment_engine, "operator")
        with pytest.raises(
            StaffEnvironmentConfigurationError,
            match="configured staff account role mismatch",
        ):
            sync_staff_users_from_environment(
                session,
                environment={"STAFF_OPERATOR_PASSWORD": "env-password"},
                now=_NOW,
            )
        session.rollback()
        after = _staff_row(staff_environment_engine, "operator")

    assert after == before


def test_password_update_preserves_inactive_status(
    staff_environment_engine: Engine,
) -> None:
    with Session(staff_environment_engine) as session:
        provision_staff_user(
            session,
            username="operator",
            password="old-password",
            role=StaffRole.OPERATOR,
        )
        deactivate_staff_user(session, username="operator", now=_NOW)
        session.commit()
        before = _staff_row(staff_environment_engine, "operator")
        sync_staff_users_from_environment(
            session,
            environment={"STAFF_OPERATOR_PASSWORD": "new-password"},
            now=_NOW,
        )
        after = _staff_row(staff_environment_engine, "operator")

    assert after["active"] is False
    assert after["deactivated_at"] == before["deactivated_at"]
    assert after["role"] == "operator"
    assert verify_password(str(after["password_hash"]), "new-password")

from __future__ import annotations

import shutil
import subprocess
import uuid

import pytest


def test_owner_cli_provisions_one_redacted_argon2id_photographer() -> None:
    command = shutil.which("face-moment-provision-staff")
    assert command is not None, (
        "the canonical owner-backed staff provisioning command is not installed"
    )

    from alembic import command as alembic_command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text

    from face_moment.infrastructure.settings import Settings
    from face_moment.platform.auth.principals import verify_password

    settings = Settings.from_env()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    username_marker = f"task003-{uuid.uuid4().hex}"
    supplied_username = f"  {username_marker.upper()}  "
    supplied_secret = f"task003-secret-{uuid.uuid4().hex}"
    second_secret = f"task003-other-{uuid.uuid4().hex}"

    try:
        alembic_config = Config("alembic.ini")
        alembic_command.downgrade(alembic_config, "0001_empty_foundation")
        assert "staff_users" not in inspect(engine).get_table_names(
            schema="face_moment"
        )
        alembic_command.upgrade(alembic_config, "head")
        assert "staff_users" in inspect(engine).get_table_names(
            schema="face_moment"
        )

        invalid_role = subprocess.run(
            [
                command,
                "--username",
                supplied_username,
                "--role",
                "observer",
                "--password-stdin",
            ],
            input=f"{supplied_secret}\n",
            capture_output=True,
            check=False,
            text=True,
        )
        assert invalid_role.returncode != 0

        created = subprocess.run(
            [
                command,
                "--username",
                supplied_username,
                "--role",
                "photographer",
                "--password-stdin",
            ],
            input=f"{supplied_secret}\n",
            capture_output=True,
            check=False,
            text=True,
        )
        assert created.returncode == 0, created.stderr

        with engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT id, username, password_hash, role, active,
                               created_at, password_changed_at, deactivated_at
                        FROM face_moment.staff_users
                        WHERE username = :username
                        """
                    ),
                    {"username": username_marker},
                )
                .mappings()
                .one()
            )

        assert row["username"] == username_marker
        assert row["role"] == "photographer"
        assert row["active"] is True
        assert row["created_at"] is not None
        assert row["password_changed_at"] is not None
        assert row["deactivated_at"] is None
        assert row["password_hash"].startswith("$argon2id$")
        assert row["password_hash"] != supplied_secret
        assert verify_password(row["password_hash"], supplied_secret)

        duplicate = subprocess.run(
            [
                command,
                "--username",
                username_marker.swapcase(),
                "--role",
                "photographer",
                "--password-stdin",
            ],
            input=f"{second_secret}\n",
            capture_output=True,
            check=False,
            text=True,
        )
        assert duplicate.returncode != 0

        with engine.connect() as connection:
            principal_count = connection.execute(
                text(
                    "SELECT count(*) FROM face_moment.staff_users "
                    "WHERE username = :username"
                ),
                {"username": username_marker},
            ).scalar_one()

        assert principal_count == 1
        retained_output = "\n".join(
            (
                invalid_role.stdout,
                invalid_role.stderr,
                created.stdout,
                created.stderr,
                duplicate.stdout,
                duplicate.stderr,
            )
        )
        assert supplied_secret not in retained_output
        assert second_secret not in retained_output
        assert row["password_hash"] not in retained_output
        print(
            "database_projection="
            f"username={row['username']} role={row['role']} active=true "
            "password_hash_kind=argon2id unique_normalized=true redaction=clean"
        )
    finally:
        if inspect(engine).has_table("staff_users", schema="face_moment"):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "DELETE FROM face_moment.staff_users "
                        "WHERE username = :username"
                    ),
                    {"username": username_marker},
                )
        engine.dispose()

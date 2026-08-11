from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.settings import Settings
from face_moment.platform.auth.principals import (
    DuplicateUsernameError,
    InvalidPasswordError,
    InvalidUsernameError,
    StaffRole,
    StaffUserNotFoundError,
    provision_staff_user,
)
from face_moment.platform.auth.sessions import (
    deactivate_staff_user_and_revoke_sessions,
    reset_staff_password_and_revoke_sessions,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision or manage one Face Moment staff principal."
    )
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--role",
        choices=tuple(role.value for role in StaffRole),
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--reset-password", action="store_true")
    action.add_argument("--deactivate", action="store_true")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="read one password line from standard input instead of prompting",
    )
    return parser


def _read_password(*, from_stdin: bool) -> str:
    if not from_stdin:
        return getpass.getpass("Password: ")
    return sys.stdin.readline().removesuffix("\n").removesuffix("\r")


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            try:
                if args.reset_password:
                    principal = reset_staff_password_and_revoke_sessions(
                        session,
                        username=args.username,
                        password=_read_password(from_stdin=args.password_stdin),
                    )
                    output = (
                        "staff_lifecycle=action=password_reset "
                        f"username={principal.username} active=true sessions_revoked=all"
                    )
                elif args.deactivate:
                    principal = deactivate_staff_user_and_revoke_sessions(
                        session,
                        username=args.username,
                    )
                    output = (
                        "staff_lifecycle=action=deactivation "
                        f"username={principal.username} active=false sessions_revoked=all"
                    )
                else:
                    if args.role is None:
                        parser.error("--role is required when provisioning")
                    principal = provision_staff_user(
                        session,
                        username=args.username,
                        password=_read_password(from_stdin=args.password_stdin),
                        role=StaffRole(args.role),
                    )
                    output = (
                        "provisioned_staff="
                        f"username={principal.username} role={principal.role.value} "
                        "active=true password_hash_kind=argon2id"
                    )
            except (
                InvalidUsernameError,
                InvalidPasswordError,
                StaffUserNotFoundError,
            ) as error:
                parser.error(str(error))
            except DuplicateUsernameError as error:
                parser.error(f"username already exists: {error}")
    finally:
        engine.dispose()

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

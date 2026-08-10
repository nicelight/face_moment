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
    provision_staff_user,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision one Face Moment staff principal."
    )
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--role",
        required=True,
        choices=tuple(role.value for role in StaffRole),
    )
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
    password = _read_password(from_stdin=args.password_stdin)
    engine = create_engine(Settings.from_env().database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            try:
                principal = provision_staff_user(
                    session,
                    username=args.username,
                    password=password,
                    role=StaffRole(args.role),
                )
            except (InvalidUsernameError, InvalidPasswordError) as error:
                parser.error(str(error))
            except DuplicateUsernameError as error:
                parser.error(f"username already exists: {error}")
    finally:
        engine.dispose()

    print(
        "provisioned_staff="
        f"username={principal.username} role={principal.role.value} "
        "active=true password_hash_kind=argon2id"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

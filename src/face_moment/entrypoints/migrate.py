from __future__ import annotations

from alembic import command
from alembic.config import Config

from face_moment.infrastructure.object_store import ensure_bucket
from face_moment.infrastructure.readiness import wait_for_dependencies
from face_moment.infrastructure.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    wait_for_dependencies(settings, require_bucket=False)
    command.upgrade(Config("alembic.ini"), "head")
    ensure_bucket(settings)


if __name__ == "__main__":
    main()


from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import Settings
from face_moment.promo.retention import PromoRetentionService


def main() -> None:
    settings = Settings.from_env()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            outcome = PromoRetentionService(
                session,
                object_store=PrivateObjectStore(settings),
            ).run()
            print(f"retention_cleanup state={outcome.state} exit_code={outcome.exit_code}")
            if outcome.error is not None:
                print(f"retention_cleanup error={outcome.error}")
            if outcome.exit_code:
                raise SystemExit(outcome.exit_code)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

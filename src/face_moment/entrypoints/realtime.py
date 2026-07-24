from __future__ import annotations

from fastapi import FastAPI

from face_moment.entrypoints.common import create_role_app, run
from face_moment.processing.face_engine import FakeFaceEngine


def create_app(engine: FakeFaceEngine | None = None) -> FastAPI:
    return create_role_app("RealtimeFaceService", engine=engine or FakeFaceEngine())


app = create_app()


def main() -> None:
    run(app, 8002)


if __name__ == "__main__":
    main()


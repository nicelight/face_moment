from __future__ import annotations

from fastapi import FastAPI

from face_moment.entrypoints.common import create_role_app, run


def create_app() -> FastAPI:
    return create_role_app("BackgroundPhotoWorker")


app = create_app()


def main() -> None:
    run(app, 8001)


if __name__ == "__main__":
    main()


"""Explicit post-migration deployment command; never part of role startup."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from face_moment.processing.model_admission import ModelAdmissionError
from face_moment.serving_control.spa_creation import initialize_default_spa


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with Session(engine) as session, session.begin():
            venue = initialize_default_spa(session)
    except ModelAdmissionError as error:
        raise SystemExit(f"Инициализация площадки отменена: {error}. Проверьте SFACE_* и файлы YuNet/SFace.") from error
    finally:
        engine.dispose()
    print("Площадки уже существуют; изменений нет." if venue is None else "Создана площадка «СПА Сибирь 1».")


if __name__ == "__main__":
    main()

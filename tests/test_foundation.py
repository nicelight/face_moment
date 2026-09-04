from __future__ import annotations

from face_moment.entrypoints.backend import create_app as create_backend
from face_moment.entrypoints.background_worker import create_app as create_worker
from face_moment.entrypoints.realtime import create_app as create_realtime
from face_moment.infrastructure.database import APP_SCHEMA, Base
from face_moment.processing.face_engine import FakeFaceEngine


def test_one_metadata_owns_all_loaded_application_tables() -> None:
    assert Base.metadata.schema == APP_SCHEMA
    assert Base.metadata.tables
    assert all(table.metadata is Base.metadata for table in Base.metadata.tables.values())
    assert all(table.schema == APP_SCHEMA for table in Base.metadata.tables.values())


def test_fake_face_engine_warmup_never_loads_a_model() -> None:
    engine = FakeFaceEngine()
    assert engine.ready is False
    engine.warmup()
    assert engine.ready is True


def test_three_role_composition_roots_are_separately_named() -> None:
    assert create_backend().title == "Face Moment backend"
    assert create_worker().title == "Face Moment BackgroundPhotoWorker"
    assert create_realtime().title == "Face Moment RealtimeFaceService"

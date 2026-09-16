"""Fresh deployment and staff creation against PostgreSQL and real SFace files."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import hashlib
from pathlib import Path
import threading

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.entrypoints.initialize_venue import main as initialize_venue
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.processing.revisions import PipelineCode, PipelineRevision
from face_moment.serving_control.ingest_target import Spa
from face_moment.serving_control.realtime_context import ReferenceSearchSettings, RealtimeContextRepository
from face_moment.serving_control.spa_creation import create_initialized_spa, initialize_default_spa
from tests.disposable_postgresql import disposable_postgresql_engine
from tests.serving_control.test_active_search_date import _login, _request


@pytest.fixture
def initial_venue(monkeypatch):
    with disposable_postgresql_engine("initial_venue") as engine:
        metadata = {
            "DETECTOR_PATH": str(Path("models/opencv_sface/yunet.onnx").resolve()),
            "RECOGNIZER_PATH": str(Path("models/opencv_sface/sface.onnx").resolve()),
            "DETECTOR_ID": "yunet", "DETECTOR_VERSION": "2023mar",
            "RECOGNIZER_ID": "sface", "RECOGNIZER_VERSION": "2021dec",
            "PREPROCESSING_VERSION": "opencv-photo-640-v2",
            "ALIGNMENT_VERSION": "opencv-aligncrop-v1", "NORMALIZATION_VERSION": "l2-v1",
            "EMBEDDING_DIMENSION": "128",
        }
        for key, value in metadata.items():
            monkeypatch.setenv("SFACE_" + key, value)
        account = {"username": "initial-operator", "password": "initial-venue-test-password"}
        with Session(engine) as session:
            provision_staff_user(session, **account, role=StaffRole.OPERATOR)
        app = create_app()
        app.state.role_state["session_factory"] = lambda: Session(engine)
        cookies = _login(app, account)
        yield engine, app, cookies, metadata


def _create(app, cookies, **overrides):
    return _request(app, "POST", "/api/serving/spas", cookies=cookies,
        headers={"X-CSRF-Token": cookies["fm_staff_csrf"]},
        body={"name": "Первая из UI", "timezone": "Etc/GMT-7", **overrides})


def _snapshot(engine):
    with engine.connect() as connection:
        return [connection.execute(select(model.__table__).order_by(*model.__table__.primary_key)).all()
                for model in (PipelineRevision, Spa, ReferenceSearchSettings)]


@pytest.mark.parametrize("entry", ["deployment", "api"])
def test_first_venue_uses_actual_model_and_requested_defaults(initial_venue, entry):
    engine, app, cookies, metadata = initial_venue
    if entry == "deployment":
        initialize_venue()
    else:
        code, headers, _ = _create(app, cookies)
        assert code == 201 and headers["cache-control"] == "no-store"
    with Session(engine) as session:
        spa = session.scalars(select(Spa)).one()
        revision = session.scalars(select(PipelineRevision)).one()
        settings = session.scalars(select(ReferenceSearchSettings)).one()
        assert spa.name == ("СПА Сибирь 1" if entry == "deployment" else "Первая из UI")
        assert spa.timezone == "Etc/GMT-7" and spa.active and spa.search_today
        assert spa.active_visit_date is None and spa.active_visit_date_to is None
        assert (spa.photo_yunet_threshold, spa.capture_blazeface_threshold) == (.7, .5)
        assert spa.serving_pipeline_revision_id == revision.id
        assert revision.pipeline_code == PipelineCode.OPENCV_SFACE
        digest = hashlib.sha256()
        for key in ("DETECTOR_PATH", "RECOGNIZER_PATH"):
            content = Path(metadata[key]).read_bytes()
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
        assert revision.weights_sha256 == digest.hexdigest()
        for key in ("DETECTOR_ID", "DETECTOR_VERSION", "RECOGNIZER_ID", "RECOGNIZER_VERSION",
                    "PREPROCESSING_VERSION", "ALIGNMENT_VERSION", "NORMALIZATION_VERSION"):
            assert getattr(revision, key.lower()) == metadata[key]
        assert revision.embedding_dimension == 128 and revision.validated_at is not None
        assert settings.spa_id == spa.id and settings.pipeline_code == "opencv_sface"
        assert settings.reference_threshold == .38 and settings.min_query_face_quality == .5
        assert settings.quality_settings == {"version": 1}
    page = _request(app, "GET", "/staff/spas", cookies=cookies)[2]
    assert '<option value="Etc/GMT-7" selected>' in page


@pytest.mark.parametrize("failure", ["missing_setting", "missing_file", "corrupt_file", "dimension", "invalid_dimension"])
def test_model_failure_rolls_back_everything(initial_venue, monkeypatch, tmp_path, failure):
    engine, app, cookies, _ = initial_venue
    if failure == "missing_setting":
        monkeypatch.delenv("SFACE_DETECTOR_VERSION")
    elif failure == "missing_file":
        monkeypatch.setenv("SFACE_DETECTOR_PATH", str(tmp_path / "missing.onnx"))
    elif failure == "corrupt_file":
        corrupt = tmp_path / "corrupt.onnx"
        corrupt.write_bytes(b"not an ONNX model")
        monkeypatch.setenv("SFACE_RECOGNIZER_PATH", str(corrupt))
    else:
        monkeypatch.setenv("SFACE_EMBEDDING_DIMENSION", "3" if failure == "dimension" else "invalid")
    with pytest.raises(SystemExit, match="Инициализация площадки отменена"):
        initialize_venue()
    code, _, response = _create(app, cookies)
    assert code == 503 and "SFace" in response["detail"]
    assert _snapshot(engine) == [[], [], []]


def test_existing_venues_are_untouched_and_new_venue_reuses_revision(initial_venue, monkeypatch):
    engine, app, cookies, _ = initial_venue
    initialize_venue()
    with Session(engine) as session, session.begin():
        spa = session.scalars(select(Spa)).one()
        spa.name = "Существующая площадка"
        spa.timezone = "UTC"
        spa.photo_yunet_threshold = .91
        spa.capture_blazeface_threshold = .61
        spa.search_today = False
        spa.active_visit_date = date(2025, 1, 1)
        spa.active_visit_date_to = date(2025, 2, 1)
        settings = session.scalars(select(ReferenceSearchSettings)).one()
        settings.reference_threshold = .45
        settings.min_query_face_quality = .6
        settings.quality_settings = {"version": 2}
    before = _snapshot(engine)
    # Existing databases do not need SFace configuration (may serve Buffalo).
    monkeypatch.delenv("SFACE_DETECTOR_PATH")
    initialize_venue()
    assert _snapshot(engine) == before
    assert _create(app, cookies)[0] == 201
    after = _snapshot(engine)
    assert after[0] == before[0]
    assert before[1][0] in after[1] and before[2][0] in after[2]
    with Session(engine) as session, session.begin():
        spas = session.scalars(select(Spa)).all()
        assert len(spas) == 2
        assert len({spa.serving_pipeline_revision_id for spa in spas}) == 1
        for spa in spas:
            spa.active = False
    inactive = _snapshot(engine)
    initialize_venue()
    assert _snapshot(engine) == inactive
    assert _create(app, cookies)[0] == 409
    assert _snapshot(engine) == inactive


def test_invalid_input_rolls_back_validated_revision_and_auth_precedes_model(initial_venue, monkeypatch):
    engine, app, cookies, _ = initial_venue
    assert _create(app, cookies, timezone="Mars/Nowhere")[0] == 422
    assert _snapshot(engine) == [[], [], []]
    monkeypatch.delenv("SFACE_DETECTOR_PATH")
    assert _request(app, "POST", "/api/serving/spas", body={"name": "Test", "timezone": "UTC"})[0] == 401
    assert _request(app, "POST", "/api/serving/spas", cookies=cookies,
        body={"name": "Test", "timezone": "UTC"})[0] == 403
    assert _snapshot(engine) == [[], [], []]


def test_concurrent_deployment_and_api_share_one_revision(initial_venue):
    engine, _, _, _ = initial_venue
    barrier = threading.Barrier(2)
    def create(default):
        barrier.wait(timeout=10)
        with Session(engine) as session, session.begin():
            if default:
                initialize_default_spa(session)
            else:
                create_initialized_spa(session, name="Concurrent UI", timezone="UTC")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(create, [True, False]))
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PipelineRevision)) == 1
        count = session.scalar(select(func.count()).select_from(Spa))
        assert count in (1, 2)
        assert session.scalar(select(func.count()).select_from(ReferenceSearchSettings)) == count


def test_failure_after_settings_flush_rolls_back_all_three_records(initial_venue, monkeypatch):
    engine, app, cookies, _ = initial_venue
    provision = RealtimeContextRepository.provision_reference_settings
    def fail_after_flush(self, **kwargs):
        provision(self, **kwargs)
        raise ValueError("injected failure after all three records were flushed")
    monkeypatch.setattr(RealtimeContextRepository, "provision_reference_settings", fail_after_flush)
    assert _create(app, cookies)[0] == 422
    assert _snapshot(engine) == [[], [], []]

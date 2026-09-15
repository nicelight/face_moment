"""Current-model manual thresholds against disposable PostgreSQL and the real app."""

import ast
from datetime import datetime, timezone
from pathlib import Path
import uuid

import pytest
from sqlalchemy.orm import Session

from face_moment.diagnostics.calibration_runs import CalibrationRun
from face_moment.processing import PipelineCode
from face_moment.processing.worker_runtime import BackgroundPhotoWorker
from face_moment.serving_control.ingest_target import Spa
from face_moment.serving_control.realtime_context import RealtimeContextRepository
from tests.serving_control.test_active_search_date import (
    _Fixture, _login, _request, active_search_date_fixture,
)


def _provision(f: _Fixture) -> None:
    with Session(f.engine) as session:
        session.get(Spa, f.inaccessible_spa_id).active = True
        for spa_id, threshold in ((f.spa_id, 0.45), (f.inaccessible_spa_id, 0.7)):
            RealtimeContextRepository(session).provision_reference_settings(
                spa_id=spa_id, pipeline_code=PipelineCode.OPENCV_SFACE,
                reference_threshold=threshold, min_query_face_quality=0.6,
                quality_settings={"version": 1},
            )
        RealtimeContextRepository(session).provision_reference_settings(
            spa_id=f.spa_id, pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
            reference_threshold=0.82, min_query_face_quality=0.6, quality_settings={"version": 1},
        )
        session.commit()


@pytest.mark.parametrize("role", ["operator", "developer"])
def test_read_save_reopen_and_venue_model_isolation(active_search_date_fixture: _Fixture, role: str) -> None:
    f = active_search_date_fixture
    _provision(f)
    cookies = _login(f.app, getattr(f, role))
    headers = {"X-CSRF-Token": cookies["fm_staff_csrf"]}
    path = f"/api/serving/spas/{f.spa_id}/similarity-threshold"
    code, response_headers, current = _request(f.app, "GET", path, cookies=cookies)
    assert code == 200 and response_headers["cache-control"] == "no-store"
    assert current["spa_id"] == str(f.spa_id) and current["threshold"] == 0.45
    assert current["pipeline_code"] == PipelineCode.OPENCV_SFACE.value
    with Session(f.engine) as session:
        assert current["pipeline_revision_id"] == str(session.get(Spa, f.spa_id).serving_pipeline_revision_id)
    payload = {key: current[key] for key in ("threshold", "pipeline_revision_id", "settings_revision")}
    payload["threshold"] = 0.58
    code, _, saved = _request(f.app, "PUT", path, cookies=cookies, headers=headers, body=payload)
    assert code == 200 and saved["threshold"] == 0.58
    assert saved["settings_revision"] > current["settings_revision"]
    assert _request(f.app, "GET", path, cookies=cookies)[2] == saved
    assert _request(f.app, "GET", path.replace(str(f.spa_id), str(f.inaccessible_spa_id)), cookies=cookies)[2]["threshold"] == 0.7
    assert _request(f.app, "PUT", path, cookies=cookies, headers=headers, body=payload)[0] == 409
    payload["settings_revision"] = saved["settings_revision"]
    payload["pipeline_revision_id"] = str(uuid.uuid4())
    assert _request(f.app, "PUT", path, cookies=cookies, headers=headers, body=payload)[0] == 409
    with Session(f.engine) as session:
        record = RealtimeContextRepository(session).get_reference_settings(spa_id=f.spa_id, pipeline_code=PipelineCode.OPENCV_SFACE)
        assert record.min_query_face_quality == 0.6 and record.quality_settings == {"version": 1}
        assert RealtimeContextRepository(session).get_reference_settings(
            spa_id=f.spa_id, pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
        ).reference_threshold == 0.82
    page = _request(f.app, "GET", "/staff/spas", cookies=cookies)[2]
    assert 'data-similarity-threshold' in page and 'Изменить порог сходства' in page
    assert 'определяет сходство лиц во время  Захвата на выходе с фотографиями от фотографов. По умолчанию 0.38' in page
    assert 'Определяет сходство лиц при поиске, а не обнаружение лиц детекторами.' not in page
    assert '/staff/calibrations' not in page


def test_missing_settings_validation_and_access(active_search_date_fixture: _Fixture) -> None:
    f = active_search_date_fixture
    cookies = _login(f.app, f.operator)
    path = f"/api/serving/spas/{f.spa_id}/similarity-threshold"
    assert _request(f.app, "GET", path, cookies=cookies)[0] == 503
    _provision(f)
    current = _request(f.app, "GET", path, cookies=cookies)[2]
    payload = {key: current[key] for key in ("threshold", "pipeline_revision_id", "settings_revision")}
    photographer = _login(f.app, f.photographer)
    for account, csrf, code in (({}, "", 401), (cookies, "wrong", 403),
                               (photographer, photographer["fm_staff_csrf"], 403)):
        assert _request(f.app, "PUT", path, cookies=account, headers={"X-CSRF-Token": csrf}, body=payload)[0] == code
    assert _request(f.app, "GET", path, cookies={})[0] == 401
    assert _request(f.app, "GET", path, cookies=photographer)[0] == 403
    for value in (-1.1, 1.1, True, "0.5", None, "NaN", "Infinity", float("nan"), float("inf"), -float("inf")):
        assert _request(f.app, "PUT", path, cookies=cookies,
            headers={"X-CSRF-Token": cookies["fm_staff_csrf"]}, body={**payload, "threshold": value})[0] == 422


def test_old_http_and_default_worker_leave_calibration_records_untouched(active_search_date_fixture: _Fixture) -> None:
    f = active_search_date_fixture
    cookies = _login(f.app, f.developer)
    ids = [uuid.uuid4(), uuid.uuid4()]
    with Session(f.engine) as session:
        revision_id = session.get(Spa, f.spa_id).serving_pipeline_revision_id
        for run_id, status in zip(ids, ("requested", "running")):
            session.add(CalibrationRun(id=run_id, requested_by_staff_id=uuid.uuid4(),
                status=status, dataset_snapshot={"preserve": True}, dataset_sha256="0" * 64,
                started_at=datetime.now(timezone.utc) if status == "running" else None))
        session.commit()
    for suffix in ("", "/threshold", f"/{ids[0]}", f"/{ids[0]}?compare_to={ids[1]}"):
        for method in ("GET", "POST", "PUT", "DELETE"):
            code, _, body = _request(f.app, method, "/staff/calibrations" + suffix,
                cookies=cookies, headers={"X-CSRF-Token": cookies["fm_staff_csrf"]}, body={})
            assert code == 410 and "отключена" in body["detail"]
    # Check production composition as well as the real default loop below.
    tree = ast.parse(Path("src/face_moment/entrypoints/background_worker.py").read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "BackgroundPhotoWorker"]
    assert len(calls) == 1
    assert not {"claim_requested_calibration", "execute_claimed_calibration", "interrupt_running_calibrations"} & {kw.arg for kw in calls[0].keywords}
    class NoPhotos:
        def process_claimed(self, **kwargs):
            raise AssertionError("isolated database contains no photos")
    worker = BackgroundPhotoWorker(session_factory=lambda: Session(f.engine),
        orchestrator=NoPhotos(), bound_pipeline_revision_id=revision_id)
    worker.recover_startup()
    assert worker.process_one() is False
    with Session(f.engine) as session:
        for run_id, status in zip(ids, ("requested", "running")):
            run = session.get(CalibrationRun, run_id)
            assert run.status == status and run.dataset_snapshot == {"preserve": True}
            assert run.result_bundle is None and run.finished_at is None

"""TASK-106 real detail actions over disposable synthetic evidence only."""
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.diagnostics.calibration_runs import CalibrationRunRepository
from face_moment.diagnostics.evidence import DiagnosticEvidenceProvider, DiagnosticEvidenceRepository
from face_moment.diagnostics.ground_truth_annotations import GroundTruthAnnotation, GroundTruthAnnotationProvider
from face_moment.platform.auth.sessions import revoke_current_browser_session
from face_moment.promo.attempt import PromoAttempt
from face_moment.promo.retention import run_retention_cleanup
from tests.diagnostics.test_calibration_http import (
    disposable_calibration_http, CalibrationHttpFixture, _request, _login_cookies,
)


def test_selected_current_case_survives_cleanup_then_confirmed_delete_and_repeat(
    disposable_calibration_http: CalibrationHttpFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = disposable_calibration_http
    with Session(fixture.engine) as session:
        evidence = DiagnosticEvidenceRepository(session)
        manifest = {
            "schema_version": 1,
            "identity": {"attempt_id": str(fixture.attempt_id), "client_attempt_id": str(uuid.uuid4())},
            "serving": {"pipeline_code": "opencv_sface", "threshold": 0.71, "quality_settings": {"version": 1}},
            "detections": [
                {"occurrence_index": 0, "rank": 1, "reference_quality_score": 0.81, "matches": [{"photo_id": str(fixture.photo_id), "cosine_similarity": 0.91}]},
                {"occurrence_index": 1, "rank": 2, "reference_quality_score": 0.22, "matches": []},
            ],
            "artifacts": [],
        }
        evidence.write_bundle(attempt_id=fixture.attempt_id, ordinary_manifest=manifest, completeness="incomplete", gap_reason="response_receipt_missing")
        annotations = GroundTruthAnnotationProvider(session)
        selected = annotations.create(attempt_id=fixture.attempt_id, target_kind="detection", detection_occurrence_index=0, participant_name="Synthetic Selected 106", outcome="correct")
        unselected = annotations.create(attempt_id=fixture.attempt_id, target_kind="detection", detection_occurrence_index=1, participant_name="Synthetic Unselected 106", outcome="false")
        selected_id, unselected_id = selected.annotation_id, unselected.annotation_id
        run = CalibrationRunRepository(session).create_requested(requested_by_staff_id=uuid.uuid4(), dataset_snapshot={
            "spa_id": str(fixture.spa_id), "selected_attempt_ids": [str(fixture.attempt_id)],
            "attempts": [{"attempt_id": str(fixture.attempt_id), "annotations": [{"annotation_id": str(selected_id)}, {"annotation_id": str(unselected_id)}]}],
        })
        run_id = run.id
        # A correction after run creation must be resolved from the current owner row.
        annotations.correct(attempt_id=fixture.attempt_id, annotation_id=selected_id,
            participant_name="Synthetic Current 106", outcome="correct")
        session.commit()
    path = f"/staff/calibrations/{run_id}"
    developer = fixture.cookies["developer"]
    csrf = {"X-CSRF-Token": developer["fm_staff_csrf"]}
    def post(action, *, form=None, cookies=developer, headers=csrf, target=path):
        return _request(fixture.app, "POST", target, cookies=cookies, headers=headers,
            form=form or {"action": action, "selection_key": str(selected_id), "confirmation": action})

    # First assertion is the prospective claim probe, before any production edit.
    promoted = post("promote")
    assert (promoted.status_code, promoted.body) == (303, "")
    with Session(fixture.engine) as session:
        stored = DiagnosticEvidenceRepository(session).require(fixture.attempt_id)
        subset = stored.promoted_subset
        assert subset == {
            "schema_version": 1,
            "parameters": manifest["serving"],
            "scores": manifest["detections"][:1],
            "annotations": [{"annotation_id": str(selected_id), "attempt_id": str(fixture.attempt_id), "target_kind": "detection", "detection_occurrence_index": 0, "participant_name": "Synthetic Current 106", "outcome": "correct"}],
        }
        promoted_at = stored.promoted_at
        assert stored.ordinary_manifest == manifest
        assert str(unselected_id) not in str(subset)
        assert "Synthetic Unselected" not in str(subset)

    revoked = _login_cookies(fixture.engine, fixture.credentials["developer"])
    with Session(fixture.engine) as session:
        revoke_current_browser_session(session, session_token=revoked["fm_staff_session"], csrf_cookie_token=revoked["fm_staff_csrf"], csrf_header_token=revoked["fm_staff_csrf"])
    for action in ("promote", "delete_promoted"):
        for cookies, headers, expected in ((None, {}, 401), (fixture.cookies["operator"], {"X-CSRF-Token": fixture.cookies["operator"]["fm_staff_csrf"]}, 403), (fixture.cookies["photographer"], {"X-CSRF-Token": fixture.cookies["photographer"]["fm_staff_csrf"]}, 403), (revoked, {"X-CSRF-Token": revoked["fm_staff_csrf"]}, 401), (developer, {}, 403)):
            for target in (path, f"/staff/calibrations/{uuid.uuid4()}"):
                denied = post(action, cookies=cookies, headers=headers, target=target)
                assert (denied.status_code, denied.body, denied.headers["cache-control"]) == (expected, "", "no-store")
        for form, expected in (({"action": action, "selection_key": str(selected_id), "confirmation": "no"}, 422), ({"action": action, "selection_key": str(uuid.uuid4()), "confirmation": action}, 404), ({"action": action, "selection_key": str(selected_id), "confirmation": action, "parameters": "browser replacement"}, 422)):
            denied = post(action, form=form)
            assert (denied.status_code, denied.body) == (expected, "")
        with Session(fixture.engine) as session:
            stored = DiagnosticEvidenceRepository(session).require(fixture.attempt_id)
            assert (stored.promoted_subset, stored.promoted_at) == (subset, promoted_at)

    # An existing run may only select its own frozen keys, and promotion is SPA-bound.
    with Session(fixture.engine) as session:
        cross_run = CalibrationRunRepository(session).create_requested(
            requested_by_staff_id=uuid.uuid4(), dataset_snapshot={
                "spa_id": str(uuid.uuid4()),
                "attempts": [{"attempt_id": str(fixture.attempt_id),
                    "annotations": [{"annotation_id": str(selected_id)}]}],
            })
        cross_path = f"/staff/calibrations/{cross_run.id}"
        missing_id = uuid.uuid4()
        missing_run = CalibrationRunRepository(session).create_requested(
            requested_by_staff_id=uuid.uuid4(), dataset_snapshot={
                "spa_id": str(fixture.spa_id),
                "attempts": [{"attempt_id": str(missing_id),
                    "annotations": [{"annotation_id": str(selected_id)}]}],
            })
        missing_path = f"/staff/calibrations/{missing_run.id}"
        session.commit()
    for action in ("promote", "delete_promoted"):
        assert post(action, target=cross_path).status_code == 409
        assert post(action, target=missing_path).status_code == 404
        assert post(action, target=f"/staff/calibrations/{uuid.uuid4()}").status_code == 404

    original_delete = DiagnosticEvidenceProvider.delete_promoted_subset
    def fail_after_delete(self, **kwargs):
        original_delete(self, **kwargs)
        raise RuntimeError("synthetic private failure")
    with monkeypatch.context() as patch:
        patch.setattr(DiagnosticEvidenceProvider, "delete_promoted_subset", fail_after_delete)
        failed = post("delete_promoted")
        assert (failed.status_code, failed.body) == (500, "")
    with Session(fixture.engine) as session:
        stored = DiagnosticEvidenceRepository(session).require(fixture.attempt_id)
        assert (stored.promoted_subset, stored.promoted_at) == (subset, promoted_at)

    detail = _request(fixture.app, "GET", path, cookies=developer)
    assert detail.status_code == 200
    assert 'value="promote"' in detail.body and 'value="delete_promoted"' in detail.body
    assert 'name="selection_key"' in detail.body
    with Session(fixture.engine) as session:
        attempt = session.get(PromoAttempt, fixture.attempt_id)
        assert attempt is not None
        attempt.created_at = datetime.now(timezone.utc) - timedelta(days=91)
        session.commit()
        result = run_retention_cleanup(session, now=datetime.now(timezone.utc))
        assert result.exit_code == 0
    with Session(fixture.engine) as session:
        stored = DiagnosticEvidenceRepository(session).require(fixture.attempt_id)
        assert stored.ordinary_manifest is None
        assert stored.ordinary_expired_at is not None
        assert (stored.promoted_subset, stored.promoted_at) == (subset, promoted_at)
        assert not session.scalars(select(GroundTruthAnnotation).where(GroundTruthAnnotation.attempt_id == fixture.attempt_id)).all()
        assert session.get(PromoAttempt, fixture.attempt_id) is None
    assert post("promote").status_code == 409
    for _ in range(2):
        assert post("delete_promoted").status_code == 303
        with Session(fixture.engine) as session:
            stored = DiagnosticEvidenceRepository(session).require(fixture.attempt_id)
            assert stored.promoted_subset is None and stored.promoted_at is None
            assert stored.ordinary_manifest is None
            assert session.get(PromoAttempt, fixture.attempt_id) is None

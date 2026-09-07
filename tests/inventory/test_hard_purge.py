"""Fixed-snapshot purge acceptance against disposable PostgreSQL state."""

from __future__ import annotations

import json
import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from face_moment.inventory.hard_purge import InventoryHardPurge, InventoryHardPurgeRun
from face_moment.inventory.photo_persistence import Photo
from face_moment.infrastructure.object_store import PrivateObjectStore, ensure_bucket, s3_client
from face_moment.infrastructure.settings import Settings
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace, ProcessingRuntimeStatus
from face_moment.processing.worker_runtime import BackgroundPhotoWorker
from face_moment.platform.auth.sessions import StaffSession

from tests.inventory.test_photo_inventory_api import (
    _cookies,
    _request as _asgi_request,
    disposable_photo_inventory_state,
    _visibility_request,
)


def _request(app, method, path, *, cookies=None, headers=None, body=None):
    return _asgi_request(
        app, method, path, params={}, cookies=cookies, headers=headers,
        body=b"" if body is None else json.dumps(body).encode(),
    )


def test_restore_all_has_an_authorized_project_wide_surface(
    disposable_photo_inventory_state,
) -> None:
    fixture = disposable_photo_inventory_state
    cookies = _cookies(fixture.engine, fixture.accounts["operator"])
    status, _, body = _request(
        fixture.app, "POST", "/api/inventory/restore-all", cookies=cookies,
        headers={"x-csrf-token": cookies["fm_staff_csrf"]},
        body={"schema_version": 1},
    )
    assert status == 200
    assert body == {"schema_version": 1, "restored_count": 0, "excluded_snapshot_count": 0}


def test_purge_empty_snapshot_completes_and_survives_backend_recreation(
    disposable_photo_inventory_state,
) -> None:
    from face_moment.entrypoints.backend import create_app
    from sqlalchemy.orm import Session

    fixture = disposable_photo_inventory_state
    cookies = _cookies(fixture.engine, fixture.accounts["operator"])
    status, _, body = _request(
        fixture.app, "POST", "/api/inventory/hard-purge", cookies=cookies,
        headers={"x-csrf-token": cookies["fm_staff_csrf"]},
        body={"schema_version": 1, "confirmed": True},
    )
    assert status == 200
    assert body["run"]["state"] == "completed"
    assert body["run"]["completed"] == body["run"]["total"] == 0
    restarted = create_app()
    restarted.state.role_state["session_factory"] = lambda: Session(fixture.engine)
    assert _request(restarted, "GET", "/api/inventory/hard-purge", cookies=cookies)[2] == body


def test_purge_routes_enforce_session_and_role_before_mutation(
    disposable_photo_inventory_state,
) -> None:
    fixture = disposable_photo_inventory_state
    photographer = _cookies(fixture.engine, fixture.accounts["photographer"])
    for path in ("/api/inventory/restore-all", "/api/inventory/hard-purge"):
        payload = {"schema_version": 1}
        if path.endswith("hard-purge"):
            payload["confirmed"] = True
        assert _request(fixture.app, "POST", path, body=payload)[0] == 401
        assert _request(
            fixture.app, "POST", path, body=payload, cookies=photographer,
            headers={"x-csrf-token": photographer["fm_staff_csrf"]},
        )[0] == 403


def test_purge_persistence_is_one_singleton_table(disposable_photo_inventory_state) -> None:
    inspector = inspect(disposable_photo_inventory_state.engine)
    tables = inspector.get_table_names(schema="face_moment")
    assert "inventory_hard_purge_run" in tables
    assert [name for name in tables if "purge" in name] == ["inventory_hard_purge_run"]


def _mutate(fixture, cookies, path, body):
    return _request(fixture.app, "POST", path, body=body, cookies=cookies,
                    headers={"x-csrf-token": cookies["fm_staff_csrf"]})


def _confirm(fixture, cookies):
    status, headers, body = _mutate(fixture, cookies, "/api/inventory/hard-purge", {"schema_version": 1, "confirmed": True})
    assert status == 200
    assert headers["cache-control"] == "no-store"
    return body["run"]


def _run(fixture, cookies):
    status, headers, body = _request(fixture.app, "GET", "/api/inventory/hard-purge", cookies=cookies)
    assert status == 200
    assert headers["cache-control"] == "no-store"
    return body["run"]


def _rows(engine, tables):
    with engine.connect() as connection:
        return {
            table: sorted(json.dumps(row, sort_keys=True) for row in connection.execute(
                text(f'SELECT to_jsonb(t) FROM face_moment.{table} t')
            ).scalars())
            for table in tables
        }


_INVENTORY_STATE = ("photos", "inventory_hard_purge_run", "processing_runtime_status")
_RETAINED_STATE = ("promo_attempts", "promo_sessions", "diagnostic_evidence", "calibration_runs")


@pytest.fixture
def purge_media(disposable_photo_inventory_state, monkeypatch):
    """Two inactive targets, two other Photos, all media and retained foreign rows."""
    from face_moment.diagnostics.calibration_runs import CalibrationRun
    from face_moment.diagnostics.evidence import DiagnosticEvidence
    from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
    from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY
    from tests.processing.test_purge_cleanup import _attempt, _promo_session

    fixture = disposable_photo_inventory_state
    monkeypatch.setenv("S3_BUCKET", "task110-" + uuid.uuid4().hex)
    settings = Settings.from_env()
    ensure_bucket(settings)
    store = PrivateObjectStore(settings)
    client = s3_client(settings)
    now = datetime.now(UTC)
    targets = sorted(fixture.owned_photo_ids[:2])
    try:
        media = {}
        with Session(fixture.engine) as session:
            extra = PipelineRevisionRepository(session).publish_eligible(
                pipeline_code=PipelineCode.OPENCV_SFACE, validated_at=now, **PIPELINE_COMPATIBILITY,
            )
            photos = list(session.scalars(select(Photo).order_by(Photo.id)))
            for photo in photos:
                photo.is_active = photo.id not in targets
                keys = [photo.original_object_key]
                for revision_id in (photo.admission_pipeline_revision_id, extra.id):
                    state = session.get(PhotoPipelineState, (photo.id, revision_id))
                    preview = f"task110/{photo.id}/{revision_id}/preview.jpg"
                    thumbnail = f"task110/{photo.id}/{revision_id}/thumbnail.jpg"
                    keys.extend((preview, thumbnail))
                    if state is None:
                        state = PhotoPipelineState(photo_id=photo.id, pipeline_revision_id=revision_id,
                            status="ready", attempt_count=1, status_changed_at=now, searchable_at=now)
                        session.add(state)
                    state.preview_object_key = preview
                    state.thumbnail_object_key = thumbnail
                    face = session.scalar(select(PhotoFace).where(PhotoFace.photo_id == photo.id, PhotoFace.pipeline_revision_id == revision_id))
                    if face is None:
                        session.add(PhotoFace(photo_id=photo.id, pipeline_revision_id=revision_id,
                            face_index=0, bbox_x=1, bbox_y=1, bbox_w=2, bbox_h=2,
                            landmarks_json=[[1, 1]] * 5, detection_confidence=.9,
                            embedding=[1.] + [0.] * 127))
                media[photo.id] = keys
            attempt = _attempt(now=now)
            attempt.spa_id = fixture.spa_id
            promo = _promo_session(attempt=attempt, photo_id=targets[0], now=now)
            ordered = targets + [photo.id for photo in photos if photo.id not in targets]
            promo.session_result_photo_ids = ordered
            promo.teaser_photo_ids = ordered
            promo.visit_date = photos[0].visit_date
            promo.browser_first_opened_at = promo.browser_last_seen_at = now
            # The published session ticket is opaque fixture data, never logged.
            ticket = "A" * 43
            promo.qr_ticket_hash_sha256 = hashlib.sha256(ticket.encode()).digest()
            evidence = DiagnosticEvidence(attempt_id=attempt.id, completeness="complete",
                ordinary_manifest={"photos": [str(p) for p in targets]}, issue_tags=[], finalized_at=now)
            calibration = CalibrationRun(id=uuid.uuid4(), requested_by_staff_id=uuid.uuid4(),
                status="complete", dataset_snapshot={"selected_photo_ids": [str(p) for p in targets]},
                dataset_sha256="a" * 64, result_bundle={"retained": True},
                started_at=now, finished_at=now)
            session.add_all((attempt, promo, evidence, calibration))
            session.commit()
            revision_id = photos[0].admission_pipeline_revision_id
        for keys in media.values():
            for key in keys:
                store.put(key=key, body=b"synthetic-task110-media")
        yield fixture, store, {"targets": targets, "media": media, "ticket": ticket,
                               "revision_id": revision_id, "now": now}
    finally:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=settings.s3_bucket):
            for item in page.get("Contents", []):
                client.delete_object(Bucket=settings.s3_bucket, Key=item["Key"])
        client.delete_bucket(Bucket=settings.s3_bucket)


def test_fixed_snapshot_excludes_restore_and_late_deletes(purge_media):
    fixture, store, data = purge_media
    operator = _cookies(fixture.engine, fixture.accounts["operator"])
    developer = _cookies(fixture.engine, fixture.accounts["developer"])
    before = _rows(fixture.engine, _RETAINED_STATE)
    run = _confirm(fixture, operator)
    assert (run["state"], run["completed"], run["total"]) == ("confirmed_waiting", 0, 2)
    assert set(run) == {"run_id", "state", "completed", "total", "waiting_for", "confirmed_at", "started_at", "completed_at"}
    late = fixture.owned_photo_ids[2]
    assert _visibility_request(fixture.app, late, False, cookies=operator)[0] == 200
    snapshot_before = _rows(fixture.engine, _INVENTORY_STATE)
    assert _mutate(fixture, developer, "/api/inventory/hard-purge", {"schema_version": 1, "confirmed": True})[0] == 409
    for target in data["targets"]:
        assert _visibility_request(fixture.app, target, True, cookies=operator)[0] == 409
    assert _rows(fixture.engine, _INVENTORY_STATE) == snapshot_before
    assert _mutate(fixture, developer, "/api/inventory/restore-all", {"schema_version": 1})[2] == {
        "schema_version": 1, "restored_count": 1, "excluded_snapshot_count": 2}
    assert _mutate(fixture, developer, "/api/inventory/restore-all", {"schema_version": 1})[2]["restored_count"] == 0
    with Session(fixture.engine) as session:
        assert session.get(InventoryHardPurgeRun, 1).target_photo_ids == data["targets"]
        assert session.get(Photo, late).is_active
    purge = InventoryHardPurge(session_factory=lambda: Session(fixture.engine), object_store=store)
    assert purge.process_one() is True
    assert _run(fixture, operator)["completed"] == 1
    assert purge.process_one() is True
    assert _run(fixture, operator)["state"] == "completed"
    assert _rows(fixture.engine, _RETAINED_STATE) == before
    assert _visibility_request(fixture.app, late, False, cookies=operator)[0] == 200
    second = _confirm(fixture, developer)
    assert second["run_id"] != run["run_id"] and second["total"] == 1


def test_authorization_and_invalid_payloads_preserve_all_three_state_owners(purge_media):
    fixture, _, _ = purge_media
    operator = _cookies(fixture.engine, fixture.accounts["operator"])
    developer = _cookies(fixture.engine, fixture.accounts["developer"])
    photographer = _cookies(fixture.engine, fixture.accounts["photographer"])
    expired = _cookies(fixture.engine, fixture.accounts["operator"])
    revoked = _cookies(fixture.engine, fixture.accounts["operator"])
    with Session(fixture.engine) as session:
        for cookies, kind in ((expired, "expired"), (revoked, "revoked")):
            row = session.scalar(select(StaffSession).where(StaffSession.token_hash_sha256 == hashlib.sha256(cookies["fm_staff_session"].encode()).digest()))
            if kind == "expired":
                row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            else:
                row.revoked_at = datetime.now(UTC)
        session.commit()
    assert _run(fixture, operator) is None and _run(fixture, developer) is None
    before = _rows(fixture.engine, _INVENTORY_STATE)
    for cookies, expected in ((None, 401), ({"fm_staff_session": "invalid"}, 401),
                              (expired, 401), (revoked, 401), (photographer, 403)):
        assert _request(fixture.app, "GET", "/api/inventory/hard-purge", cookies=cookies)[0] == expected
        for path, payload in (("/api/inventory/restore-all", {"schema_version": 1}),
                              ("/api/inventory/hard-purge", {"schema_version": 1, "confirmed": True})):
            status, headers, _ = _request(fixture.app, "POST", path, cookies=cookies, body=payload,
                headers={"x-csrf-token": (cookies or {}).get("fm_staff_csrf", "")})
            assert status == expected and headers["cache-control"] == "no-store"
            assert _rows(fixture.engine, _INVENTORY_STATE) == before
    for path in ("/api/inventory/restore-all", "/api/inventory/hard-purge"):
        payload = {"schema_version": 1, **({"confirmed": True} if path.endswith("hard-purge") else {})}
        for cookie, headers in ((operator, {}), (operator, {"x-csrf-token": "bad"}),
                                ({"fm_staff_session": operator["fm_staff_session"]}, {"x-csrf-token": operator["fm_staff_csrf"]})):
            assert _request(fixture.app, "POST", path, body=payload, cookies=cookie, headers=headers)[0] == 403
            assert _rows(fixture.engine, _INVENTORY_STATE) == before
        bad_bodies = [{}, {**payload, "schema_version": True}, {**payload, "extra": 1}]
        if path.endswith("hard-purge"):
            bad_bodies += [{"schema_version": 1, "confirmed": False}, {"schema_version": 1, "confirmed": 1}]
        for body in bad_bodies:
            assert _mutate(fixture, operator, path, body)[0] == 422
            assert _rows(fixture.engine, _INVENTORY_STATE) == before
    assert _mutate(fixture, developer, "/api/inventory/restore-all", {"schema_version": 1})[0] == 200
    assert _confirm(fixture, developer)["state"] == "completed"


def test_two_concurrent_confirmations_freeze_one_run(purge_media):
    fixture, _, data = purge_media
    cookies = [_cookies(fixture.engine, fixture.accounts[role]) for role in ("operator", "developer")]
    barrier = Barrier(2)
    def confirm(cookie):
        barrier.wait(timeout=10)
        return _mutate(fixture, cookie, "/api/inventory/hard-purge", {"schema_version": 1, "confirmed": True})
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(confirm, cookies))
    assert sorted(result[0] for result in results) == [200, 409]
    with Session(fixture.engine) as session:
        rows = list(session.scalars(select(InventoryHardPurgeRun)))
        assert len(rows) == 1 and rows[0].target_photo_ids == data["targets"]


@pytest.mark.parametrize("operation,label", [("photo_processing", "Обработка фото"),
    ("calibration", "Калибровка"), ("retention_cleanup", "Очистка диагностических данных")])
def test_busy_worker_waits_without_preemption_then_purge_precedes_new_claims(purge_media, operation, label):
    fixture, store, data = purge_media
    from face_moment.processing.worker_claims import WorkerClaimRepository
    operator = _cookies(fixture.engine, fixture.accounts["operator"])
    calls = []
    class NoPhotos:
        def process_claimed(self, **kwargs):
            raise AssertionError("ordinary Photo must not preempt purge")
    purge = InventoryHardPurge(session_factory=lambda: Session(fixture.engine), object_store=store)
    worker = BackgroundPhotoWorker(session_factory=lambda: Session(fixture.engine),
        orchestrator=NoPhotos(), bound_pipeline_revision_id=data["revision_id"],
        process_inventory_purge=purge.process_one,
        claim_requested_calibration=lambda: calls.append("calibration-claim"))
    with Session(fixture.engine) as session:
        if operation == "calibration":
            WorkerClaimRepository(session, bound_pipeline_revision_id=data["revision_id"]).begin_calibration()
        else:
            runtime = session.get(ProcessingRuntimeStatus, 1)
            runtime.current_operation = operation
            runtime.operation_started_at = datetime.now(UTC)
        session.commit()
    _confirm(fixture, operator)
    before = _rows(fixture.engine, _INVENTORY_STATE)
    assert _run(fixture, operator)["waiting_for"] == label
    assert worker.process_one() is False
    assert _rows(fixture.engine, _INVENTORY_STATE) == before and calls == []
    # Release the supported existing operation; the next tick must serve purge.
    with Session(fixture.engine) as session:
        runtime = session.get(ProcessingRuntimeStatus, 1)
        runtime.current_operation = "idle"
        runtime.operation_started_at = None
        session.commit()
    assert worker.process_one() is True
    assert _run(fixture, operator)["completed"] == 1 and calls == []
    assert worker.process_one() is True
    assert _run(fixture, operator)["state"] == "completed"


class _Crash(BaseException):
    pass


def test_two_crash_points_resume_prefix_retain_foreign_state_and_skip_missing_media(purge_media):
    from face_moment.entrypoints.backend import create_app
    from face_moment.promo.qr_continuation import PhoneContinuationService
    fixture, store, data = purge_media
    operator = _cookies(fixture.engine, fixture.accounts["operator"])
    run = _confirm(fixture, operator)
    before = _rows(fixture.engine, _RETAINED_STATE)
    late = fixture.owned_photo_ids[2]
    assert _visibility_request(fixture.app, late, False, cookies=operator)[0] == 200

    def worker(crash=None):
        class CrashSession(Session):
            def commit(self):
                target_commit = any(isinstance(row, InventoryHardPurgeRun) and row.completed_count == 1 for row in self.dirty)
                if target_commit and crash == "before":
                    raise _Crash()
                super().commit()
                if target_commit and crash == "after":
                    raise _Crash()
        factory = lambda: CrashSession(fixture.engine)
        return BackgroundPhotoWorker(session_factory=lambda: Session(fixture.engine),
            orchestrator=object(), bound_pipeline_revision_id=data["revision_id"],
            process_inventory_purge=InventoryHardPurge(session_factory=factory, object_store=store).process_one)

    with pytest.raises(_Crash):
        worker("before").process_one()
    assert _run(fixture, operator)["completed"] == 0
    with Session(fixture.engine) as session:
        assert session.get(Photo, data["targets"][0]) is not None
    remaining_keys = store.list_keys(prefix="")
    assert not set(data["media"][data["targets"][0]]) & remaining_keys
    assert _rows(fixture.engine, _RETAINED_STATE) == before
    restarted = worker("after")
    restarted.recover_startup()
    with pytest.raises(_Crash):
        restarted.process_one()
    assert _run(fixture, operator)["completed"] == 1
    # Recreate both the HTTP process boundary and worker with fresh sessions.
    app = create_app()
    app.state.role_state["session_factory"] = lambda: Session(fixture.engine)
    projection = _request(app, "GET", "/api/inventory/hard-purge", cookies=operator)[2]["run"]
    assert projection["run_id"] == run["run_id"] and projection["completed"] == 1
    final_worker = worker()
    final_worker.recover_startup()
    assert final_worker.process_one() is True
    assert _run(fixture, operator)["completed"] == 2
    assert _run(fixture, operator)["state"] == "completed"
    assert _rows(fixture.engine, _RETAINED_STATE) == before
    with Session(fixture.engine) as session:
        assert session.get(InventoryHardPurgeRun, 1).target_photo_ids == data["targets"]
        for target in data["targets"]:
            assert session.get(Photo, target) is None
            assert session.scalar(select(PhotoFace).where(PhotoFace.photo_id == target)) is None
            assert session.scalar(select(PhotoPipelineState).where(PhotoPipelineState.photo_id == target)) is None
        assert session.get(Photo, late) is not None and session.get(Photo, late).is_active is False
        assert session.get(ProcessingRuntimeStatus, 1).current_operation == "idle"
        phone = PhoneContinuationService(session, object_store=store,
            qr_ticket_secret="task110-fixture", purchase_url="https://example.test/purchase")
        view = phone.read_session(data["ticket"], now=data["now"])
        assert view.n == 4 and view.teaser is not None
    remaining_keys = store.list_keys(prefix="")
    assert remaining_keys == {key for photo, keys in data["media"].items() if photo not in data["targets"] for key in keys}
    print("restart_matrix=before_commit:0,after_commit:1,resumed:2; owned_media_deleted; foreign_state_unchanged; issued_N=4")


def test_storage_failure_keeps_target_and_retry_converges(purge_media):
    fixture, store, data = purge_media
    operator = _cookies(fixture.engine, fixture.accounts["operator"])
    _confirm(fixture, operator)
    class UnavailableStore:
        def delete(self, *, key):
            raise OSError("synthetic storage failure")
    assert InventoryHardPurge(session_factory=lambda: Session(fixture.engine), object_store=UnavailableStore()).process_one() is False
    assert _run(fixture, operator)["completed"] == 0
    with Session(fixture.engine) as session:
        assert session.get(Photo, data["targets"][0]) is not None
        assert session.get(ProcessingRuntimeStatus, 1).current_operation == "hard_purge"
    purge = InventoryHardPurge(session_factory=lambda: Session(fixture.engine), object_store=store)
    assert purge.process_one() is True and purge.process_one() is True
    assert purge.process_one() is None


def test_migration_roundtrip_preserves_prerequisites_and_enforces_singleton_prefix(purge_media):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.exc import IntegrityError
    fixture, _, _ = purge_media
    before = _rows(fixture.engine, _RETAINED_STATE + ("photos", "photo_pipeline_states", "photo_faces"))
    command.downgrade(Config("alembic.ini"), "0021_calibration_runs")
    assert "inventory_hard_purge_run" not in inspect(fixture.engine).get_table_names(schema="face_moment")
    command.upgrade(Config("alembic.ini"), "0022_inventory_hard_purge_run")
    assert _rows(fixture.engine, _RETAINED_STATE + ("photos", "photo_pipeline_states", "photo_faces")) == before
    operator = _cookies(fixture.engine, fixture.accounts["operator"])
    _confirm(fixture, operator)
    for assignment in ("singleton_id = 2", "completed_count = -1", "completed_count = 3",
                       "state = 'completed'", "state = 'running'", "state = 'failed'"):
        with pytest.raises(IntegrityError), fixture.engine.begin() as connection:
            connection.execute(text("UPDATE face_moment.inventory_hard_purge_run SET " + assignment))
    assert _run(fixture, operator)["completed"] == 0


def test_upload_staged_before_confirmation_commits_during_purge(purge_media):
    from face_moment.inventory.admission import AdmissionCandidate, AtomicPhotoAdmission
    from face_moment.inventory.candidate_staging import CandidateStager
    from face_moment.inventory.validation import JpegValidationLimits, validate_jpeg_candidate
    from face_moment.serving_control.ingest_target import IngestTargetRepository
    from tests.inventory.test_photo_upload_api import _jpeg

    fixture, store, data = purge_media
    image = _jpeg()
    staged = CandidateStager(store).stage(image)
    with Session(fixture.engine) as session:
        target = IngestTargetRepository(session).resolve_ingest_target(fixture.spa_id)
        uploader = session.get(Photo, data['targets'][0]).uploader_id
    validated = validate_jpeg_candidate(image, visit_date=data['now'].date(),
        spa_timezone='Asia/Dushanbe', upload_started_at=data['now'],
        limits=JpegValidationLimits(1_000_000, 4096, 16_000_000))
    operator = _cookies(fixture.engine, fixture.accounts['operator'])
    _confirm(fixture, operator)
    purge = InventoryHardPurge(session_factory=lambda: Session(fixture.engine), object_store=store)
    assert purge.process_one() is True
    with Session(fixture.engine) as session:
        photo = AtomicPhotoAdmission(session).publish(ingest_target=target, uploader_id=uploader,
            candidate=AdmissionCandidate(staged_candidate=staged, validated_jpeg=validated))
        new_id = photo.id
        assert session.get(PhotoPipelineState, (new_id, target.pipeline_revision_id)).status == 'pending'
        assert session.get(ProcessingRuntimeStatus, 1).current_operation == 'hard_purge'
        assert new_id not in session.get(InventoryHardPurgeRun, 1).target_photo_ids
    assert purge.process_one() is True
    with Session(fixture.engine) as session:
        assert session.get(Photo, new_id).is_active
        assert session.get(PhotoPipelineState, (new_id, target.pipeline_revision_id)).status == 'pending'
    assert store.read(key=staged.key) == image


def test_purge_removes_derivatives_published_before_processing_crash(purge_media):
    from sqlalchemy import delete
    from tests.inventory.test_photo_upload_api import _jpeg
    from face_moment.processing.derivatives import (
        PrivatePhotoDerivativeCreator, DerivativeEncoding, DerivativeEncodingConfig,
        derivative_object_key,
    )
    from face_moment.processing.photo_orchestration import PhotoProcessingOrchestrator
    fixture, store, data = purge_media
    target = data['targets'][0]
    revision = data['revision_id']
    # Represent an in-flight processing claim: no terminal row/key publication.
    with Session(fixture.engine) as session:
        photo = session.get(Photo, target)
        photo.is_active = True
        original = photo.original_object_key
        state = session.get(PhotoPipelineState, (target, revision))
        for key in (state.preview_object_key, state.thumbnail_object_key):
            if key:
                store.delete(key=key)
        state.preview_object_key = state.thumbnail_object_key = None
        state.status = 'processing'
        state.searchable_at = None
        session.execute(delete(PhotoFace).where(PhotoFace.photo_id == target, PhotoFace.pipeline_revision_id == revision))
        runtime = session.get(ProcessingRuntimeStatus, 1)
        runtime.current_operation = 'photo_processing'
        runtime.operation_started_at = datetime.now(UTC)
        session.commit()
    store.put(key=original, body=_jpeg())
    creator = PrivatePhotoDerivativeCreator(store, encoding=DerivativeEncodingConfig(
        preview=DerivativeEncoding(128, 85), thumbnail=DerivativeEncoding(64, 85),
    ))
    class ProcessCrash(BaseException):
        pass
    class Adapter:
        pipeline_revision_id = revision
        def process_for_terminal(self, photo):
            from tests.processing.test_photo_orchestration import _terminal_face
            return (_terminal_face(),)
    class InterruptedProcessor(PhotoProcessingOrchestrator):
        def _publish_ready(self, **kwargs):
            raise ProcessCrash('process terminated after derivative IO before ready publication')
    processor = InterruptedProcessor(session_factory=lambda: Session(fixture.engine),
        object_store=store, sface_adapter=Adapter(), buffalo_adapter=Adapter(),
        derivative_creator=creator)
    with pytest.raises(ProcessCrash):
        processor.process_claimed(photo_id=target, pipeline_revision_id=revision)
    keys = {derivative_object_key(photo_id=target, pipeline_revision_id=revision, artifact_kind=kind)
            for kind in ('preview', 'thumbnail')}
    assert keys <= store.list_keys(prefix='')
    # Process stops here, before _publish_ready; same state survives restart.
    operator = _cookies(fixture.engine, fixture.accounts['operator'])
    assert _visibility_request(fixture.app, target, False, cookies=operator)[0] == 200
    _confirm(fixture, operator)
    factory = lambda: Session(fixture.engine)
    purge = InventoryHardPurge(session_factory=factory, object_store=store)
    worker = BackgroundPhotoWorker(session_factory=factory, orchestrator=object(),
        bound_pipeline_revision_id=revision, process_inventory_purge=purge.process_one)
    worker.recover_startup()
    assert worker.process_one() is True and worker.process_one() is True
    projection = _run(fixture, operator)
    assert projection['state'] == 'completed' and projection['completed'] == 2
    with factory() as session:
        assert session.get(Photo, target) is None
        assert session.scalar(select(PhotoPipelineState).where(PhotoPipelineState.photo_id == target)) is None
    leftovers = keys & store.list_keys(prefix='')
    print(f'purge_state=completed; progress=2/2; Photo/pipeline=absent; unpublished_derivative_objects_remaining={len(leftovers)}')
    assert not leftovers, 'AC005: deterministic preview/thumbnail survived completed purge after processing crash'

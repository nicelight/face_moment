"""Real PostgreSQL/MinIO/native SFace proof of the manual capture workflow."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any
import uuid

from alembic import command
from alembic.config import Config
import cv2
import numpy as np
import pytest
from skimage import data as sample_data
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from face_moment.diagnostics.capture_identity import (
    DiagnosticFaceLabel, DiagnosticPerson, compatible_examples, identify_capture,
)
from face_moment.diagnostics.evidence import DiagnosticEvidenceRepository
from face_moment.entrypoints import realtime
from face_moment.inventory.photo_persistence import Photo
from face_moment.platform.staff_datetime import STAFF_TIMEZONE
from face_moment.processing.derivatives import (
    DerivativeEncoding, DerivativeEncodingConfig, PrivatePhotoDerivativeCreator,
)
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.processing.persistence import PhotoFace, ProcessingRuntimeStatus
from face_moment.processing.reference_query import PreparedReferenceQuery
from face_moment.processing.revisions import PipelineCode, PipelineRevisionRepository
from face_moment.processing.sface_adapter import SFaceModelAssets, SFacePhotoAdapter
from face_moment.processing.terminal_publication import TerminalPublicationRepository
from face_moment.promo.attempt import PromoAttempt
from face_moment.promo.retention import run_retention_cleanup
from face_moment.serving_control.display_client_access import DisplayClientRepository
from face_moment.serving_control.display_client_auth import DisplayClientRateLimiter
from face_moment.serving_control.ingest_target import Spa
from face_moment.serving_control.realtime_context import RealtimeContextRepository
from tests.diagnostics.test_realtime_evidence import _manifest
from tests.inventory.test_staff_media_api import MediaFixture, media_state, request


def test_person_score_is_maximum_with_inclusive_threshold_and_no_revision_mix() -> None:
    revision = uuid.uuid4()
    first, second = uuid.uuid4(), uuid.uuid4()
    query = PreparedReferenceQuery(revision, np.array([1., 0.], dtype=np.float32))
    examples = [(first, "Одинаковое имя", np.array([0., 1.], dtype=np.float32)),
                (first, "Одинаковое имя", np.array([1., 0.], dtype=np.float32)),
                (second, "Одинаковое имя", np.array([.8, .6], dtype=np.float32))]
    found = identify_capture(query=query, examples=examples, revision_id=revision, threshold=1.)
    assert found["person_id"] == str(first)
    assert found["score"] == 1.
    assert [item["person_id"] for item in found["nearest_people"]] == [str(first), str(second)]
    below = identify_capture(query=query, examples=examples[2:], revision_id=revision, threshold=.9)
    assert below["person_id"] is None and below["reason"] == "below_threshold"
    assert below["identity_name"] is None
    assert below["nearest_people"] == [{"person_id": str(second), "identity_name": "Одинаковое имя", "score": pytest.approx(.8)}]
    assert below["score"] == pytest.approx(.8)
    assert identify_capture(query=query, examples=examples, revision_id=uuid.uuid4(), threshold=0.)["reason"] == "incompatible_revision"
    assert identify_capture(query=None, examples=examples, revision_id=revision, threshold=0., unavailable_reason="no_face")["reason"] == "no_face"


def test_three_nearest_are_distinct_people_sorted_even_below_threshold() -> None:
    revision = uuid.uuid4()
    query = PreparedReferenceQuery(revision, np.array([1., 0.], dtype=np.float32))
    people = [uuid.UUID(int=index) for index in range(1, 5)]
    examples = [(person, "Гость", np.array([score, (1 - score ** 2) ** .5], dtype=np.float32))
                for person, score in zip(people, (.5, .8, .8, .3))]
    examples.append((people[0], "Гость", np.array([.9, (1 - .9 ** 2) ** .5], dtype=np.float32)))
    found = identify_capture(query=query, examples=examples, revision_id=revision, threshold=.95)
    assert found["person_id"] is None and found["reason"] == "below_threshold"
    assert [item["person_id"] for item in found["nearest_people"]] == [str(person) for person in people[:3]]
    assert [item["score"] for item in found["nearest_people"]] == pytest.approx([.9, .8, .8])
    recognized = identify_capture(query=query, examples=examples, revision_id=revision, threshold=.1)
    assert recognized["nearest_people"] == found["nearest_people"]
    assert recognized["reason"] == "recognized"


def _native_photo(fixture: MediaFixture) -> tuple[SFacePhotoAdapter, uuid.UUID, bytes]:
    assets = SFaceModelAssets(
        detector_path=Path("models/opencv_sface/yunet.onnx"), detector_id="yunet", detector_version="2023mar",
        recognizer_path=Path("models/opencv_sface/sface.onnx"), recognizer_id="sface", recognizer_version="2021dec",
        preprocessing_version="opencv-photo-640-v2", alignment_version="aligncrop-v1", normalization_version="l2-v1")
    if not assets.detector_path.is_file() or not assets.recognizer_path.is_file():
        pytest.skip("Native SFace assets are not available")
    image = cv2.cvtColor(sample_data.astronaut(), cv2.COLOR_RGB2BGR)
    original = cv2.imencode(".jpg", image)[1].tobytes()
    with Session(fixture.engine) as session:
        revision = PipelineRevisionRepository(session).publish_eligible(
            pipeline_code=PipelineCode.OPENCV_SFACE, validated_at=datetime.now(UTC),
            detector_id=assets.detector_id, detector_version=assets.detector_version,
            recognizer_id=assets.recognizer_id, recognizer_version=assets.recognizer_version,
            weights_sha256=assets.weights_sha256(), preprocessing_version=assets.preprocessing_version,
            alignment_version=assets.alignment_version, normalization_version=assets.normalization_version,
            embedding_dimension=128)
        adapter = SFacePhotoAdapter.from_configured_assets(revision=revision, assets=assets)
        faces = adapter.process_for_terminal(image)
        assert len(faces) == 1, "Native YuNet must find the test sample's face"
        photo = session.get(Photo, fixture.ids["no_faces"])
        assert photo is not None
        assert photo.admission_pipeline_revision_id != revision.id
        photo.width, photo.height = image.shape[1], image.shape[0]
        photo.original_byte_size = len(original)
        photo.accepted_at = datetime.now(UTC)
        photo.visit_date = datetime.now(STAFF_TIMEZONE).date()
        fixture.store.put(key=photo.original_object_key, body=original)
        derivatives = PrivatePhotoDerivativeCreator(fixture.store, encoding=DerivativeEncodingConfig(
            preview=DerivativeEncoding(1024, 85), thumbnail=DerivativeEncoding(320, 80))).create(
            photo_id=photo.id, pipeline_revision_id=revision.id,
            original_object_key=photo.original_object_key, decoded_original=image)
        fixture.keys.extend([derivatives.preview_object_key, derivatives.thumbnail_object_key])
        session.add(PhotoPipelineState(photo_id=photo.id, pipeline_revision_id=revision.id, status="processing"))
        runtime = session.get(ProcessingRuntimeStatus, 1)
        if runtime is None:
            runtime = ProcessingRuntimeStatus(singleton_id=1)
            session.add(runtime)
        runtime.current_operation = "photo_processing"
        runtime.operation_started_at = datetime.now(UTC)
        session.flush()
        TerminalPublicationRepository(session).publish_ready(photo_id=photo.id,
            pipeline_revision_id=revision.id, faces=faces, derivatives=derivatives)
        spa = session.get(Spa, fixture.spa_id)
        assert spa is not None
        spa.serving_pipeline_revision_id = revision.id
        session.commit()
        face_id = session.scalar(select(PhotoFace.id).where(PhotoFace.photo_id == photo.id,
            PhotoFace.pipeline_revision_id == revision.id))
        assert face_id is not None
    face = faces[0]
    size = 1.2 * max(face.bbox_w, face.bbox_h)
    center_x, center_y = face.bbox_x + face.bbox_w/2, face.bbox_y + face.bbox_h/2
    crop = image[max(0, int(center_y-size/2)):int(center_y+size/2),
                 max(0, int(center_x-size/2)):int(center_x+size/2)]
    return adapter, face_id, cv2.imencode(".jpg", crop)[1].tobytes()


def _realtime_request(fixture: MediaFixture, adapter: SFacePhotoAdapter, crops: list[bytes],
                       *, finalize_before_background: bool = False) -> tuple[int, uuid.UUID]:
    with Session(fixture.engine) as session:
        RealtimeContextRepository(session).provision_reference_settings(
            spa_id=fixture.spa_id, pipeline_code=PipelineCode.OPENCV_SFACE,
            reference_threshold=.4, min_query_face_quality=.5, quality_settings={"version": 1})
        display = DisplayClientRepository(session).provision(spa_id=fixture.spa_id, name="capture-test-display")
        session.commit()
        token = display.token_value
    app = realtime.create_app()
    app.state.role_state.update({"ready": True, "session_factory": lambda: Session(fixture.engine),
        "admitted_pipeline_revision_id": adapter.pipeline_revision_id, "model_adapter": adapter,
        "object_store": fixture.store, "qr_ticket_secret": "capture-identity-isolated-test",
        "realtime_deadline_ms": 7000, "realtime_result_display_ms": 15000,
        "display_client_rate_limiter": DisplayClientRateLimiter(limit=100, window_seconds=60)})
    client_id = uuid.uuid4()
    manifest = _manifest(client_id, count=len(crops))
    manifest["timing"]["reference_series_ready_at"] = datetime.now(UTC).isoformat()
    boundary = "capture-identity-native"
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="manifest"\r\nContent-Type: application/json; charset=utf-8\r\n\r\n'.encode()
             + json.dumps(manifest).encode() + b"\r\n"]
    for index, crop in enumerate(crops):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="crop_{index:03d}"; filename="crop_{index:03d}.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode() + crop + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    messages: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)
        if (finalize_before_background and message["type"] == "http.response.body"
                and next(item["status"] for item in messages if item["type"] == "http.response.start") == 200):
            # A fast client receipt can finalize evidence before the background
            # attachment gets the DB lock. Exercise that exact ordering.
            with Session(fixture.engine) as session:
                attempt = session.scalar(select(PromoAttempt).where(PromoAttempt.client_attempt_id == client_id))
                assert attempt is not None
                repository = DiagnosticEvidenceRepository(session)
                evidence = repository.get(attempt.id)
                assert evidence is not None and "captures" not in (evidence.ordinary_manifest or {})
                repository.finalize(attempt_id=attempt.id, ordinary_manifest={"schema_version": 1,
                    "client": {"response_received_ms": 123}, "display": {"status": "confirmed"}})
                session.commit()

    asyncio.run(app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "https", "path": "/api/realtime/attempts", "raw_path": b"/api/realtime/attempts",
        "query_string": b"", "headers": [(b"host", b"testserver"),
            (b"authorization", f"Bearer {token}".encode()),
            (b"content-type", f"multipart/form-data; boundary={boundary}".encode())],
        "client": ("127.0.0.1", 10000), "server": ("testserver", 443)}, receive, send))
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    with Session(fixture.engine) as session:
        attempt_id = session.scalar(select(PromoAttempt.id).where(PromoAttempt.client_attempt_id == client_id))
    assert attempt_id is not None, messages
    return status, attempt_id


def test_native_label_capture_reopen_receipt_race_and_retention(media_state: MediaFixture) -> None:
    f = media_state
    adapter, face_id, crop = _native_photo(f)
    cookies = f.cookies["operator"]
    csrf = cookies["fm_staff_csrf"]
    assert request(f.app, "/api/diagnostics/people").status == 401
    assert request(f.app, "/api/diagnostics/people", cookies=f.cookies["photographer"]).status == 403
    assert request(f.app, "/api/diagnostics/people", cookies=cookies, method="POST", payload={"name": "Тест"}).status == 403
    one = request(f.app, "/api/diagnostics/people", cookies=cookies, csrf=csrf, method="POST", payload={"name": "Тестовое лицо"}).json()
    two = request(f.app, "/api/diagnostics/people", cookies=cookies, csrf=csrf, method="POST", payload={"name": "Тестовое лицо"}).json()
    assert one["id"] != two["id"]
    faces = request(f.app, f'/api/diagnostics/photo-faces/{f.ids["no_faces"]}', cookies=cookies).json()["faces"]
    assert [face["id"] for face in faces] == [str(face_id)]
    today = datetime.now(STAFF_TIMEZONE).date().isoformat()
    photos = request(f.app, "/api/inventory/venue-media", cookies=cookies,
        params={"spa_id": str(f.spa_id), "date_from": today, "date_to": today}).json()["photos"]
    assert str(f.ids["no_faces"]) in [photo["photo_id"] for photo in photos]
    image = request(f.app, faces[0]["image_url"], cookies=cookies)
    assert image.status == 200 and image.body.startswith(b"\xff\xd8")
    assert request(f.app, f"/api/diagnostics/photo-faces/{face_id}/person", cookies=cookies,
        csrf=csrf, method="PUT", payload={"person_id": one["id"]}).status == 200
    # No additional vectors were materialized by manual labeling.
    with Session(f.engine) as session:
        assert session.scalar(select(func.count()).select_from(PhotoFace)) == 1
        assert session.scalar(select(func.count()).select_from(DiagnosticFaceLabel)) == 1
        assert compatible_examples(session, uuid.uuid4()) == []
    blank = cv2.imencode(".jpg", np.zeros((64, 64, 3), dtype=np.uint8))[1].tobytes()
    crops = [blank, *([crop] * 7)]
    status, attempt_id = _realtime_request(f, adapter, crops, finalize_before_background=True)
    assert status == 200
    path = f"/api/diagnostics/captures/{attempt_id}"
    detail = request(f.app, path, cookies=cookies)
    assert detail.status == 200
    captures = detail.json()["captures"]
    assert len(captures["items"]) == 8 and captures["selection_available"]
    assert captures["threshold"] == .4
    assert captures["pipeline_revision_id"] == str(adapter.pipeline_revision_id)
    assert captures["items"][0]["reason"] == "no_face"
    assert all(item["person_id"] == one["id"] for item in captures["items"][1:])
    assert all(item["nearest_people"][0]["person_id"] == one["id"] for item in captures["items"][1:])
    assert all(item["nearest_people"][0]["identity_name"] == "Тестовое лицо" for item in captures["items"][1:])
    assert [item["occurrence_index"] for item in captures["items"] if item["rank"] is None] == [0, 6, 7]
    for index, item in enumerate(captures["items"]):
        response = request(f.app, item["image_url"], cookies=cookies)
        assert response.status == 200 and response.body == crops[index]
        assert response.headers["cache-control"] == "no-store"
        assert request(f.app, item["image_url"]).status == 401
    keys = [f"diagnostics/captures/{attempt_id}/{index}.jpg" for index in range(len(crops))]
    f.keys.extend(keys)
    with Session(f.engine) as session:
        evidence = DiagnosticEvidenceRepository(session).get(attempt_id)
        assert evidence is not None and evidence.completeness == "complete"
        manifest = evidence.ordinary_manifest
        assert manifest is not None
        assert manifest["client"]["response_received_ms"] == 123
        assert manifest["display"]["status"] == "confirmed"
        selected = sorted((item for item in captures["items"] if item["rank"] is not None), key=lambda item: item["rank"])
        assert [item["occurrence_index"] for item in selected] == [item["occurrence_index"] for item in manifest["detections"]]
    # A new app/session reads the same labels and diagnostics.
    assert request(f.app, path, cookies=cookies).json()["captures"] == captures
    assert request(f.app, f'/api/diagnostics/photo-faces/{f.ids["no_faces"]}', cookies=cookies).json()["faces"][0]["person_id"] == one["id"]
    future = datetime.now(UTC) + timedelta(days=91)
    with Session(f.engine) as session:
        cleanup = run_retention_cleanup(session, object_store=f.store, now=future)
    assert cleanup.state == "succeeded"
    assert cleanup.private_artifacts_deleted == 8
    with Session(f.engine) as session:
        assert session.get(PromoAttempt, attempt_id) is None
        assert session.scalar(select(func.count()).select_from(DiagnosticPerson)) == 2
        assert session.scalar(select(func.count()).select_from(DiagnosticFaceLabel)) == 1
        assert DiagnosticEvidenceRepository(session).get(attempt_id).ordinary_manifest is None
    assert not f.store.list_keys(prefix=f"diagnostics/captures/{attempt_id}/")
    assert request(f.app, path, cookies=cookies).status == 404
    # Manual correction/removal is independent from capture retention.
    assert request(f.app, f"/api/diagnostics/photo-faces/{face_id}/person", cookies=cookies,
        csrf=csrf, method="PUT", payload={"person_id": two["id"]}).status == 200
    assert request(f.app, f"/api/diagnostics/photo-faces/{face_id}/person", cookies=cookies,
        csrf=csrf, method="PUT", payload={"person_id": None}).status == 200
    assert request(f.app, f'/api/diagnostics/people/{one["id"]}', cookies=cookies, csrf=csrf, method="DELETE").status == 200
    # Downgrade only the test-owned database and prove upgrade reversibility.
    command.downgrade(Config("alembic.ini"), "0024_spa_detector_thresholds")
    assert "diagnostic_people" not in inspect(f.engine).get_table_names(schema="face_moment")
    command.upgrade(Config("alembic.ini"), "head")

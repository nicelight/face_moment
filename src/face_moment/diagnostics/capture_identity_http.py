"""Private Admin media diagnostics, using existing staff sessions and CSRF."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from face_moment.diagnostics.capture_identity import DiagnosticFaceLabel, DiagnosticPerson
from face_moment.diagnostics.evidence import DiagnosticEvidenceRepository, ORDINARY_REMOVED_GAP_REASON
from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.platform.auth.principals import StaffRole
from face_moment.platform.auth.sessions import (
    CsrfValidationError, InvalidSessionError, authenticate_unsafe_staff_request,
    get_current_principal,
)
from face_moment.platform.staff_datetime import STAFF_TIMEZONE
from face_moment.processing.persistence import PhotoFace
from face_moment.processing.staff_media_projection import read_staff_media_projections
from face_moment.promo.attempt import PromoAttempt
from face_moment.serving_control.ingest_target import Spa

HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def register_capture_identity_routes(app: FastAPI, *, session_factory: Callable[[], Session],
                                     object_store_factory: Callable[[], PrivateObjectStore] | None = None) -> None:
    store_factory = object_store_factory or (lambda: PrivateObjectStore(Settings.from_env()))

    def respond(request: Request, operation: Callable[[Session], object]) -> Response:
        try:
            with session_factory() as session:
                if request.method in {"GET", "HEAD"}:
                    principal = get_current_principal(session, session_token=request.cookies.get("fm_staff_session"))
                else:
                    principal = authenticate_unsafe_staff_request(session,
                        session_token=request.cookies.get("fm_staff_session"),
                        csrf_cookie_token=request.cookies.get("fm_staff_csrf"),
                        csrf_header_token=request.headers.get("x-csrf-token"))
                if principal.role not in {StaffRole.OPERATOR, StaffRole.DEVELOPER}:
                    raise HTTPException(403)
                result = operation(session)
                if request.method not in {"GET", "HEAD"}:
                    session.commit()
                if isinstance(result, Response):
                    return result
                return JSONResponse(result, headers=HEADERS)
        except InvalidSessionError as error:
            raise HTTPException(401, headers=HEADERS) from error
        except CsrfValidationError as error:
            raise HTTPException(403, headers=HEADERS) from error
        except (ValueError, TypeError, KeyError) as error:
            raise HTTPException(422, detail="Некорректные данные", headers=HEADERS) from error

    @app.get("/api/diagnostics/people")
    def people(request: Request) -> Response:
        return respond(request, lambda session: {"people": [
            {"id": str(person.id), "name": person.name}
            for person in session.scalars(select(DiagnosticPerson).order_by(DiagnosticPerson.name, DiagnosticPerson.id))]})

    @app.post("/api/diagnostics/people")
    async def create_person(request: Request) -> Response:
        body = await request.json()
        def operation(session: Session) -> object:
            person = DiagnosticPerson(name=_name(body))
            session.add(person)
            session.flush()
            return {"id": str(person.id), "name": person.name}
        return await run_in_threadpool(respond, request, operation)

    @app.patch("/api/diagnostics/people/{person_id}")
    async def rename_person(person_id: UUID, request: Request) -> Response:
        body = await request.json()
        def operation(session: Session) -> object:
            person = session.get(DiagnosticPerson, person_id)
            if person is None:
                raise HTTPException(404)
            person.name = _name(body)
            return {"id": str(person.id), "name": person.name}
        return await run_in_threadpool(respond, request, operation)

    @app.delete("/api/diagnostics/people/{person_id}")
    def delete_person(person_id: UUID, request: Request) -> Response:
        def operation(session: Session) -> object:
            session.execute(delete(DiagnosticPerson).where(DiagnosticPerson.id == person_id))
            return {"deleted": True}
        return respond(request, operation)

    @app.get("/api/diagnostics/photo-faces/{photo_id}")
    def photo_faces(photo_id: UUID, request: Request) -> Response:
        def operation(session: Session) -> object:
            photo = _photo(session, photo_id)
            venue = _venue(session, photo.spa_id)
            projection = read_staff_media_projections(session,
                photo_revisions=[(photo.id, photo.admission_pipeline_revision_id)],
                preferred_revision_id=venue.serving_pipeline_revision_id).get(photo.id)
            revision_id = projection.pipeline_revision_id if projection else photo.admission_pipeline_revision_id
            faces = session.execute(select(PhotoFace, DiagnosticFaceLabel.person_id)
                .outerjoin(DiagnosticFaceLabel, DiagnosticFaceLabel.face_id == PhotoFace.id)
                .where(PhotoFace.photo_id == photo.id,
                       PhotoFace.pipeline_revision_id == revision_id)
                .order_by(PhotoFace.face_index)).all()
            return {"faces": [{"id": str(face.id), "person_id": str(person_id) if person_id else None,
                "pipeline_revision_id": str(face.pipeline_revision_id),
                "image_url": f"/api/diagnostics/photo-faces/{face.id}/image"}
                for face, person_id in faces]}
        return respond(request, operation)

    @app.put("/api/diagnostics/photo-faces/{face_id}/person")
    async def label_face(face_id: UUID, request: Request) -> Response:
        body = await request.json()
        def operation(session: Session) -> object:
            face = session.get(PhotoFace, face_id)
            if face is None:
                raise HTTPException(404)
            _photo(session, face.photo_id)
            person_id = UUID(body["person_id"]) if body.get("person_id") else None
            if person_id is not None and session.get(DiagnosticPerson, person_id) is None:
                raise HTTPException(404)
            label = session.get(DiagnosticFaceLabel, face_id)
            if person_id is None:
                if label is not None:
                    session.delete(label)
            elif label is None:
                session.add(DiagnosticFaceLabel(face_id=face_id, person_id=person_id))
            else:
                label.person_id = person_id
            return {"person_id": str(person_id) if person_id else None}
        return await run_in_threadpool(respond, request, operation)

    @app.get("/api/diagnostics/photo-faces/{face_id}/image")
    def face_image(face_id: UUID, request: Request) -> Response:
        def operation(session: Session) -> object:
            face = session.get(PhotoFace, face_id)
            if face is None:
                raise HTTPException(404)
            photo = _photo(session, face.photo_id)
            original = store_factory().read(key=photo.original_object_key)
            image = cv2.imdecode(np.frombuffer(original, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise HTTPException(404)
            height, width = image.shape[:2]
            padding = .1 * max(face.bbox_w, face.bbox_h)
            x0, y0 = max(0, int(face.bbox_x-padding)), max(0, int(face.bbox_y-padding))
            x1 = min(width, int(face.bbox_x+face.bbox_w+padding))
            y1 = min(height, int(face.bbox_y+face.bbox_h+padding))
            if x1 <= x0 or y1 <= y0:
                raise HTTPException(404)
            success, encoded = cv2.imencode(".jpg", image[y0:y1, x0:x1])
            if not success:
                raise HTTPException(404)
            return Response(encoded.tobytes(), media_type="image/jpeg", headers=HEADERS)
        return respond(request, operation)

    @app.get("/api/diagnostics/captures")
    def captures(request: Request, spa_id: UUID, date_from: str, date_to: str) -> Response:
        def operation(session: Session) -> object:
            _venue(session, spa_id)
            start, end = _period(date_from, date_to)
            attempts = session.scalars(select(PromoAttempt).where(PromoAttempt.spa_id == spa_id,
                PromoAttempt.created_at >= start, PromoAttempt.created_at < end)
                .order_by(PromoAttempt.created_at.desc(), PromoAttempt.id))
            return {"attempts": [{"id": str(attempt.id), "created_at": attempt.created_at.isoformat(),
                "proposal_count": attempt.proposal_count} for attempt in attempts]}
        return respond(request, operation)

    @app.get("/api/diagnostics/captures/{attempt_id}")
    def capture_detail(attempt_id: UUID, request: Request) -> Response:
        def operation(session: Session) -> object:
            attempt = _attempt(session, attempt_id)
            evidence = DiagnosticEvidenceRepository(session).get(attempt_id)
            manifest = _readable_manifest(evidence)
            captures = manifest.get("captures")
            result: dict[str, object] = {"id": str(attempt.id), "created_at": attempt.created_at.isoformat(),
                "captures": None}
            if isinstance(captures, dict):
                data = dict(captures)
                expired = datetime.fromisoformat(str(data["expires_at"])) <= datetime.now(timezone.utc)
                items = []
                for capture in data.get("items", []):
                    row = dict(capture)
                    row["image_url"] = (f"/api/diagnostics/captures/{attempt.id}/images/{row['occurrence_index']}"
                        if row.get("image_saved") and not expired else None)
                    items.append(row)
                data["items"] = items
                data["images_expired"] = expired
                result["captures"] = data
            return result
        return respond(request, operation)

    @app.get("/api/diagnostics/captures/{attempt_id}/images/{occurrence_index}")
    def capture_image(attempt_id: UUID, occurrence_index: int, request: Request) -> Response:
        def operation(session: Session) -> object:
            _attempt(session, attempt_id)
            evidence = DiagnosticEvidenceRepository(session).get(attempt_id)
            manifest = _readable_manifest(evidence)
            for artifact in manifest.get("artifacts", []):
                if artifact.get("kind") != "capture_crop" or artifact.get("occurrence_index") != occurrence_index:
                    continue
                if datetime.fromisoformat(artifact["expires_at"]) <= datetime.now(timezone.utc):
                    raise HTTPException(410, detail="Срок хранения изображения истёк", headers=HEADERS)
                return Response(store_factory().read(key=artifact["object_key"]),
                                media_type="image/jpeg", headers=HEADERS)
            raise HTTPException(404, headers=HEADERS)
        return respond(request, operation)


def _name(body: Any) -> str:
    name = body.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 200:
        raise ValueError("name")
    return name.strip()


def _venue(session: Session, spa_id: UUID) -> Spa:
    venue = session.get(Spa, spa_id)
    if venue is None or not venue.active:
        raise HTTPException(404)
    return venue


def _photo(session: Session, photo_id: UUID) -> Photo:
    photo = session.get(Photo, photo_id)
    if photo is None or not photo.is_active:
        raise HTTPException(404)
    _venue(session, photo.spa_id)
    return photo


def _attempt(session: Session, attempt_id: UUID) -> PromoAttempt:
    attempt = session.get(PromoAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(404)
    _venue(session, attempt.spa_id)
    return attempt


def _readable_manifest(evidence: Any) -> dict[str, Any]:
    if evidence is None or evidence.ordinary_expired_at is not None or evidence.gap_reason == ORDINARY_REMOVED_GAP_REASON:
        return {}
    return dict(evidence.ordinary_manifest or {})


def _period(date_from: str, date_to: str) -> tuple[datetime, datetime]:
    first = datetime.strptime(date_from, "%Y-%m-%d").date()
    last = datetime.strptime(date_to, "%Y-%m-%d").date()
    if first > last:
        raise ValueError("reversed dates")
    return datetime.combine(first, time.min, STAFF_TIMEZONE), datetime.combine(last + timedelta(days=1), time.min, STAFF_TIMEZONE)

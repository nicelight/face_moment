"""Small manual identity registry and best-effort capture diagnostic attachment.

@docs .memory-bank/domains/capture-identity.md
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
import json
from typing import Protocol
import uuid

import numpy as np
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Uuid, cast, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.diagnostics.evidence import (
    DiagnosticEvidenceRepository, ORDINARY_REMOVED_GAP_REASON,
    _validate_ordinary_manifest,
)
from face_moment.infrastructure.database import Base
from face_moment.inventory.photo_persistence import Photo
from face_moment.processing.persistence import PhotoFace
from face_moment.processing.reference_query import PreparedReferenceQuery

class CaptureObjectStore(Protocol):
    def put(self, *, key: str, body: bytes) -> None: ...
    def read(self, *, key: str) -> bytes: ...
    def delete(self, *, key: str) -> None: ...


class DiagnosticPerson(Base):
    __tablename__ = "diagnostic_people"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="ck_diagnostic_people_name"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class DiagnosticFaceLabel(Base):
    __tablename__ = "diagnostic_face_labels"
    __table_args__ = (Index("ix_diagnostic_face_labels_person", "person_id"),)
    # Logical processing-owned face reference: purge never cascades into labels.
    face_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    person_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("face_moment.diagnostic_people.id", ondelete="CASCADE"),
        nullable=False,
    )


def compatible_examples(session: Session, revision_id: uuid.UUID) -> list[tuple[uuid.UUID, str, np.ndarray]]:  # type: ignore[type-arg]
    """Read existing active labelled embeddings; never persist another copy."""
    rows = session.execute(select(DiagnosticPerson.id, DiagnosticPerson.name,
        cast(PhotoFace.embedding, String)).select_from(DiagnosticFaceLabel)
        .join(DiagnosticPerson, DiagnosticPerson.id == DiagnosticFaceLabel.person_id)
        .join(PhotoFace, PhotoFace.id == DiagnosticFaceLabel.face_id)
        .join(Photo, Photo.id == PhotoFace.photo_id)
        .where(PhotoFace.pipeline_revision_id == revision_id, Photo.is_active.is_(True)))
    return [(person_id, name, np.asarray(json.loads(vector), dtype=np.float32))
            for person_id, name, vector in rows]


def identify_capture(*, query: PreparedReferenceQuery | None,
                     examples: Sequence[tuple[uuid.UUID, str, np.ndarray]],  # type: ignore[type-arg]
                     revision_id: uuid.UUID, threshold: float,
                     unavailable_reason: str = "preparation_unavailable") -> dict[str, object]:
    if query is None:
        return {"reason": unavailable_reason, "person_id": None, "score": None}
    if query.pipeline_revision_id != revision_id:
        return {"reason": "incompatible_revision", "person_id": None, "score": None}
    by_person: dict[str, tuple[float, str]] = {}
    for person_id, name, embedding in examples:
        if embedding.shape != query.embedding.shape:
            continue
        denominator = float(np.linalg.norm(query.embedding) * np.linalg.norm(embedding))
        if denominator <= 0 or not np.isfinite(denominator):
            continue
        score = float(np.clip(np.dot(query.embedding, embedding) / denominator, -1, 1))
        key = str(person_id)
        if key not in by_person or score > by_person[key][0]:
            by_person[key] = (score, name)
    if not by_person:
        return {"reason": "no_compatible_examples", "person_id": None, "score": None}
    ranked = sorted(by_person.items(), key=lambda item: (-item[1][0], item[0]))[:3]
    nearest = [{"person_id": person_id, "identity_name": name, "score": score}
               for person_id, (score, name) in ranked]
    best_id, (best_score, best_name) = ranked[0]
    return {"reason": "recognized" if best_score >= threshold else "below_threshold",
            "person_id": best_id if best_score >= threshold else None,
            "identity_name": best_name if best_score >= threshold else None,
            "nearest_people": nearest,
            "score": best_score}


def attach_captures(session_factory: Callable[[], Session], *, object_store: CaptureObjectStore,
                    attempt_id: uuid.UUID, created_at: datetime,
                    revision_id: uuid.UUID, threshold: float,
                    crops: Sequence[bytes], observations: Mapping[int, Mapping[str, object]]) -> None:
    """After-response attachment; never call the shared model or alter Promo state.

    Persist object descriptors before uploading so interruption leaves cleanup
    retry references. Merge under the evidence lock, including finalized bundles.
    """
    if len(crops) > 20:
        return
    from face_moment.promo.retention import ORDINARY_RETENTION_DAYS

    expires_at = created_at + timedelta(days=ORDINARY_RETENTION_DAYS)
    if datetime.now(timezone.utc) >= expires_at:
        return
    try:
        with session_factory() as session:
            examples = compatible_examples(session, revision_id)
            rows: list[dict[str, object]] = []
            artifacts: list[dict[str, object]] = []
            for index, _ in enumerate(crops):
                observation = observations.get(index, {})
                query = observation.get("query")
                result = identify_capture(query=query if isinstance(query, PreparedReferenceQuery) else None,
                    examples=examples, revision_id=revision_id, threshold=threshold,
                    unavailable_reason=str(observation.get("reason", "preparation_unavailable")))
                rows.append({"occurrence_index": index, "rank": observation.get("rank"),
                             "image_saved": False, **result})
                artifacts.append({"kind": "capture_crop", "occurrence_index": index,
                    "object_key": f"diagnostics/captures/{attempt_id}/{index}.jpg",
                    "expires_at": expires_at.isoformat()})
            capture_data: dict[str, object] = {"pipeline_revision_id": str(revision_id),
                "threshold": threshold, "expires_at": expires_at.isoformat(),
                "selection_available": not crops or any("rank" in value for value in observations.values()),
                "items": rows}
            if not _merge_capture_data(session, attempt_id, capture_data, artifacts):
                return
            session.commit()
            for row, artifact, body in zip(rows, artifacts, crops, strict=True):
                try:
                    object_store.put(key=str(artifact["object_key"]), body=body)
                    row["image_saved"] = True
                except Exception:
                    row["image_saved"] = False
            _merge_capture_data(session, attempt_id, capture_data, artifacts)
            session.commit()
    except Exception:
        # Optional diagnostics must not fail the already-completed request.
        return


def _merge_capture_data(session: Session, attempt_id: uuid.UUID,
                        capture_data: dict[str, object], artifacts: list[dict[str, object]]) -> bool:
    evidence = DiagnosticEvidenceRepository(session).get(attempt_id, for_update=True)
    if evidence is None or evidence.ordinary_expired_at is not None or evidence.gap_reason == ORDINARY_REMOVED_GAP_REASON:
        return False
    manifest = dict(evidence.ordinary_manifest or {"schema_version": 1})
    # Capture attachment owns only these two sections; receipt fields survive.
    manifest["captures"] = capture_data
    previous = manifest.get("artifacts", [])
    other = [item for item in previous if isinstance(item, dict) and item.get("kind") != "capture_crop"] if isinstance(previous, list) else []
    manifest["artifacts"] = [*other, *artifacts]
    evidence.ordinary_manifest = _validate_ordinary_manifest(manifest)
    evidence.updated_at = datetime.now(timezone.utc)
    session.flush()
    return True

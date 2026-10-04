"""Promo-owned hidden profile admission; processing supplies the current query.

No selfie bytes or diagnostics are stored here. Caller commits the transaction
and sends the cookie only after successful commit, including bounded denials.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import secrets
import uuid
from typing import Literal

import numpy as np
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Uuid, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import Float
from sqlalchemy.orm import Mapped, Session, mapped_column
from starlette.responses import Response

from face_moment.infrastructure.database import Base
from face_moment.processing.reference_query import PreparedReferenceQuery
from face_moment.serving_control.public_search_settings import read_profile_similarity_threshold

COOKIE_NAME = "fm_browser_profile"
FACE_DENIED_MESSAGE = "Это лицо невозможно искать, так как оно отличается от тех лиц, которые вы искали ранее"
CONFIRMATION_MESSAGE = "Снимок отличается от предыдущих. Возможно, вы сканируете чужое лицо. Это я / Переснять"


class BrowserSearchProfile(Base):
    __tablename__ = "browser_search_profiles"
    __table_args__ = (
        CheckConstraint("b_embedding IS NULL OR a_embedding IS NOT NULL", name="ck_browser_profile_b_requires_a"),
        CheckConstraint("(a_embedding IS NULL) = (a_pipeline_revision_id IS NULL)", name="ck_browser_profile_a_revision"),
        CheckConstraint("(b_embedding IS NULL) = (b_pipeline_revision_id IS NULL)", name="ck_browser_profile_b_revision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cookie_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    last_visit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reset_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    a_embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
    b_embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
    a_pipeline_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("face_moment.pipeline_revisions.id", ondelete="RESTRICT"), nullable=True)
    b_pipeline_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("face_moment.pipeline_revisions.id", ondelete="RESTRICT"), nullable=True)


class IncompatibleBrowserProfileRevisionError(RuntimeError):
    """Transport maps this fail-closed condition to HTTP 503."""


@dataclass(frozen=True, slots=True)
class BrowserProfileAdmission:
    profile_id: uuid.UUID
    cookie_token: str
    outcome: Literal["allowed", "retake_required", "confirmation_required", "face_denied"]
    query: PreparedReferenceQuery | None
    message: str | None = None


def set_browser_profile_cookie(response: Response, cookie_token: str) -> None:
    response.set_cookie(COOKIE_NAME, cookie_token, max_age=31536000,
                        httponly=True, secure=True, samesite="lax", path="/")


class BrowserSearchProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find(self, cookie_token: str | None, *, lock: bool = False) -> BrowserSearchProfile | None:
        if not cookie_token:
            return None
        statement = select(BrowserSearchProfile).where(
            BrowserSearchProfile.cookie_digest == hashlib.sha256(cookie_token.encode()).hexdigest())
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return self.session.execute(statement).scalar_one_or_none()

    def admit(
        self, *, cookie_token: str | None, query: PreparedReferenceQuery | None,
        confirm_reset: bool = False,
    ) -> BrowserProfileAdmission:
        """Only a search action creates unknown profiles; None means unusable capture.

        processing must validate single-face/native quality before supplying the
        compatible query. Row lock is held until the caller's commit/rollback.
        """
        record = self.find(cookie_token, lock=True)
        if record is None:
            cookie_token = secrets.token_hex(32)
            record = BrowserSearchProfile(cookie_digest=hashlib.sha256(cookie_token.encode()).hexdigest(),
                last_visit_at=datetime.now(timezone.utc), reset_used=False)
            self.session.add(record)
            self.session.flush()
        assert cookie_token is not None
        if query is not None:
            for revision in (record.a_pipeline_revision_id, record.b_pipeline_revision_id):
                if revision is not None and revision != query.pipeline_revision_id:
                    raise IncompatibleBrowserProfileRevisionError("profile revision incompatible")
        record.last_visit_at = datetime.now(timezone.utc)
        outcome: Literal["allowed", "retake_required", "confirmation_required", "face_denied"] = "allowed"
        message = None
        if query is None:
            outcome = "retake_required"
        else:
            embedding = query.embedding.astype(np.float64)
            norm = float(np.linalg.norm(embedding))
            if not norm or not np.isfinite(norm):
                raise ValueError("processing query must have a nonzero finite norm")
            threshold = read_profile_similarity_threshold(self.session)
            matches = False
            for sample in (record.a_embedding, record.b_embedding):
                if sample is not None:
                    saved = np.asarray(sample, dtype=np.float64)
                    if saved.shape != embedding.shape:
                        raise IncompatibleBrowserProfileRevisionError("profile embedding shape incompatible")
                    # Identical nonzero vectors have cosine 1; norm rounding must
                    # not consume B/reset at the accepted threshold endpoint.
                    similarity = (1.0 if np.array_equal(saved, embedding) else
                                  float(np.dot(saved, embedding) / (np.linalg.norm(saved) * norm)))
                    # Roundoff can leave cosine's mathematical [-1, 1] range.
                    similarity = max(-1.0, min(1.0, similarity))
                    matches = matches or similarity >= threshold
            if record.a_embedding is None:
                record.a_embedding = embedding.tolist()
                record.a_pipeline_revision_id = query.pipeline_revision_id
            elif matches:
                pass
            elif record.b_embedding is None:
                record.b_embedding = embedding.tolist()
                record.b_pipeline_revision_id = query.pipeline_revision_id
            elif record.reset_used:
                outcome, message = "face_denied", FACE_DENIED_MESSAGE
            elif confirm_reset:
                record.a_embedding = embedding.tolist()
                record.a_pipeline_revision_id = query.pipeline_revision_id
                record.b_embedding = None
                record.b_pipeline_revision_id = None
                record.reset_used = True
            else:
                outcome, message = "confirmation_required", CONFIRMATION_MESSAGE
        self.session.flush()
        return BrowserProfileAdmission(record.id, cookie_token, outcome,
                                       query if outcome == "allowed" else None, message)

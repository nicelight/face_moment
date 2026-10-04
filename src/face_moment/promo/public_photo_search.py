"""Promo owns public admission, current results and cross-owner orchestration."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import time
from typing import Any
import uuid

from botocore.exceptions import ClientError
from PIL import Image

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import DateTime, ForeignKey, Index, Uuid, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.infrastructure.database import Base
from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.inventory.public_photo_projection import read_public_active_photos, read_public_active_original
from face_moment.processing.public_gallery_preview import render_public_gallery_preview
from face_moment.processing.face_engine import FaceEngine
from face_moment.processing.persistence import PublicExactSearchRepository
from face_moment.processing.public_selfie_search import prepare_public_selfie, search_public_selfie, read_public_common_photos
from face_moment.promo.browser_search_profile import BrowserSearchProfileRepository
from face_moment.promo.realtime_orchestration import _PROCESS_LOCAL_REALTIME_SLOT
from face_moment.serving_control.public_search_context import read_public_search_context, read_public_venues


class PublicSearchResult(Base):
    __tablename__ = "public_search_results"
    __table_args__ = (Index("ix_public_results_profile_created", "profile_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("face_moment.browser_search_profiles.id", ondelete="RESTRICT"), nullable=False)
    venue_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid(as_uuid=True)), nullable=False)
    pipeline_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("face_moment.pipeline_revisions.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    venues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)


class PublicResultNotFoundError(LookupError):
    pass


class PublicProfileRequiredError(LookupError):
    pass


class PublicSearchResultRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def current(self, *, cookie_token: str | None, result_id: uuid.UUID) -> dict[str, Any]:
        profile = BrowserSearchProfileRepository(self.session).find(cookie_token, lock=True)
        if profile is None:
            raise PublicProfileRequiredError
        record = self.session.scalar(select(PublicSearchResult).where(
            PublicSearchResult.profile_id == profile.id).order_by(
                PublicSearchResult.created_at.desc(), PublicSearchResult.id.desc()).limit(1))
        if record is None or record.id != result_id:
            raise PublicResultNotFoundError
        profile.last_visit_at = datetime.now(timezone.utc)
        return self.project(record)

    def project(self, record: PublicSearchResult) -> dict[str, Any]:
        """Expose IDs/local preview routes, never private keys or embeddings."""
        ids = [uuid.UUID(item['id']) for venue in record.venues for kind in ('personal', 'common') for item in venue[kind]]
        active = {str(p.photo_id) for p in read_public_active_photos(self.session, ids)}
        venues = []
        for saved in record.venues:
            personal = [dict(item) for item in saved['personal'] if item['id'] in active]
            dates = sorted({item['visit_date'] for item in personal})
            common = [dict(item) for item in saved['common'] if item['id'] in active and item['visit_date'] in dates]
            if not personal:
                continue
            for item in personal + common:
                item.pop('similarity', None)
                item['preview_url'] = f"/api/public/results/{record.id}/previews/{item['id']}"
            venues.append({'id': saved['id'], 'name': saved['name'], 'dates': dates, 'personal': personal, 'common': common})
        return {'schema_version': 1, 'outcome': 'result', 'result_id': str(record.id),
                'personal_count': sum(len(v['personal']) for v in venues), 'venues': venues}


def execute_public_photo_search(
    *, session_factory: Callable[[], Session], engine: FaceEngine,
    pipeline_revision_id: uuid.UUID, selfie: NDArray[np.uint8], venue_ids: Sequence[uuid.UUID],
    cookie_token: str | None, confirm_reset: bool, deadline_ms: int,
) -> tuple[dict[str, Any], str | None]:
    """Use the existing Promo slot, discard late native calls, commit owners only.

    A/B and gallery publish share one profile lock/transaction. Native code is
    never force-killed; late work is rolled back and the slot stays occupied
    until it actually finishes, matching the existing Promo policy.
    """
    deadline_at = time.monotonic() + deadline_ms / 1000
    if not _PROCESS_LOCAL_REALTIME_SLOT.acquire(blocking=False):
        return {'schema_version': 1, 'outcome': 'busy'}, None
    try:
        # The provider locks venue configuration while freezing the snapshot.
        # Release those locks before native work so same-venue Promo admission
        # reaches the shared nonblocking slot rather than waiting on PostgreSQL.
        with session_factory() as snapshot_session:
            context = read_public_search_context(snapshot_session, venue_ids=venue_ids,
                admitted_pipeline_revision_id=pipeline_revision_id)
            venues = {venue.id: venue for venue in read_public_venues(snapshot_session)}
            snapshot_session.commit()
        observation = prepare_public_selfie(context=context, engine=engine, selfie=selfie)
        if time.monotonic() >= deadline_at:
            return {'schema_version': 1, 'outcome': 'deadline'}, None
        with session_factory() as session:
            admission = BrowserSearchProfileRepository(session).admit(
                cookie_token=cookie_token, query=observation.query, confirm_reset=confirm_reset)
            response: dict[str, Any] = {'schema_version': 1, 'outcome': admission.outcome}
            if admission.message:
                response['message'] = admission.message
            if admission.query is not None:
                matches = search_public_selfie(repository=PublicExactSearchRepository(session),
                    context=context, query=admission.query)
                if matches:
                    common = read_public_common_photos(session, pipeline_revision_id=context.pipeline_revision_id,
                        matched_dates=tuple({(m.spa_id, m.visit_date) for m in matches}))
                    groups = []
                    for venue_id in venue_ids:
                        owner = venues[venue_id]
                        personal = [{'id': str(m.photo_id), 'visit_date': m.visit_date.isoformat(),
                            'similarity': m.cosine_similarity, 'is_free': owner.is_free} for m in matches if m.spa_id == venue_id]
                        if personal:
                            groups.append({'id': str(venue_id), 'name': owner.name, 'personal': personal,
                                'common': [{'id': str(p.photo_id), 'visit_date': p.visit_date.isoformat(), 'is_free': True}
                                           for p in common if p.spa_id == venue_id]})
                    record = PublicSearchResult(profile_id=admission.profile_id, venue_ids=list(venue_ids),
                        pipeline_revision_id=context.pipeline_revision_id, created_at=datetime.now(timezone.utc), venues=groups)
                    session.add(record)
                    session.flush()
                    response = PublicSearchResultRepository(session).project(record)
                else:
                    response['outcome'] = 'no_matches'
            if time.monotonic() >= deadline_at:
                return {'schema_version': 1, 'outcome': 'deadline'}, None
            session.commit()
            return response, admission.cookie_token
    finally:
        _PROCESS_LOCAL_REALTIME_SLOT.release()


def read_public_gallery_preview(*, session_factory: Callable[[], Session], cookie_token: str,
                                result_id: uuid.UUID, photo_id: uuid.UUID,
                                object_store: PrivateObjectStore) -> bytes:
    """Authorize current gallery membership before resolving any private bytes."""
    with session_factory() as session:
        content = PublicSearchResultRepository(session).current(cookie_token=cookie_token, result_id=result_id)
        if not any(item['id'] == str(photo_id) for venue in content['venues']
                   for kind in ('personal', 'common') for item in venue[kind]):
            raise PublicResultNotFoundError
        key = read_public_active_original(session, photo_id=photo_id,
            venue_ids=[uuid.UUID(venue['id']) for venue in content['venues']])
        if key is None:
            raise PublicResultNotFoundError
        session.commit()
    try:
        original = object_store.read(key=key)
    except ClientError as error:
        if error.response.get('Error', {}).get('Code') in {'NoSuchKey', 'NotFound', '404'}:
            raise PublicResultNotFoundError from error
        raise
    try:
        return render_public_gallery_preview(original)
    except (ValueError, OSError, Image.DecompressionBombError) as error:
        raise PublicResultNotFoundError from error

"""Promo-owned authoritative selected-photo quote using existing owner projections.

@docs .memory-bank/domains/photo-orders.md
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Any
import uuid

from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.inventory.public_photo_projection import read_public_active_original, read_public_active_photos
from face_moment.promo.public_photo_search import PublicSearchResultRepository, PublicResultNotFoundError
from face_moment.serving_control.photo_tariff import read_photo_tariff_snapshot
from face_moment.serving_control.public_search_context import read_public_venues


def quote_selected_photos(session: Session, *, cookie_token: str, result_id: uuid.UUID,
                          photo_ids: Sequence[uuid.UUID], object_store: PrivateObjectStore) -> dict[str, Any]:
    if len(set(photo_ids)) != len(photo_ids):
        raise ValueError('distinct photo IDs required')
    gallery = PublicSearchResultRepository(session).current(cookie_token=cookie_token, result_id=result_id)
    members = {uuid.UUID(item['id']): (uuid.UUID(venue['id']), kind)
               for venue in gallery['venues'] for kind in ('personal', 'common') for item in venue[kind]}
    venues = {venue.id: venue for venue in read_public_venues(session)}
    photos = {photo.photo_id: photo for photo in read_public_active_photos(session, photo_ids)}
    items = []
    for identity in sorted(photo_ids):
        if identity not in members or identity not in photos:
            raise PublicResultNotFoundError
        venue_id, kind = members[identity]
        photo = photos[identity]
        if venue_id not in venues or photo.spa_id != venue_id:
            raise PublicResultNotFoundError
        key = read_public_active_original(session, photo_id=identity, venue_ids=(venue_id,))
        if key is None or not object_store.exists(key=key):
            raise PublicResultNotFoundError
        items.append({'photo_id': str(identity), 'venue_id': str(venue_id),
                      'visit_date': photo.visit_date.isoformat(),
                      'is_free': kind == 'common' or venues[venue_id].is_free, 'unit_kopecks': 0})
    paid = [item for item in items if not item['is_free']]
    if paid:
        tariff = read_photo_tariff_snapshot(session)
        units = [tariff.base_kopecks]
        for coefficient in (tariff.d1, tariff.d2, tariff.d3):
            # Preserve exact multiplication for arbitrary accepted numeric precision.
            with localcontext() as context:
                context.prec = len(str(tariff.base_kopecks)) + len(coefficient.as_tuple().digits) + 2
                units.append(int((Decimal(tariff.base_kopecks) * coefficient).to_integral_value(rounding=ROUND_HALF_UP)))
        for index, item in enumerate(paid):
            item['unit_kopecks'] = units[0 if index == 0 else 1 if index < 5 else 2 if index < 20 else 3]
    return {'schema_version': 1, 'items': items, 'selected_count': len(items), 'paid_count': len(paid),
            'total_kopecks': sum(item['unit_kopecks'] for item in items), 'currency': 'RUB'}

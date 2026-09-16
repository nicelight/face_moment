"""Venue-owned advertising playlists; binary assets live in the existing private store."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, JSON, String, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from face_moment.infrastructure.database import Base
from face_moment.serving_control.ingest_target import Spa


class AdvertisingPlaylist(Base):
    __tablename__ = "advertising_playlists"
    spa_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("face_moment.spas.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    image_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=5)
    crossfade_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=1)
    random_start: Mapped[bool] = mapped_column(nullable=False, default=False)
    item_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class AdvertisingMedia(Base):
    __tablename__ = "advertising_media"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    spa_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("face_moment.spas.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    @property
    def object_key(self) -> str:
        return f"advertising/{self.spa_id}/{self.id}"


def owned_advertising_object_keys(session: Session, media_ids: list[uuid.UUID]) -> set[str]:
    """Expose committed advertising object ownership to operator cleanup."""
    return {
        f"advertising/{spa_id}/{media_id}"
        for spa_id, media_id in session.execute(
            select(AdvertisingMedia.spa_id, AdvertisingMedia.id).where(
                AdvertisingMedia.id.in_(media_ids)
            )
        )
    }


def locked_playlist(session: Session, spa_id: uuid.UUID) -> AdvertisingPlaylist:
    # Lock the always-existing venue row, including the first playlist creation.
    if session.scalar(select(Spa).where(Spa.id == spa_id).with_for_update()) is None:
        raise LookupError("Площадка не найдена")
    playlist = session.get(AdvertisingPlaylist, spa_id)
    if playlist is None:
        playlist = AdvertisingPlaylist(spa_id=spa_id, revision=0, image_seconds=5,
            crossfade_seconds=1, random_start=False, item_ids=[])
        session.add(playlist)
        session.flush()
    return playlist


def playlist_projection(session: Session, spa_id: uuid.UUID, *, display: bool = False) -> dict[str, Any]:
    venue = session.get(Spa, spa_id)
    if venue is None:
        raise LookupError("Площадка не найдена")
    playlist = session.get(AdvertisingPlaylist, spa_id)
    media = {str(item.id): item for item in session.scalars(
        select(AdvertisingMedia).where(AdvertisingMedia.spa_id == spa_id))}
    prefix = "/api/promo/advertising/media" if display else "/api/advertising/media"
    return {
        "spa_id": str(spa_id), "name": venue.name,
        "revision": playlist.revision if playlist else 0,
        "image_seconds": playlist.image_seconds if playlist else 5,
        "crossfade_seconds": playlist.crossfade_seconds if playlist else 1,
        "random_start": playlist.random_start if playlist else False,
        "items": [{"id": item_id, "filename": media[item_id].filename,
            "content_type": media[item_id].content_type, "byte_size": media[item_id].byte_size,
            "duration_seconds": media[item_id].duration_seconds,
            "url": f"{prefix}/{item_id}"}
            for item_id in (playlist.item_ids if playlist else []) if item_id in media],
    }

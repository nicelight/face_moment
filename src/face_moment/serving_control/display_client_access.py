from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    Uuid,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import func

from face_moment.infrastructure.database import Base
from face_moment.serving_control.ingest_target import Spa

_MAX_DISPLAY_CLIENT_NAME_LENGTH = 255
_TOKEN_BYTES = 32


class DisplayClient(Base):
    """Serving-control-owned credential and lifecycle state for one kiosk."""

    __tablename__ = "display_clients"
    __table_args__ = (
        CheckConstraint(
            "octet_length(token_hash_sha256) = 32",
            name="ck_display_clients_token_hash_sha256_length",
        ),
        CheckConstraint(
            "char_length(token_value) >= 43",
            name="ck_display_clients_token_value_length",
        ),
        CheckConstraint(
            "(active AND deactivated_at IS NULL) OR "
            "(NOT active AND deactivated_at IS NOT NULL)",
            name="ck_display_clients_lifecycle_consistency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    spa_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("face_moment.spas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(_MAX_DISPLAY_CLIENT_NAME_LENGTH), nullable=False)
    token_hash_sha256: Mapped[bytes] = mapped_column(
        LargeBinary(length=32), nullable=False, unique=True
    )
    token_value: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DisplayClientNotFoundError(LookupError):
    pass


class UnknownDisplayClientSpaError(LookupError):
    pass


def hash_display_client_token(token: str) -> bytes:
    """Return the digest persisted for an opaque display-client token."""

    return hashlib.sha256(token.encode("ascii")).digest()


def _new_display_client_token() -> str:
    random_bytes = secrets.token_bytes(_TOKEN_BYTES)
    return base64.urlsafe_b64encode(random_bytes).rstrip(b"=").decode("ascii")


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("display-client lifecycle timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _normalize_name(name: str) -> str:
    normalized = name.strip()
    if not normalized or len(normalized) > _MAX_DISPLAY_CLIENT_NAME_LENGTH:
        raise ValueError("display-client name must contain 1 to 255 characters")
    return normalized


class DisplayClientRepository:
    """Owner boundary for display-client persistence and lifecycle changes."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def provision(
        self,
        *,
        spa_id: uuid.UUID,
        name: str,
        now: datetime | None = None,
    ) -> DisplayClient:
        if self._session.get(Spa, spa_id) is None:
            raise UnknownDisplayClientSpaError(str(spa_id))
        token = _new_display_client_token()
        client = DisplayClient(
            spa_id=spa_id,
            name=_normalize_name(name),
            token_hash_sha256=hash_display_client_token(token),
            token_value=token,
            active=True,
            created_at=_utc(now),
        )
        self._session.add(client)
        self._session.flush()
        return client

    def reset(
        self,
        *,
        display_client_id: uuid.UUID,
        now: datetime | None = None,
    ) -> DisplayClient:
        client = self._load(display_client_id, for_update=True)
        token = _new_display_client_token()
        client.token_hash_sha256 = hash_display_client_token(token)
        client.token_value = token
        client.active = True
        client.rotated_at = _utc(now)
        client.deactivated_at = None
        self._session.flush()
        return client

    def deactivate(
        self,
        *,
        display_client_id: uuid.UUID,
        now: datetime | None = None,
    ) -> DisplayClient:
        client = self._load(display_client_id, for_update=True)
        if client.active:
            client.active = False
            client.deactivated_at = _utc(now)
            self._session.flush()
        return client

    def get(self, display_client_id: uuid.UUID) -> DisplayClient:
        return self._load(display_client_id)

    def list_for_spa(self, spa_id: uuid.UUID) -> list[DisplayClient]:
        return list(
            self._session.scalars(
                select(DisplayClient)
                .where(DisplayClient.spa_id == spa_id)
                .order_by(DisplayClient.name, DisplayClient.id)
            )
        )

    def _load(self, display_client_id: uuid.UUID, *, for_update: bool = False) -> DisplayClient:
        statement = select(DisplayClient).where(DisplayClient.id == display_client_id)
        if for_update:
            statement = statement.with_for_update()
        client = self._session.scalar(statement)
        if client is None:
            raise DisplayClientNotFoundError(str(display_client_id))
        return client

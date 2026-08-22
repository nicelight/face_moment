"""Create the promo-owned immutable result-session table.

Revision ID: 0013_promo_sessions
Revises: 0012_promo_attempts
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0013_promo_sessions"
down_revision: str | Sequence[str] | None = "0012_promo_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "promo_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("spa_id", sa.Uuid(), nullable=False),
        sa.Column("visit_date", sa.Date(), nullable=True),
        sa.Column(
            "session_result_photo_ids",
            sa.ARRAY(sa.Uuid()),
            nullable=False,
        ),
        sa.Column("teaser_photo_ids", sa.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column(
            "qr_ticket_hash_sha256",
            sa.LargeBinary(length=32),
            nullable=False,
        ),
        sa.Column("qr_issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "qr_first_open_expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("n >= 4", name="ck_promo_sessions_n_minimum"),
        sa.CheckConstraint(
            "octet_length(qr_ticket_hash_sha256) = 32",
            name="ck_promo_sessions_qr_ticket_hash_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["face_moment.promo_attempts.id"],
            name="fk_promo_sessions_attempt_id_promo_attempts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_promo_sessions"),
        sa.UniqueConstraint("attempt_id", name="uq_promo_sessions_attempt_id"),
        sa.UniqueConstraint(
            "qr_ticket_hash_sha256",
            name="uq_promo_sessions_qr_ticket_hash_sha256",
        ),
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_table("promo_sessions", schema="face_moment")

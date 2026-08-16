"""Persist serving-control display-client credentials and lifecycle.

Revision ID: 0010_display_clients
Revises: 0009_photo_admission_lineage
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0010_display_clients"
down_revision: str | Sequence[str] | None = "0009_photo_admission_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "display_clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("spa_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("token_hash_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("token_value", sa.Text(), nullable=False),
        sa.Column(
            "active", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash_sha256) = 32",
            name="ck_display_clients_token_hash_sha256_length",
        ),
        sa.CheckConstraint(
            "char_length(token_value) >= 43",
            name="ck_display_clients_token_value_length",
        ),
        sa.CheckConstraint(
            "(active AND deactivated_at IS NULL) OR "
            "(NOT active AND deactivated_at IS NOT NULL)",
            name="ck_display_clients_lifecycle_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["spa_id"],
            ["face_moment.spas.id"],
            name="fk_display_clients_spa_id_spas",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_display_clients"),
        sa.UniqueConstraint(
            "token_hash_sha256", name="uq_display_clients_token_hash_sha256"
        ),
        schema="face_moment",
    )
    op.create_index(
        "ix_display_clients_spa_id",
        "display_clients",
        ["spa_id"],
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_index("ix_display_clients_spa_id", table_name="display_clients", schema="face_moment")
    op.drop_table("display_clients", schema="face_moment")

"""Create inventory-owned Photo identity persistence.

Revision ID: 0006_photo_identity_persistence
Revises: 0005_serving_ingest_targets
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_photo_identity_persistence"
down_revision: str | Sequence[str] | None = "0005_serving_ingest_targets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "photos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("spa_id", sa.Uuid(), nullable=False),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_at_source", sa.String(length=24), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("uploader_id", sa.Uuid(), nullable=False),
        sa.Column("checksum_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("original_object_key", sa.Text(), nullable=False),
        sa.Column("original_byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.CheckConstraint(
            "captured_at_source IN "
            "('exif', 'upload_started_at', 'visit_date_fallback')",
            name="ck_photos_captured_at_source",
        ),
        sa.CheckConstraint(
            "octet_length(checksum_sha256) = 32",
            name="ck_photos_checksum_sha256_length",
        ),
        sa.CheckConstraint(
            "original_byte_size > 0",
            name="ck_photos_original_byte_size_positive",
        ),
        sa.CheckConstraint("width > 0", name="ck_photos_width_positive"),
        sa.CheckConstraint("height > 0", name="ck_photos_height_positive"),
        sa.ForeignKeyConstraint(
            ["spa_id"],
            ["face_moment.spas.id"],
            name="fk_photos_spa_id_spas",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_photos"),
        sa.UniqueConstraint(
            "spa_id",
            "visit_date",
            "checksum_sha256",
            name="uq_photos_spa_id_visit_date_checksum_sha256",
        ),
        sa.UniqueConstraint(
            "original_object_key", name="uq_photos_original_object_key"
        ),
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_table("photos", schema="face_moment")

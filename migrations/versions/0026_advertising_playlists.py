"""Add independent venue advertising storage; existing media and history stay intact."""
from alembic import op
import sqlalchemy as sa

revision = "0026_advertising_playlists"
down_revision = "0025_capture_identity_labels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("advertising_playlists",
        sa.Column("spa_id", sa.Uuid(), sa.ForeignKey("face_moment.spas.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("image_seconds", sa.Float(), nullable=False),
        sa.Column("crossfade_seconds", sa.Float(), nullable=False),
        sa.Column("random_start", sa.Boolean(), nullable=False),
        sa.Column("item_ids", sa.JSON(), nullable=False), schema="face_moment")
    op.create_table("advertising_media",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("spa_id", sa.Uuid(), sa.ForeignKey("face_moment.spas.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True), schema="face_moment")
    op.create_index("ix_advertising_media_spa_id", "advertising_media", ["spa_id"], schema="face_moment")


def downgrade() -> None:
    op.drop_table("advertising_media", schema="face_moment")
    op.drop_table("advertising_playlists", schema="face_moment")

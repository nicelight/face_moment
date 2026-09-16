"""Persist preview pHash v1 for new processing; leave historical rows unchanged."""

from alembic import op
import sqlalchemy as sa

revision = "0027_preview_phash"
down_revision = "0026_advertising_playlists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "photo_pipeline_states",
        sa.Column("preview_phash64_v1", sa.String(16), nullable=True),
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_photo_pipeline_states_preview_phash64_v1",
        "photo_pipeline_states",
        "preview_phash64_v1 ~ '^[0-9a-f]{16}$'",
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_photo_pipeline_states_preview_phash64_v1",
        "photo_pipeline_states",
        type_="check",
        schema="face_moment",
    )
    op.drop_column("photo_pipeline_states", "preview_phash64_v1", schema="face_moment")

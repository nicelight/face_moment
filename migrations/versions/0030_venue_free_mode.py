"""Serving-control free flag; existing venues remain paid."""
from alembic import op
import sqlalchemy as sa

revision = "0030_venue_free_mode"
down_revision = "0029_global_photo_tariff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("spas", sa.Column("is_free", sa.Boolean(), nullable=False, server_default=sa.false()), schema="face_moment")


def downgrade() -> None:
    op.drop_column("spas", "is_free", schema="face_moment")

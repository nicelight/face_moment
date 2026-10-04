"""Persist fixed Promo gallery membership; historical sessions stay unchanged."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0033_promo_session_gallery"
down_revision = "0032_photo_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("promo_sessions", sa.Column("gallery_photos", postgresql.JSONB(), nullable=True), schema="face_moment")


def downgrade() -> None:
    op.drop_column("promo_sessions", "gallery_photos", schema="face_moment")

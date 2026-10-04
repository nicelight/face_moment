"""Persistent global photo tariff; prices are provisioned explicitly."""
from alembic import op
import sqlalchemy as sa

revision = "0029_global_photo_tariff"
down_revision = "0028_browser_search_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("photo_tariff",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("base_kopecks", sa.Numeric(), nullable=False),
        sa.Column("d1", sa.Numeric(), nullable=False),
        sa.Column("d2", sa.Numeric(), nullable=False),
        sa.Column("d3", sa.Numeric(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_photo_tariff_singleton"),
        sa.CheckConstraint("base_kopecks > 0 AND base_kopecks = trunc(base_kopecks) AND base_kopecks < 'Infinity'::numeric", name="ck_photo_tariff_base"),
        sa.CheckConstraint("1 >= d1 AND d1 >= d2 AND d2 >= d3 AND d3 > 0", name="ck_photo_tariff_coefficients"),
        sa.CheckConstraint("round(base_kopecks * d3) >= 1", name="ck_photo_tariff_paid_unit"),
        schema="face_moment")


def downgrade() -> None:
    op.drop_table("photo_tariff", schema="face_moment")

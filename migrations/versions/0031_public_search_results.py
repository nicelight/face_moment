"""Promo-owned current public result snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0031_public_search_results"
down_revision = "0030_venue_free_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("public_search_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("profile_id", sa.Uuid(), sa.ForeignKey("face_moment.browser_search_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("venue_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("pipeline_revision_id", sa.Uuid(), sa.ForeignKey("face_moment.pipeline_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("venues", postgresql.JSONB(), nullable=False), schema="face_moment")
    op.create_index("ix_public_results_profile_created", "public_search_results", ["profile_id", "created_at"], schema="face_moment")


def downgrade() -> None:
    op.drop_table("public_search_results", schema="face_moment")

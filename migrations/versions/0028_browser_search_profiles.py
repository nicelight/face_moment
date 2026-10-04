"""Hidden browser profiles and independent public identity threshold."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0028_browser_search_profiles"
down_revision = "0027_preview_phash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("browser_search_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("cookie_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("last_visit_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reset_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("a_embedding", ARRAY(sa.Float()), nullable=True),
        sa.Column("b_embedding", ARRAY(sa.Float()), nullable=True),
        sa.Column("a_pipeline_revision_id", sa.Uuid(), sa.ForeignKey("face_moment.pipeline_revisions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("b_pipeline_revision_id", sa.Uuid(), sa.ForeignKey("face_moment.pipeline_revisions.id", ondelete="RESTRICT"), nullable=True),
        sa.CheckConstraint("b_embedding IS NULL OR a_embedding IS NOT NULL", name="ck_browser_profile_b_requires_a"),
        sa.CheckConstraint("(a_embedding IS NULL) = (a_pipeline_revision_id IS NULL)", name="ck_browser_profile_a_revision"),
        sa.CheckConstraint("(b_embedding IS NULL) = (b_pipeline_revision_id IS NULL)", name="ck_browser_profile_b_revision"),
        schema="face_moment")
    op.create_table("public_search_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_similarity_threshold", sa.Float(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_public_search_settings_singleton"),
        sa.CheckConstraint("profile_similarity_threshold >= -1 AND profile_similarity_threshold <= 1", name="ck_public_search_settings_threshold"),
        schema="face_moment")
    op.execute("INSERT INTO face_moment.public_search_settings (id, profile_similarity_threshold) VALUES (1, 0.38)")


def downgrade() -> None:
    op.drop_table("browser_search_profiles", schema="face_moment")
    op.drop_table("public_search_settings", schema="face_moment")

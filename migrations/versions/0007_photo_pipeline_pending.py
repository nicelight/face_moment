"""Create processing-owned initial Photo pipeline state.

Revision ID: 0007_photo_pipeline_pending
Revises: 0006_photo_identity_persistence
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007_photo_pipeline_pending"
down_revision: str | Sequence[str] | None = "0006_photo_identity_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "photo_pipeline_states",
        sa.Column("photo_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_revision_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'no_faces', 'failed')",
            name="ck_photo_pipeline_states_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_photo_pipeline_states_attempt_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["photo_id"],
            ["face_moment.photos.id"],
            name="fk_photo_pipeline_states_photo_id_photos",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_revision_id"],
            ["face_moment.pipeline_revisions.id"],
            name="fk_photo_pipeline_states_pipeline_revision_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "photo_id", "pipeline_revision_id", name="pk_photo_pipeline_states"
        ),
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_table("photo_pipeline_states", schema="face_moment")

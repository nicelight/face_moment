"""Create serving-owned SPA ingest targets.

Revision ID: 0005_serving_ingest_targets
Revises: 0004_staff_sessions
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_serving_ingest_targets"
down_revision: str | Sequence[str] | None = "0004_staff_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("timezone", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("serving_pipeline_revision_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["serving_pipeline_revision_id"],
            ["face_moment.pipeline_revisions.id"],
            name="fk_spas_serving_pipeline_revision_id_pipeline_revisions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_spas"),
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_table("spas", schema="face_moment")

"""Create immutable processing pipeline revisions.

Revision ID: 0003_pipeline_revisions
Revises: 0002_staff_users
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_pipeline_revisions"
down_revision: str | Sequence[str] | None = "0002_staff_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pipeline_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_code", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "pipeline_code IN ('opencv_sface', 'insightface_buffalo_m')",
            name="ck_pipeline_revisions_pipeline_code",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_revisions"),
        schema="face_moment",
    )
    op.execute(
        """
        CREATE FUNCTION face_moment.reject_pipeline_revision_eligibility_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'pipeline revision identity and validated_at are immutable';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER pipeline_revisions_immutable
        BEFORE UPDATE OF id, pipeline_code, created_at, validated_at
        ON face_moment.pipeline_revisions
        FOR EACH ROW
        EXECUTE FUNCTION face_moment.reject_pipeline_revision_eligibility_update()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER pipeline_revisions_immutable "
        "ON face_moment.pipeline_revisions"
    )
    op.execute(
        "DROP FUNCTION face_moment.reject_pipeline_revision_eligibility_update()"
    )
    op.drop_table("pipeline_revisions", schema="face_moment")

"""Create opaque Staff Access browser sessions.

Revision ID: 0004_staff_sessions
Revises: 0003_pipeline_revisions
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_staff_sessions"
down_revision: str | Sequence[str] | None = "0003_pipeline_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("staff_user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "csrf_token_hash_sha256", sa.LargeBinary(length=32), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["face_moment.staff_users.id"],
            name="fk_staff_sessions_staff_user_id_staff_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_staff_sessions"),
        sa.UniqueConstraint(
            "token_hash_sha256", name="uq_staff_sessions_token_hash_sha256"
        ),
        schema="face_moment",
    )
    op.create_index(
        "ix_staff_sessions_staff_user_id",
        "staff_sessions",
        ["staff_user_id"],
        unique=False,
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_staff_sessions_staff_user_id",
        table_name="staff_sessions",
        schema="face_moment",
    )
    op.drop_table("staff_sessions", schema="face_moment")

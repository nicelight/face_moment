"""Create Staff Access principals.

Revision ID: 0002_staff_users
Revises: 0001_empty_foundation
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_staff_users"
down_revision: str | Sequence[str] | None = "0001_empty_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column(
            "active", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "username = lower(username)",
            name="ck_staff_users_username_normalized",
        ),
        sa.CheckConstraint(
            "role IN ('photographer', 'operator', 'developer')",
            name="staff_role",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_staff_users"),
        sa.UniqueConstraint("username", name="uq_staff_users_username"),
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_table("staff_users", schema="face_moment")

"""Create the empty Foundation application schema.

Revision ID: 0001_empty_foundation
Revises:
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_empty_foundation"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE SCHEMA IF NOT EXISTS face_moment")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS face_moment")


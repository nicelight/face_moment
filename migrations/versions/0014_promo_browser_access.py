"""Add the shared browser-access timestamps to promo sessions.

Revision ID: 0014_promo_browser_access
Revises: 0013_promo_sessions
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0014_promo_browser_access"
down_revision: str | Sequence[str] | None = "0013_promo_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "promo_sessions",
        sa.Column("browser_first_opened_at", sa.DateTime(timezone=True), nullable=True),
        schema="face_moment",
    )
    op.add_column(
        "promo_sessions",
        sa.Column("browser_last_seen_at", sa.DateTime(timezone=True), nullable=True),
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_promo_sessions_browser_access_timestamp_pair",
        "promo_sessions",
        "((browser_first_opened_at IS NULL AND browser_last_seen_at IS NULL) "
        "OR (browser_first_opened_at IS NOT NULL "
        "AND browser_last_seen_at IS NOT NULL "
        "AND browser_last_seen_at >= browser_first_opened_at))",
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_promo_sessions_browser_access_timestamp_pair",
        "promo_sessions",
        schema="face_moment",
        type_="check",
    )
    op.drop_column("promo_sessions", "browser_last_seen_at", schema="face_moment")
    op.drop_column("promo_sessions", "browser_first_opened_at", schema="face_moment")

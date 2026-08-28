"""Add the browser response marker to promo Attempts.

Revision ID: 0015_promo_attempt_client_timing
Revises: 0014_promo_browser_access
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0015_promo_attempt_client_timing"
down_revision: str | Sequence[str] | None = "0014_promo_browser_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "promo_attempts",
        sa.Column("response_received_ms", sa.Integer(), nullable=True),
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_promo_attempts_client_response_order",
        "promo_attempts",
        "response_received_ms IS NULL OR response_received_ms >= request_started_ms",
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_promo_attempts_client_response_order",
        "promo_attempts",
        schema="face_moment",
        type_="check",
    )
    op.drop_column("promo_attempts", "response_received_ms", schema="face_moment")

"""Create the singleton promo-owned retention cleanup result.

Revision ID: 0017_retention_cleanup_latest
Revises: 0016_diagnostic_evidence
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0017_retention_cleanup_latest"
down_revision: str | Sequence[str] | None = "0016_diagnostic_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retention_cleanup_latest",
        sa.Column("singleton_key", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("technical_logs_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempts_and_evidence_before",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("core_attempts_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "ordinary_evidence_expired",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("technical_logs_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "private_artifacts_deleted",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "promoted_subsets_preserved",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "singleton_key = 1",
            name="ck_retention_cleanup_latest_singleton_key",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'interrupted')",
            name="ck_retention_cleanup_latest_status",
        ),
        sa.CheckConstraint(
            "core_attempts_deleted >= 0 AND ordinary_evidence_expired >= 0 "
            "AND technical_logs_deleted >= 0 AND private_artifacts_deleted >= 0 "
            "AND promoted_subsets_preserved >= 0",
            name="ck_retention_cleanup_latest_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND error IS NULL) OR "
            "(status = 'succeeded' AND finished_at IS NOT NULL AND error IS NULL) OR "
            "(status IN ('failed', 'interrupted') AND finished_at IS NOT NULL "
            "AND error IS NOT NULL)",
            name="ck_retention_cleanup_latest_terminal_shape",
        ),
        sa.PrimaryKeyConstraint("singleton_key"),
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_table("retention_cleanup_latest", schema="face_moment")

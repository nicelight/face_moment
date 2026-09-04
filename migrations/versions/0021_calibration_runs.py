"""Create diagnostics-owned immutable Calibration runs.

Revision ID: 0021_calibration_runs
Revises: 0020_annotation_name_whitespace
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0021_calibration_runs"
down_revision: str | Sequence[str] | None = "0020_annotation_name_whitespace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calibration_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_staff_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("dataset_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dataset_sha256", sa.String(length=64), nullable=False),
        sa.Column("result_bundle", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('requested', 'running', 'complete', 'failed', 'interrupted')",
            name="ck_calibration_runs_status",
        ),
        sa.CheckConstraint(
            "char_length(dataset_sha256) = 64",
            name="ck_calibration_runs_dataset_sha256_length",
        ),
        sa.CheckConstraint(
            "octet_length(dataset_snapshot::text) <= 1048576",
            name="ck_calibration_runs_dataset_snapshot_size",
        ),
        sa.CheckConstraint(
            "result_bundle IS NULL OR octet_length(result_bundle::text) <= 1048576",
            name="ck_calibration_runs_result_bundle_size",
        ),
        sa.CheckConstraint(
            "(status = 'complete' AND result_bundle IS NOT NULL AND error_code IS NULL "
            "AND started_at IS NOT NULL AND finished_at IS NOT NULL) OR "
            "(status IN ('requested', 'running') AND result_bundle IS NULL "
            "AND error_code IS NULL AND finished_at IS NULL) OR "
            "(status IN ('failed', 'interrupted') AND result_bundle IS NULL "
            "AND error_code IS NOT NULL AND started_at IS NOT NULL AND finished_at IS NOT NULL)",
            name="ck_calibration_runs_terminal_shape",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_calibration_runs"),
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_table("calibration_runs", schema="face_moment")

"""Create the diagnostics-owned versioned evidence table.

Revision ID: 0016_diagnostic_evidence
Revises: 0015_promo_attempt_client_timing
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa


revision: str = "0016_diagnostic_evidence"
down_revision: str | Sequence[str] | None = "0015_promo_attempt_client_timing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("completeness", sa.String(length=16), nullable=False),
        sa.Column("gap_reason", sa.String(length=255), nullable=True),
        sa.Column(
            "issue_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("ordinary_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("promoted_subset", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ordinary_expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "schema_version > 0",
            name="ck_diagnostic_evidence_schema_version_positive",
        ),
        sa.CheckConstraint(
            "completeness IN ('incomplete', 'complete')",
            name="ck_diagnostic_evidence_completeness",
        ),
        sa.CheckConstraint(
            "(completeness = 'incomplete' AND gap_reason IS NOT NULL "
            "AND length(btrim(gap_reason)) > 0) OR "
            "(completeness = 'complete' AND gap_reason IS NULL)",
            name="ck_diagnostic_evidence_gap_matches_completeness",
        ),
        sa.CheckConstraint(
            "(completeness = 'incomplete' AND finalized_at IS NULL) OR "
            "(completeness = 'complete' AND finalized_at IS NOT NULL)",
            name="ck_diagnostic_evidence_finalized_matches_completeness",
        ),
        sa.CheckConstraint(
            "(promoted_subset IS NULL AND promoted_at IS NULL) OR "
            "(promoted_subset IS NOT NULL AND promoted_at IS NOT NULL)",
            name="ck_diagnostic_evidence_promotion_pair",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id",
            "schema_version",
            name="uq_diagnostic_evidence_attempt_schema_version",
        ),
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_table("diagnostic_evidence", schema="face_moment")

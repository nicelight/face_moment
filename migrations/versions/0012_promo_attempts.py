"""Create the promo-owned core Attempt table.

Revision ID: 0012_promo_attempts
Revises: 0011_active_search_context
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0012_promo_attempts"
down_revision: str | Sequence[str] | None = "0011_active_search_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "promo_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("spa_id", sa.Uuid(), nullable=False),
        sa.Column("client_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_source", sa.String(length=16), nullable=False),
        sa.Column("client_release", sa.String(length=255), nullable=False),
        sa.Column("detector_id", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=False),
        sa.Column("jpeg_quality", sa.Integer(), nullable=False),
        sa.Column("camera_device_id", sa.String(length=255), nullable=False),
        sa.Column("reference_series_ready_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_detection_completed_ms", sa.Integer(), nullable=False),
        sa.Column("request_started_ms", sa.Integer(), nullable=False),
        sa.Column("proposal_count", sa.Integer(), nullable=False),
        sa.Column("settings_revision", sa.Integer(), nullable=False),
        sa.Column("visit_date", sa.Date(), nullable=True),
        sa.Column("pipeline_revision_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_code", sa.String(length=32), nullable=False),
        sa.Column("query_source", sa.String(length=32), nullable=False),
        sa.Column("release_id", sa.String(length=255), nullable=False),
        sa.Column("threshold", sa.Double(), nullable=False),
        sa.Column("quality_settings", sa.JSON(), nullable=False),
        sa.Column("calibration_id", sa.Uuid(), nullable=True),
        sa.Column("deadline_ms", sa.Integer(), nullable=False),
        sa.Column("slot_decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("search_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("search_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_status", sa.String(length=32), server_default="accepted", nullable=False),
        sa.Column("domain_outcome", sa.String(length=32), nullable=True),
        sa.Column("display_status", sa.String(length=32), server_default="not_applicable", nullable=False),
        sa.Column("display_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("display_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("qr_fully_visible_elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "trigger_source IN ('sensor', 'test')",
            name="ck_promo_attempts_trigger_source",
        ),
        sa.CheckConstraint(
            "jpeg_quality BETWEEN 1 AND 100",
            name="ck_promo_attempts_jpeg_quality_range",
        ),
        sa.CheckConstraint(
            "local_detection_completed_ms >= 0 AND request_started_ms >= 0",
            name="ck_promo_attempts_client_offsets_nonnegative",
        ),
        sa.CheckConstraint(
            "proposal_count BETWEEN 0 AND 20",
            name="ck_promo_attempts_proposal_count_range",
        ),
        sa.CheckConstraint(
            "settings_revision > 0",
            name="ck_promo_attempts_settings_revision_positive",
        ),
        sa.CheckConstraint(
            "pipeline_code IN ('opencv_sface', 'insightface_buffalo_m')",
            name="ck_promo_attempts_pipeline_code",
        ),
        sa.CheckConstraint(
            "query_source = 'reference'",
            name="ck_promo_attempts_query_source",
        ),
        sa.CheckConstraint(
            "deadline_ms > 0",
            name="ck_promo_attempts_deadline_positive",
        ),
        sa.CheckConstraint(
            "processing_status IN ('accepted', 'searching', 'result_issued', 'no_success', 'interrupted', 'deadline', 'internal_failure')",
            name="ck_promo_attempts_processing_status",
        ),
        sa.CheckConstraint(
            "domain_outcome IS NULL OR domain_outcome IN ('result', 'no_proposals', 'busy', 'deadline', 'unacceptable_query', 'insufficient_results', 'interrupted')",
            name="ck_promo_attempts_domain_outcome",
        ),
        sa.CheckConstraint(
            "display_status IN ('not_applicable', 'pending', 'confirmed', 'failed')",
            name="ck_promo_attempts_display_status",
        ),
        sa.CheckConstraint(
            "qr_fully_visible_elapsed_ms IS NULL OR qr_fully_visible_elapsed_ms >= 0",
            name="ck_promo_attempts_qr_elapsed_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_promo_attempts"),
        sa.UniqueConstraint(
            "spa_id", "client_attempt_id", name="uq_promo_attempts_spa_client_attempt"
        ),
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_table("promo_attempts", schema="face_moment")

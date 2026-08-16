"""Persist serving-control active-search context inputs.

Revision ID: 0011_active_search_context
Revises: 0010_display_clients
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0011_active_search_context"
down_revision: str | Sequence[str] | None = "0010_display_clients"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "spas",
        sa.Column("active_visit_date", sa.Date(), nullable=True),
        schema="face_moment",
    )
    op.add_column(
        "spas",
        sa.Column("settings_revision", sa.Integer(), server_default="1", nullable=False),
        schema="face_moment",
    )
    op.add_column(
        "spas",
        sa.Column("settings_updated_at", sa.DateTime(timezone=True), nullable=True),
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_spas_settings_revision_positive",
        "spas",
        "settings_revision > 0",
        schema="face_moment",
    )
    op.create_table(
        "reference_search_settings",
        sa.Column("spa_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_code", sa.String(length=32), nullable=False),
        sa.Column("query_source", sa.String(length=32), nullable=False),
        sa.Column("reference_threshold", sa.Double(), nullable=False),
        sa.Column("min_query_face_quality", sa.Double(), nullable=False),
        sa.Column("quality_settings", sa.JSON(), nullable=False),
        sa.Column("calibration_id", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "pipeline_code IN ('opencv_sface', 'insightface_buffalo_m')",
            name="ck_reference_search_settings_pipeline_code",
        ),
        sa.CheckConstraint(
            "query_source = 'reference'",
            name="ck_reference_search_settings_query_source",
        ),
        sa.ForeignKeyConstraint(
            ["spa_id"],
            ["face_moment.spas.id"],
            name="fk_reference_search_settings_spa_id_spas",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "spa_id",
            "pipeline_code",
            "query_source",
            name="pk_reference_search_settings",
        ),
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_table("reference_search_settings", schema="face_moment")
    op.drop_constraint(
        "ck_spas_settings_revision_positive",
        "spas",
        schema="face_moment",
        type_="check",
    )
    op.drop_column("spas", "settings_updated_at", schema="face_moment")
    op.drop_column("spas", "settings_revision", schema="face_moment")
    op.drop_column("spas", "active_visit_date", schema="face_moment")

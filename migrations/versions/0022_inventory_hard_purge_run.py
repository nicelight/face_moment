"""Add the inventory-owned singleton fixed-snapshot purge run."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0022_inventory_hard_purge_run"
down_revision = "0021_calibration_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_hard_purge_run",
        sa.Column("singleton_id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("target_photo_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("singleton_id = 1", name="ck_inventory_purge_singleton"),
        sa.CheckConstraint(
            "state IN ('confirmed_waiting', 'running', 'completed')",
            name="ck_inventory_purge_state",
        ),
        sa.CheckConstraint(
            "completed_count >= 0 AND completed_count <= cardinality(target_photo_ids)",
            name="ck_inventory_purge_prefix",
        ),
        sa.CheckConstraint(
            "(state = 'confirmed_waiting' AND started_at IS NULL AND completed_at IS NULL "
            "AND completed_count = 0 AND cardinality(target_photo_ids) > 0) OR "
            "(state = 'running' AND started_at IS NOT NULL AND completed_at IS NULL "
            "AND completed_count < cardinality(target_photo_ids)) OR "
            "(state = 'completed' AND completed_at IS NOT NULL "
            "AND completed_count = cardinality(target_photo_ids))",
            name="ck_inventory_purge_lifecycle",
        ),
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_table("inventory_hard_purge_run", schema="face_moment")

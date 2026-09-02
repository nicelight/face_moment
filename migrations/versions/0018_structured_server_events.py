"""Create diagnostics-owned structured server events.

Revision ID: 0018_structured_server_events
Revises: 0017_retention_cleanup_latest
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0018_structured_server_events"
down_revision: str | Sequence[str] | None = "0017_retention_cleanup_latest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CATALOG_SHAPE = " OR ".join(
    (
        "(event_code = 'runtime.readiness_closed' AND severity = 'warning' AND component = 'runtime')",
        "(event_code = 'attempt.admitted' AND severity = 'info' AND component = 'realtime')",
        "(event_code = 'attempt.failed' AND severity = 'error' AND component = 'realtime')",
        "(event_code = 'promo.result_issued' AND severity = 'info' AND component = 'promo')",
        "(event_code = 'promo.display_confirmed' AND severity = 'info' AND component = 'promo')",
        "(event_code = 'qr.session_opened' AND severity = 'info' AND component = 'qr')",
        "(event_code = 'qr.session_expired' AND severity = 'warning' AND component = 'qr')",
    )
)


def upgrade() -> None:
    op.create_table(
        "server_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("severity", sa.String(length=7), nullable=False),
        sa.Column("component", sa.String(length=8), nullable=False),
        sa.Column("event_code", sa.String(length=32), nullable=False),
        sa.Column("release_id", sa.String(length=128), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'error')",
            name="ck_server_events_severity",
        ),
        sa.CheckConstraint(
            "component IN ('runtime', 'realtime', 'promo', 'qr')",
            name="ck_server_events_component",
        ),
        sa.CheckConstraint(
            _CATALOG_SHAPE,
            name="ck_server_events_catalog_shape",
        ),
        sa.CheckConstraint(
            "char_length(release_id) BETWEEN 1 AND 128",
            name="ck_server_events_release_id_length",
        ),
        sa.CheckConstraint(
            "(event_code = 'runtime.readiness_closed' AND attempt_id IS NULL AND correlation_id IS NULL) OR "
            "(event_code IN ('attempt.admitted', 'attempt.failed', 'promo.result_issued', "
            "'promo.display_confirmed', 'qr.session_opened') AND attempt_id IS NOT NULL "
            "AND correlation_id IS NOT NULL) OR "
            "(event_code = 'qr.session_expired' AND ((attempt_id IS NULL AND correlation_id IS NULL) "
            "OR (attempt_id IS NOT NULL AND correlation_id IS NOT NULL)))",
            name="ck_server_events_correlation_shape",
        ),
        sa.PrimaryKeyConstraint("event_id"),
        schema="face_moment",
    )
    op.create_index(
        "ix_server_events_occurred_at",
        "server_events",
        [sa.text("occurred_at DESC")],
        schema="face_moment",
    )
    op.create_index(
        "ix_server_events_attempt_id",
        "server_events",
        ["attempt_id"],
        schema="face_moment",
    )
    op.create_index(
        "ix_server_events_correlation_id",
        "server_events",
        ["correlation_id"],
        schema="face_moment",
    )
    op.create_index(
        "ix_server_events_severity_component_code",
        "server_events",
        ["severity", "component", "event_code"],
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_server_events_severity_component_code",
        table_name="server_events",
        schema="face_moment",
    )
    op.drop_index(
        "ix_server_events_correlation_id",
        table_name="server_events",
        schema="face_moment",
    )
    op.drop_index(
        "ix_server_events_attempt_id",
        table_name="server_events",
        schema="face_moment",
    )
    op.drop_index(
        "ix_server_events_occurred_at",
        table_name="server_events",
        schema="face_moment",
    )
    op.drop_table("server_events", schema="face_moment")

"""Per-SPA automatic today/manual range and immutable result range ends."""

from alembic import op
import sqlalchemy as sa

revision = "0023_search_date_ranges"
down_revision = "0022_inventory_hard_purge_run"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("spas", sa.Column("search_today", sa.Boolean(), nullable=False,
                                  server_default=sa.true()), schema="face_moment")
    op.add_column("spas", sa.Column("active_visit_date_to", sa.Date()), schema="face_moment")
    # Retain the previous manual day for switching back, but start in auto mode.
    op.execute("UPDATE face_moment.spas SET active_visit_date_to = active_visit_date, "
               "settings_revision = settings_revision + 1, settings_updated_at = now()")
    for table in ("promo_attempts", "promo_sessions"):
        # NULL end denotes a historical single-day record; no history rewrite.
        op.add_column(table, sa.Column("visit_date_to", sa.Date()), schema="face_moment")


def downgrade() -> None:
    for table in ("promo_sessions", "promo_attempts"):
        op.drop_column(table, "visit_date_to", schema="face_moment")
    op.drop_column("spas", "active_visit_date_to", schema="face_moment")
    op.drop_column("spas", "search_today", schema="face_moment")

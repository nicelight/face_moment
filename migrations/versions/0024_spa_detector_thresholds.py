"""Per-SPA detector settings and immutable photographer-photo threshold."""

from alembic import op
import sqlalchemy as sa

revision = "0024_spa_detector_thresholds"
down_revision = "0023_search_date_ranges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, column, default, constraint in (
        ("spas", "photo_yunet_threshold", "0.9", "ck_spas_photo_yunet_threshold"),
        ("spas", "capture_blazeface_threshold", "0.5", "ck_spas_capture_blazeface_threshold"),
        ("photos", "photo_yunet_threshold", "0.9", "ck_photos_yunet_threshold"),
    ):
        op.add_column(table, sa.Column(column, sa.Float(), nullable=False,
                                     server_default=default), schema="face_moment")
        op.create_check_constraint(constraint, table, f"{column} > 0 AND {column} <= 1",
                                   schema="face_moment")


def downgrade() -> None:
    for table, column, constraint in (
        ("photos", "photo_yunet_threshold", "ck_photos_yunet_threshold"),
        ("spas", "capture_blazeface_threshold", "ck_spas_capture_blazeface_threshold"),
        ("spas", "photo_yunet_threshold", "ck_spas_photo_yunet_threshold"),
    ):
        op.drop_constraint(constraint, table, schema="face_moment", type_="check")
        op.drop_column(table, column, schema="face_moment")

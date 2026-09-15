"""Global people and labels on existing processed photo faces."""
from alembic import op
import sqlalchemy as sa

revision = "0025_capture_identity_labels"
down_revision = "0024_spa_detector_thresholds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_people",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_diagnostic_people_name"),
        schema="face_moment",
    )
    op.create_table(
        "diagnostic_face_labels",
        sa.Column("face_id", sa.Uuid(), primary_key=True),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey(
            "face_moment.diagnostic_people.id", ondelete="CASCADE"), nullable=False),
        schema="face_moment",
    )
    op.create_index("ix_diagnostic_face_labels_person", "diagnostic_face_labels",
                    ["person_id"], schema="face_moment")


def downgrade() -> None:
    op.drop_table("diagnostic_face_labels", schema="face_moment")
    op.drop_table("diagnostic_people", schema="face_moment")

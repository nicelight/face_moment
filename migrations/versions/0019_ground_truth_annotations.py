"""Create diagnostics-owned normalized ground-truth annotations.

Revision ID: 0019_ground_truth_annotations
Revises: 0018_structured_server_events
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0019_ground_truth_annotations"
down_revision: str | Sequence[str] | None = "0018_structured_server_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ground_truth_annotations",
        sa.Column("annotation_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("target_kind", sa.String(length=16), nullable=False),
        sa.Column("detection_occurrence_index", sa.Integer(), nullable=True),
        sa.Column("participant_name", sa.String(length=200), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "target_kind IN ('detection', 'person')",
            name="ck_ground_truth_annotations_target_kind",
        ),
        sa.CheckConstraint(
            "outcome IN ('correct', 'false', 'missed')",
            name="ck_ground_truth_annotations_outcome",
        ),
        sa.CheckConstraint(
            "char_length(btrim(participant_name)) BETWEEN 1 AND 200",
            name="ck_ground_truth_annotations_participant_name",
        ),
        sa.CheckConstraint(
            "(target_kind = 'detection' AND detection_occurrence_index IS NOT NULL "
            "AND detection_occurrence_index >= 0 AND outcome IN ('correct', 'false')) OR "
            "(target_kind = 'person' AND detection_occurrence_index IS NULL "
            "AND outcome = 'missed')",
            name="ck_ground_truth_annotations_target_outcome_shape",
        ),
        sa.PrimaryKeyConstraint("annotation_id"),
        schema="face_moment",
    )
    op.create_index(
        "uq_ground_truth_annotations_detection_target",
        "ground_truth_annotations",
        ["attempt_id", "detection_occurrence_index"],
        unique=True,
        schema="face_moment",
        postgresql_where=sa.text("target_kind = 'detection'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ground_truth_annotations_detection_target",
        table_name="ground_truth_annotations",
        schema="face_moment",
    )
    op.drop_table("ground_truth_annotations", schema="face_moment")

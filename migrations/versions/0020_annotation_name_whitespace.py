"""Align annotation-name whitespace validation with Python ``str.strip()``.

Revision ID: 0020_annotation_name_whitespace
Revises: 0019_ground_truth_annotations
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0020_annotation_name_whitespace"
down_revision: str | Sequence[str] | None = "0019_ground_truth_annotations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_ground_truth_annotations_participant_name",
        "ground_truth_annotations",
        schema="face_moment",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ground_truth_annotations_participant_name",
        "ground_truth_annotations",
        r"char_length(btrim(participant_name, "
        r"U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020"
        r"\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006"
        r"\2007\2008\2009\200A\2028\2029\202F\205F\3000')) "
        "BETWEEN 1 AND 200",
        schema="face_moment",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ground_truth_annotations_participant_name",
        "ground_truth_annotations",
        schema="face_moment",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ground_truth_annotations_participant_name",
        "ground_truth_annotations",
        "char_length(btrim(participant_name)) BETWEEN 1 AND 200",
        schema="face_moment",
    )

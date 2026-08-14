"""Persist immutable Photo admission-revision lineage.

Revision ID: 0009_photo_admission_lineage
Revises: 0008_processing_persistence
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0009_photo_admission_lineage"
down_revision: str | Sequence[str] | None = "0008_processing_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _assert_photos_empty() -> None:
    connection = op.get_bind()
    has_photo = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM face_moment.photos)")
    ).scalar_one()
    if has_photo:
        raise RuntimeError(
            "face_moment.photos must be empty before the admission lineage cutover"
        )


def upgrade() -> None:
    _assert_photos_empty()

    op.add_column(
        "photos",
        sa.Column("admission_pipeline_revision_id", sa.Uuid(), nullable=False),
        schema="face_moment",
    )
    op.create_foreign_key(
        "fk_photos_admission_pipeline_revision_id_pipeline_revisions",
        "photos",
        "pipeline_revisions",
        ["admission_pipeline_revision_id"],
        ["id"],
        source_schema="face_moment",
        referent_schema="face_moment",
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_photos_admission_pipeline_revision_id_pipeline_revisions",
        "photos",
        type_="foreignkey",
        schema="face_moment",
    )
    op.drop_column("photos", "admission_pipeline_revision_id", schema="face_moment")

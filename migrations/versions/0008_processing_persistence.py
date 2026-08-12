"""Extend processing compatibility and persistence shape.

Revision ID: 0008_processing_persistence
Revises: 0007_photo_pipeline_pending
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0008_processing_persistence"
down_revision: str | Sequence[str] | None = "0007_photo_pipeline_pending"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class Vector(sa.types.UserDefinedType[object]):
    cache_ok = True

    def get_col_spec(self, **_kw: object) -> str:
        return "vector"


def _assert_no_legacy_pipeline_revisions() -> None:
    connection = op.get_bind()
    has_legacy_revision = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM face_moment.pipeline_revisions)")
    ).scalar_one()
    if has_legacy_revision:
        raise RuntimeError(
            "face_moment.pipeline_revisions must be empty before the "
            "processing compatibility cutover"
        )


def _replace_pipeline_revision_immutability_trigger() -> None:
    op.execute("DROP TRIGGER pipeline_revisions_immutable ON face_moment.pipeline_revisions")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION face_moment.reject_pipeline_revision_eligibility_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF OLD.id IS DISTINCT FROM NEW.id
                OR OLD.pipeline_code IS DISTINCT FROM NEW.pipeline_code
                OR OLD.created_at IS DISTINCT FROM NEW.created_at
                OR OLD.validated_at IS DISTINCT FROM NEW.validated_at
            THEN
                RAISE EXCEPTION
                    'pipeline revision identity and validated_at are immutable';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM face_moment.photo_pipeline_states
                WHERE pipeline_revision_id = OLD.id
            ) AND (
                OLD.detector_id IS DISTINCT FROM NEW.detector_id
                OR OLD.detector_version IS DISTINCT FROM NEW.detector_version
                OR OLD.recognizer_id IS DISTINCT FROM NEW.recognizer_id
                OR OLD.recognizer_version IS DISTINCT FROM NEW.recognizer_version
                OR OLD.weights_sha256 IS DISTINCT FROM NEW.weights_sha256
                OR OLD.preprocessing_version IS DISTINCT FROM NEW.preprocessing_version
                OR OLD.alignment_version IS DISTINCT FROM NEW.alignment_version
                OR OLD.normalization_version IS DISTINCT FROM NEW.normalization_version
                OR OLD.embedding_dimension IS DISTINCT FROM NEW.embedding_dimension
            ) THEN
                RAISE EXCEPTION
                    'referenced pipeline revision compatibility identity is immutable';
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER pipeline_revisions_immutable
        BEFORE UPDATE OF id, pipeline_code, created_at, validated_at, detector_id,
            detector_version, recognizer_id, recognizer_version, weights_sha256,
            preprocessing_version, alignment_version, normalization_version,
            embedding_dimension
        ON face_moment.pipeline_revisions
        FOR EACH ROW
        EXECUTE FUNCTION face_moment.reject_pipeline_revision_eligibility_update()
        """
    )


def _restore_pipeline_revision_immutability_trigger() -> None:
    op.execute("DROP TRIGGER pipeline_revisions_immutable ON face_moment.pipeline_revisions")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION face_moment.reject_pipeline_revision_eligibility_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'pipeline revision identity and validated_at are immutable';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER pipeline_revisions_immutable
        BEFORE UPDATE OF id, pipeline_code, created_at, validated_at
        ON face_moment.pipeline_revisions
        FOR EACH ROW
        EXECUTE FUNCTION face_moment.reject_pipeline_revision_eligibility_update()
        """
    )


def _create_photo_face_embedding_dimension_trigger() -> None:
    op.execute(
        """
        CREATE FUNCTION face_moment.require_photo_face_embedding_dimension()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            expected_dimension integer;
        BEGIN
            SELECT embedding_dimension
            INTO expected_dimension
            FROM face_moment.pipeline_revisions
            WHERE id = NEW.pipeline_revision_id;

            IF expected_dimension IS NULL
                OR vector_dims(NEW.embedding) <> expected_dimension
            THEN
                RAISE EXCEPTION
                    'photo face embedding dimension must match pipeline revision';
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER photo_faces_embedding_dimension_matches_revision
        BEFORE INSERT OR UPDATE OF pipeline_revision_id, embedding
        ON face_moment.photo_faces
        FOR EACH ROW
        EXECUTE FUNCTION face_moment.require_photo_face_embedding_dimension()
        """
    )


def upgrade() -> None:
    _assert_no_legacy_pipeline_revisions()

    op.add_column(
        "pipeline_revisions",
        sa.Column("detector_id", sa.String(length=128), nullable=False),
        schema="face_moment",
    )
    op.add_column(
        "pipeline_revisions",
        sa.Column("detector_version", sa.String(length=128), nullable=False),
        schema="face_moment",
    )
    op.add_column(
        "pipeline_revisions",
        sa.Column("recognizer_id", sa.String(length=128), nullable=False),
        schema="face_moment",
    )
    op.add_column(
        "pipeline_revisions",
        sa.Column("recognizer_version", sa.String(length=128), nullable=False),
        schema="face_moment",
    )
    op.add_column(
        "pipeline_revisions",
        sa.Column("weights_sha256", sa.String(length=64), nullable=False),
        schema="face_moment",
    )
    op.add_column(
        "pipeline_revisions",
        sa.Column("preprocessing_version", sa.String(length=128), nullable=False),
        schema="face_moment",
    )
    op.add_column(
        "pipeline_revisions",
        sa.Column("alignment_version", sa.String(length=128), nullable=False),
        schema="face_moment",
    )
    op.add_column(
        "pipeline_revisions",
        sa.Column("normalization_version", sa.String(length=128), nullable=False),
        schema="face_moment",
    )
    op.add_column(
        "pipeline_revisions",
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_pipeline_revisions_detector_id_present",
        "pipeline_revisions",
        "btrim(detector_id) <> ''",
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_pipeline_revisions_detector_version_present",
        "pipeline_revisions",
        "btrim(detector_version) <> ''",
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_pipeline_revisions_recognizer_id_present",
        "pipeline_revisions",
        "btrim(recognizer_id) <> ''",
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_pipeline_revisions_recognizer_version_present",
        "pipeline_revisions",
        "btrim(recognizer_version) <> ''",
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_pipeline_revisions_weights_sha256",
        "pipeline_revisions",
        "weights_sha256 ~ '^[0-9a-f]{64}$'",
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_pipeline_revisions_preprocessing_version_present",
        "pipeline_revisions",
        "btrim(preprocessing_version) <> ''",
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_pipeline_revisions_alignment_version_present",
        "pipeline_revisions",
        "btrim(alignment_version) <> ''",
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_pipeline_revisions_normalization_version_present",
        "pipeline_revisions",
        "btrim(normalization_version) <> ''",
        schema="face_moment",
    )
    op.create_check_constraint(
        "ck_pipeline_revisions_embedding_dimension_positive",
        "pipeline_revisions",
        "embedding_dimension > 0",
        schema="face_moment",
    )
    _replace_pipeline_revision_immutability_trigger()

    op.add_column(
        "photo_pipeline_states",
        sa.Column("searchable_at", sa.DateTime(timezone=True), nullable=True),
        schema="face_moment",
    )
    op.add_column(
        "photo_pipeline_states",
        sa.Column("last_error", sa.String(length=512), nullable=True),
        schema="face_moment",
    )
    op.add_column(
        "photo_pipeline_states",
        sa.Column("preview_object_key", sa.String(), nullable=True),
        schema="face_moment",
    )
    op.add_column(
        "photo_pipeline_states",
        sa.Column("thumbnail_object_key", sa.String(), nullable=True),
        schema="face_moment",
    )

    op.create_table(
        "photo_faces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("photo_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_revision_id", sa.Uuid(), nullable=False),
        sa.Column("face_index", sa.Integer(), nullable=False),
        sa.Column("bbox_x", sa.Double(), nullable=False),
        sa.Column("bbox_y", sa.Double(), nullable=False),
        sa.Column("bbox_w", sa.Double(), nullable=False),
        sa.Column("bbox_h", sa.Double(), nullable=False),
        sa.Column("landmarks_json", sa.JSON(), nullable=False),
        sa.Column("detection_confidence", sa.Double(), nullable=False),
        sa.Column("quality_score", sa.Double(), nullable=True),
        sa.Column("blur_score", sa.Double(), nullable=True),
        sa.Column("brightness_score", sa.Double(), nullable=True),
        sa.Column("pose_yaw", sa.Double(), nullable=True),
        sa.Column("pose_pitch", sa.Double(), nullable=True),
        sa.Column("pose_roll", sa.Double(), nullable=True),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("bbox_w > 0", name="ck_photo_faces_bbox_w_positive"),
        sa.CheckConstraint("bbox_h > 0", name="ck_photo_faces_bbox_h_positive"),
        sa.CheckConstraint(
            "bbox_x NOT IN ('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision) AND bbox_y NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision) AND bbox_w NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision) AND bbox_h NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision) AND detection_confidence NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_required_values_finite",
        ),
        sa.CheckConstraint(
            "quality_score IS NULL OR quality_score NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_quality_score_finite",
        ),
        sa.CheckConstraint(
            "blur_score IS NULL OR blur_score NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_blur_score_finite",
        ),
        sa.CheckConstraint(
            "brightness_score IS NULL OR brightness_score NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_brightness_score_finite",
        ),
        sa.CheckConstraint(
            "pose_yaw IS NULL OR pose_yaw NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_pose_yaw_finite",
        ),
        sa.CheckConstraint(
            "pose_pitch IS NULL OR pose_pitch NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_pose_pitch_finite",
        ),
        sa.CheckConstraint(
            "pose_roll IS NULL OR pose_roll NOT IN "
            "('NaN'::double precision, 'Infinity'::double precision, "
            "'-Infinity'::double precision)",
            name="ck_photo_faces_pose_roll_finite",
        ),
        sa.ForeignKeyConstraint(
            ["photo_id"],
            ["face_moment.photos.id"],
            name="fk_photo_faces_photo_id_photos",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_revision_id"],
            ["face_moment.pipeline_revisions.id"],
            name="fk_photo_faces_pipeline_revision_id_pipeline_revisions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_photo_faces"),
        sa.UniqueConstraint(
            "photo_id",
            "pipeline_revision_id",
            "face_index",
            name="uq_photo_faces_photo_revision_face_index",
        ),
        schema="face_moment",
    )
    _create_photo_face_embedding_dimension_trigger()

    op.create_table(
        "processing_runtime_status",
        sa.Column("singleton_id", sa.Integer(), nullable=False),
        sa.Column("worker_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_recovery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_recovered_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "current_operation",
            sa.String(length=20),
            server_default="idle",
            nullable=False,
        ),
        sa.Column("operation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "singleton_id = 1", name="ck_processing_runtime_status_singleton"
        ),
        sa.CheckConstraint(
            "last_recovered_count >= 0",
            name="ck_processing_runtime_status_recovered_count_nonnegative",
        ),
        sa.CheckConstraint(
            "current_operation IN "
            "('idle', 'photo_processing', 'calibration', 'hard_purge', "
            "'retention_cleanup')",
            name="ck_processing_runtime_status_operation",
        ),
        sa.CheckConstraint(
            "(current_operation = 'idle' AND operation_started_at IS NULL) "
            "OR (current_operation <> 'idle' AND operation_started_at IS NOT NULL)",
            name="ck_processing_runtime_status_operation_started_at",
        ),
        sa.PrimaryKeyConstraint("singleton_id", name="pk_processing_runtime_status"),
        schema="face_moment",
    )
    op.execute(
        "INSERT INTO face_moment.processing_runtime_status (singleton_id) VALUES (1)"
    )


def downgrade() -> None:
    op.drop_table("processing_runtime_status", schema="face_moment")
    op.execute(
        "DROP TRIGGER photo_faces_embedding_dimension_matches_revision "
        "ON face_moment.photo_faces"
    )
    op.execute("DROP FUNCTION face_moment.require_photo_face_embedding_dimension()")
    op.drop_table("photo_faces", schema="face_moment")

    op.drop_column("photo_pipeline_states", "thumbnail_object_key", schema="face_moment")
    op.drop_column("photo_pipeline_states", "preview_object_key", schema="face_moment")
    op.drop_column("photo_pipeline_states", "last_error", schema="face_moment")
    op.drop_column("photo_pipeline_states", "searchable_at", schema="face_moment")

    _restore_pipeline_revision_immutability_trigger()
    op.drop_constraint(
        "ck_pipeline_revisions_embedding_dimension_positive",
        "pipeline_revisions",
        schema="face_moment",
    )
    op.drop_constraint(
        "ck_pipeline_revisions_normalization_version_present",
        "pipeline_revisions",
        schema="face_moment",
    )
    op.drop_constraint(
        "ck_pipeline_revisions_alignment_version_present",
        "pipeline_revisions",
        schema="face_moment",
    )
    op.drop_constraint(
        "ck_pipeline_revisions_preprocessing_version_present",
        "pipeline_revisions",
        schema="face_moment",
    )
    op.drop_constraint(
        "ck_pipeline_revisions_weights_sha256",
        "pipeline_revisions",
        schema="face_moment",
    )
    op.drop_constraint(
        "ck_pipeline_revisions_recognizer_version_present",
        "pipeline_revisions",
        schema="face_moment",
    )
    op.drop_constraint(
        "ck_pipeline_revisions_recognizer_id_present",
        "pipeline_revisions",
        schema="face_moment",
    )
    op.drop_constraint(
        "ck_pipeline_revisions_detector_version_present",
        "pipeline_revisions",
        schema="face_moment",
    )
    op.drop_constraint(
        "ck_pipeline_revisions_detector_id_present",
        "pipeline_revisions",
        schema="face_moment",
    )
    op.drop_column("pipeline_revisions", "embedding_dimension", schema="face_moment")
    op.drop_column("pipeline_revisions", "normalization_version", schema="face_moment")
    op.drop_column("pipeline_revisions", "alignment_version", schema="face_moment")
    op.drop_column("pipeline_revisions", "preprocessing_version", schema="face_moment")
    op.drop_column("pipeline_revisions", "weights_sha256", schema="face_moment")
    op.drop_column("pipeline_revisions", "recognizer_version", schema="face_moment")
    op.drop_column("pipeline_revisions", "recognizer_id", schema="face_moment")
    op.drop_column("pipeline_revisions", "detector_version", schema="face_moment")
    op.drop_column("pipeline_revisions", "detector_id", schema="face_moment")

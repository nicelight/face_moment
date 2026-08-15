"""Processing capability seam used by the Foundation proof."""

from face_moment.processing.face_engine import FaceEngine, FakeFaceEngine
from face_moment.processing.initial_pending import InitialPendingRepository
from face_moment.processing.revisions import (
    EligiblePipelineRevision,
    IneligiblePipelineRevisionError,
    PipelineCode,
    PipelineRevisionRepository,
    UnsupportedPipelineCodeError,
)
from face_moment.processing.searchable_projection import read_photo_processing_projection
from face_moment.processing.serving_revision_guard import (
    ServingRevisionGuardProjection,
    ServingRevisionGuardRepository,
    read_serving_revision_guard,
)

__all__ = [
    "EligiblePipelineRevision",
    "FaceEngine",
    "FakeFaceEngine",
    "InitialPendingRepository",
    "IneligiblePipelineRevisionError",
    "PipelineCode",
    "PipelineRevisionRepository",
    "read_photo_processing_projection",
    "read_serving_revision_guard",
    "ServingRevisionGuardProjection",
    "ServingRevisionGuardRepository",
    "UnsupportedPipelineCodeError",
]

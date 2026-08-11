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

__all__ = [
    "EligiblePipelineRevision",
    "FaceEngine",
    "FakeFaceEngine",
    "InitialPendingRepository",
    "IneligiblePipelineRevisionError",
    "PipelineCode",
    "PipelineRevisionRepository",
    "UnsupportedPipelineCodeError",
]

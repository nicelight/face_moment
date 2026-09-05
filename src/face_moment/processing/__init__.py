"""Processing capability seam used by the Foundation proof."""

from face_moment.processing.face_engine import FaceEngine, FakeFaceEngine
from face_moment.processing.initial_pending import InitialPendingRepository
from face_moment.processing.purge_cleanup import (
    ProcessingPurgeCleanup,
    ProcessingPurgeCleanupResult,
)
from face_moment.processing.revisions import (
    EligiblePipelineRevision,
    IneligiblePipelineRevisionError,
    PipelineCode,
    PipelineRevisionRepository,
    UnsupportedPipelineCodeError,
)
from face_moment.processing.searchable_projection import read_photo_processing_projection
from face_moment.processing.persistence import (
    CompatiblePhotoMatch,
    ExactCompatibleSearchRepository,
)
from face_moment.processing.realtime_search import (
    DetectionSearchObservation,
    PhotoMatchObservation,
    RealtimeSearchResult,
    RealtimeSearchService,
    opencv_phash64_v1,
    search_realtime_references,
)
from face_moment.processing.serving_revision_guard import (
    ServingRevisionGuardProjection,
    ServingRevisionGuardRepository,
    read_serving_revision_guard,
)

__all__ = [
    "EligiblePipelineRevision",
    "CompatiblePhotoMatch",
    "DetectionSearchObservation",
    "ExactCompatibleSearchRepository",
    "FaceEngine",
    "FakeFaceEngine",
    "InitialPendingRepository",
    "IneligiblePipelineRevisionError",
    "PipelineCode",
    "PipelineRevisionRepository",
    "ProcessingPurgeCleanup",
    "ProcessingPurgeCleanupResult",
    "PhotoMatchObservation",
    "RealtimeSearchResult",
    "RealtimeSearchService",
    "opencv_phash64_v1",
    "read_photo_processing_projection",
    "read_serving_revision_guard",
    "ServingRevisionGuardProjection",
    "ServingRevisionGuardRepository",
    "search_realtime_references",
    "UnsupportedPipelineCodeError",
]

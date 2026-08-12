"""Processing capability seam used by the Foundation proof."""

from face_moment.processing.face_engine import FaceEngine, FakeFaceEngine
from face_moment.processing.buffalo_adapter import (
    BuffaloEmbeddingDimensionMismatchError,
    BuffaloModelAssetMismatchError,
    BuffaloModelAssets,
    BuffaloPhotoAdapter,
    BuffaloPhotoFace,
    BuffaloRevisionMismatchError,
    InvalidBuffaloPhotoError,
)
from face_moment.processing.initial_pending import InitialPendingRepository
from face_moment.processing.revisions import (
    EligiblePipelineRevision,
    IneligiblePipelineRevisionError,
    PipelineCode,
    PipelineRevisionRepository,
    UnsupportedPipelineCodeError,
)
from face_moment.processing.sface_adapter import (
    EmbeddingDimensionMismatchError,
    InvalidSFacePhotoError,
    ModelAssetMismatchError,
    SFaceModelAssets,
    SFacePhotoAdapter,
    SFacePhotoFace,
    SFaceRevisionMismatchError,
)

__all__ = [
    "EligiblePipelineRevision",
    "EmbeddingDimensionMismatchError",
    "FaceEngine",
    "FakeFaceEngine",
    "BuffaloEmbeddingDimensionMismatchError",
    "BuffaloModelAssetMismatchError",
    "BuffaloModelAssets",
    "BuffaloPhotoAdapter",
    "BuffaloPhotoFace",
    "BuffaloRevisionMismatchError",
    "InitialPendingRepository",
    "InvalidBuffaloPhotoError",
    "IneligiblePipelineRevisionError",
    "InvalidSFacePhotoError",
    "ModelAssetMismatchError",
    "PipelineCode",
    "PipelineRevisionRepository",
    "SFaceModelAssets",
    "SFacePhotoAdapter",
    "SFacePhotoFace",
    "SFaceRevisionMismatchError",
    "UnsupportedPipelineCodeError",
]

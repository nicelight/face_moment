from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray
from face_moment.infrastructure.settings import Settings
from face_moment.processing.buffalo_adapter import BuffaloModelAssets, BuffaloPhotoAdapter
from face_moment.processing.revisions import EligiblePipelineRevision, PipelineCode
from face_moment.processing.sface_adapter import SFaceModelAssets, SFacePhotoAdapter
from face_moment.processing.terminal_publication import TerminalFace


class ModelAdmissionError(RuntimeError):
    """The committed serving revision cannot be bound by this process."""


class AdmittedModelAdapter(Protocol):
    @property
    def ready(self) -> bool: ...

    @property
    def pipeline_revision_id(self) -> object: ...

    def warmup(self) -> None: ...

    def process_for_terminal(
        self, photo: NDArray[np.uint8]
    ) -> tuple[TerminalFace, ...]: ...


def admit_selected_model(
    *,
    revision: EligiblePipelineRevision,
    settings: Settings,
) -> AdmittedModelAdapter:
    """Verify and warm exactly the direct adapter for the committed revision."""

    try:
        adapter: SFacePhotoAdapter | BuffaloPhotoAdapter
        if revision.pipeline_code is PipelineCode.OPENCV_SFACE:
            adapter = _admit_sface(revision=revision, settings=settings)
        elif revision.pipeline_code is PipelineCode.INSIGHTFACE_BUFFALO_M:
            adapter = _admit_buffalo(revision=revision, settings=settings)
        else:
            raise ModelAdmissionError(f"unsupported committed pipeline: {revision.pipeline_code}")
        adapter.warmup()
        if not adapter.ready:
            raise ModelAdmissionError("direct model warmup did not reach readiness")
        return cast(AdmittedModelAdapter, adapter)
    except ModelAdmissionError:
        raise
    except (OSError, ValueError) as error:
        raise ModelAdmissionError("committed model assets cannot be admitted") from error


def _admit_sface(
    *, revision: EligiblePipelineRevision, settings: Settings
) -> SFacePhotoAdapter:
    embedding_dimension = _required_int(
        settings.sface_embedding_dimension, "SFACE_EMBEDDING_DIMENSION"
    )
    if revision.embedding_dimension != embedding_dimension:
        raise ModelAdmissionError("committed SFace embedding dimension mismatches configuration")
    assets = SFaceModelAssets(
        detector_path=Path(_required(settings.sface_detector_path, "SFACE_DETECTOR_PATH")),
        detector_id=_required(settings.sface_detector_id, "SFACE_DETECTOR_ID"),
        detector_version=_required(
            settings.sface_detector_version, "SFACE_DETECTOR_VERSION"
        ),
        recognizer_path=Path(
            _required(settings.sface_recognizer_path, "SFACE_RECOGNIZER_PATH")
        ),
        recognizer_id=_required(settings.sface_recognizer_id, "SFACE_RECOGNIZER_ID"),
        recognizer_version=_required(
            settings.sface_recognizer_version, "SFACE_RECOGNIZER_VERSION"
        ),
        preprocessing_version=_required(
            settings.sface_preprocessing_version, "SFACE_PREPROCESSING_VERSION"
        ),
        alignment_version=_required(
            settings.sface_alignment_version, "SFACE_ALIGNMENT_VERSION"
        ),
        normalization_version=_required(
            settings.sface_normalization_version, "SFACE_NORMALIZATION_VERSION"
        ),
    )
    assets.verify_revision(revision)
    return SFacePhotoAdapter.from_configured_assets(revision=revision, assets=assets)


def _admit_buffalo(
    *, revision: EligiblePipelineRevision, settings: Settings
) -> BuffaloPhotoAdapter:
    assets = BuffaloModelAssets(
        detector_path=Path(
            _required(settings.buffalo_detector_path, "BUFFALO_DETECTOR_PATH")
        ),
        detector_id=_required(settings.buffalo_detector_id, "BUFFALO_DETECTOR_ID"),
        detector_version=_required(
            settings.buffalo_detector_version, "BUFFALO_DETECTOR_VERSION"
        ),
        recognizer_path=Path(
            _required(settings.buffalo_recognizer_path, "BUFFALO_RECOGNIZER_PATH")
        ),
        recognizer_id=_required(
            settings.buffalo_recognizer_id, "BUFFALO_RECOGNIZER_ID"
        ),
        recognizer_version=_required(
            settings.buffalo_recognizer_version, "BUFFALO_RECOGNIZER_VERSION"
        ),
        preprocessing_version=_required(
            settings.buffalo_preprocessing_version, "BUFFALO_PREPROCESSING_VERSION"
        ),
        alignment_version=_required(
            settings.buffalo_alignment_version, "BUFFALO_ALIGNMENT_VERSION"
        ),
        normalization_version=_required(
            settings.buffalo_normalization_version, "BUFFALO_NORMALIZATION_VERSION"
        ),
        embedding_dimension=_required_int(
            settings.buffalo_embedding_dimension, "BUFFALO_EMBEDDING_DIMENSION"
        ),
    )
    assets.verify_revision(revision)
    return BuffaloPhotoAdapter.from_configured_assets(revision=revision, assets=assets)


def _required(value: str | None, name: str) -> str:
    if value is None:
        raise ModelAdmissionError(f"required selected-model setting is missing: {name}")
    return value


def _required_int(value: int | None, name: str) -> int:
    if value is None:
        raise ModelAdmissionError(f"required selected-model setting is missing: {name}")
    return value

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from face_moment.processing.revisions import EligiblePipelineRevision, PipelineCode
from face_moment.processing.sface_adapter import (
    EmbeddingDimensionMismatchError,
    InvalidSFacePhotoError,
    ModelAssetMismatchError,
    SFaceModelAssets,
    SFacePhotoAdapter,
    SFaceRevisionMismatchError,
)


class _YuNetFixture:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls
        self.detections = np.array(
            [[10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 0.98]],
            dtype=np.float32,
        )

    def setInputSize(self, size: tuple[int, int]) -> None:
        assert size == (32, 32)
        self._calls.append("yunet.setInputSize")

    def detect(
        self, photo: NDArray[np.uint8]
    ) -> tuple[bool, NDArray[np.float32] | None]:
        assert photo.shape == (32, 32, 3)
        self._calls.append("yunet.detect")
        return True, self.detections


class _SFaceFixture:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def alignCrop(
        self, photo: NDArray[np.uint8], detection: NDArray[np.float32]
    ) -> NDArray[np.uint8]:
        assert photo.shape == (32, 32, 3)
        np.testing.assert_array_equal(
            detection,
            np.array(
                [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 0.98],
                dtype=np.float32,
            ),
        )
        self._calls.append("sface.alignCrop")
        return np.full((112, 112, 3), 17, dtype=np.uint8)

    def feature(self, aligned: NDArray[np.uint8]) -> NDArray[np.float32]:
        assert aligned.shape == (112, 112, 3)
        self._calls.append("sface.feature")
        return np.array([[3.0, 4.0, 0.0]], dtype=np.float32)


def _assets(tmp_path: Path) -> SFaceModelAssets:
    detector_path = tmp_path / "yunet.onnx"
    recognizer_path = tmp_path / "sface.onnx"
    detector_path.write_bytes(b"detector-model")
    recognizer_path.write_bytes(b"recognizer-model")
    return SFaceModelAssets(
        detector_path=detector_path,
        detector_id="yunet",
        detector_version="2024mar",
        recognizer_path=recognizer_path,
        recognizer_id="sface",
        recognizer_version="2021dec",
        preprocessing_version="opencv-bgr-v1",
        alignment_version="opencv-aligncrop-v1",
        normalization_version="l2-v1",
    )


def _revision(
    assets: SFaceModelAssets,
    *,
    pipeline_code: PipelineCode = PipelineCode.OPENCV_SFACE,
    embedding_dimension: int = 3,
) -> EligiblePipelineRevision:
    return EligiblePipelineRevision(
        id=uuid.uuid4(),
        pipeline_code=pipeline_code,
        detector_id=assets.detector_id,
        detector_version=assets.detector_version,
        recognizer_id=assets.recognizer_id,
        recognizer_version=assets.recognizer_version,
        weights_sha256=assets.weights_sha256(),
        preprocessing_version=assets.preprocessing_version,
        alignment_version=assets.alignment_version,
        normalization_version=assets.normalization_version,
        embedding_dimension=embedding_dimension,
        created_at=datetime.now(UTC),
        validated_at=datetime.now(UTC),
    )


def test_sface_adapter_runs_yunet_aligncrop_and_sface_for_a_synthetic_photo(
    tmp_path: Path,
) -> None:
    assets = _assets(tmp_path)
    revision = _revision(assets)
    calls: list[str] = []
    detector = _YuNetFixture(calls)
    adapter = SFacePhotoAdapter(
        revision=revision,
        assets=assets,
        detector=detector,
        recognizer=_SFaceFixture(calls),
    )

    assert adapter.ready is True
    adapter.warmup()
    faces = adapter.process_photo(np.zeros((32, 32, 3), dtype=np.uint8))

    assert calls == [
        "yunet.setInputSize",
        "yunet.detect",
        "sface.alignCrop",
        "sface.feature",
    ]
    assert len(faces) == 1
    assert faces[0].pipeline_revision_id == revision.id
    assert np.shares_memory(faces[0].native_detection, detector.detections)
    np.testing.assert_allclose(faces[0].embedding, np.array([0.6, 0.8, 0.0]))
    assert np.linalg.norm(faces[0].embedding) == pytest.approx(1.0)


def test_sface_adapter_rejects_dimension_and_asset_identity_mismatch(
    tmp_path: Path,
) -> None:
    assets = _assets(tmp_path)
    calls: list[str] = []

    with pytest.raises(EmbeddingDimensionMismatchError):
        SFacePhotoAdapter(
            revision=_revision(assets, embedding_dimension=4),
            assets=assets,
            detector=_YuNetFixture(calls),
            recognizer=_SFaceFixture(calls),
        ).process_photo(np.zeros((32, 32, 3), dtype=np.uint8))

    mismatched_assets = SFaceModelAssets(
        detector_path=assets.detector_path,
        detector_id="wrong-yunet",
        detector_version=assets.detector_version,
        recognizer_path=assets.recognizer_path,
        recognizer_id=assets.recognizer_id,
        recognizer_version=assets.recognizer_version,
        preprocessing_version=assets.preprocessing_version,
        alignment_version=assets.alignment_version,
        normalization_version=assets.normalization_version,
    )
    with pytest.raises(ModelAssetMismatchError):
        SFacePhotoAdapter(
            revision=_revision(assets),
            assets=mismatched_assets,
            detector=_YuNetFixture(calls),
            recognizer=_SFaceFixture(calls),
        )
    assert calls == [
        "yunet.setInputSize",
        "yunet.detect",
        "sface.alignCrop",
        "sface.feature",
    ]


def test_sface_adapter_rejects_buffalo_revision_before_native_calls(
    tmp_path: Path,
) -> None:
    assets = _assets(tmp_path)
    calls: list[str] = []

    with pytest.raises(SFaceRevisionMismatchError):
        SFacePhotoAdapter(
            revision=_revision(
                assets,
                pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
            ),
            assets=assets,
            detector=_YuNetFixture(calls),
            recognizer=_SFaceFixture(calls),
        )

    assert calls == []


def test_sface_adapter_rejects_a_buffalo_derived_value_as_photo_input(
    tmp_path: Path,
) -> None:
    class _BuffaloDerivedValue:
        pass

    assets = _assets(tmp_path)
    calls: list[str] = []
    adapter = SFacePhotoAdapter(
        revision=_revision(assets),
        assets=assets,
        detector=_YuNetFixture(calls),
        recognizer=_SFaceFixture(calls),
    )

    with pytest.raises(InvalidSFacePhotoError):
        adapter.process_photo(_BuffaloDerivedValue())  # type: ignore[arg-type]

    assert calls == []

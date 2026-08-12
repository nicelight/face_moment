from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from insightface.app.common import Face
from numpy.typing import NDArray

from face_moment.processing.buffalo_adapter import (
    BuffaloEmbeddingDimensionMismatchError,
    BuffaloModelAssetMismatchError,
    BuffaloModelAssets,
    BuffaloPhotoAdapter,
    BuffaloRevisionMismatchError,
    InvalidBuffaloPhotoError,
)
from face_moment.processing.revisions import EligiblePipelineRevision, PipelineCode


class _ScrfdFixture:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls
        self.detections = np.array([[10, 11, 22, 24, 0.98]], dtype=np.float32)
        self.landmarks = np.array(
            [[[12, 13], [20, 13], [16, 17], [13, 21], [19, 21]]],
            dtype=np.float32,
        )

    def detect(
        self,
        photo: NDArray[np.uint8],
        max_num: int = 0,
        metric: str = "default",
    ) -> tuple[NDArray[np.float32], NDArray[np.float32] | None]:
        assert photo.shape == (32, 32, 3)
        assert max_num == 0
        assert metric == "default"
        self._calls.append("scrfd.detect")
        return self.detections, self.landmarks


class _BuffaloRecognizerFixture:
    def __init__(
        self,
        calls: list[str],
        embedding: NDArray[np.float32] | None = None,
    ) -> None:
        self._calls = calls
        self._embedding = (
            np.array([3.0, 4.0, 0.0], dtype=np.float32)
            if embedding is None
            else embedding
        )

    def get(self, photo: NDArray[np.uint8], face: Face) -> NDArray[np.float32]:
        assert photo.shape == (32, 32, 3)
        np.testing.assert_array_equal(
            face.bbox,
            np.array([10, 11, 22, 24], dtype=np.float32),
        )
        np.testing.assert_array_equal(
            face.kps,
            np.array(
                [[12, 13], [20, 13], [16, 17], [13, 21], [19, 21]],
                dtype=np.float32,
            ),
        )
        self._calls.append("buffalo.native_alignment")
        face.embedding = self._embedding
        self._calls.append("buffalo.normed_embedding")
        return face.embedding


def _assets(tmp_path: Path) -> BuffaloModelAssets:
    detector_path = tmp_path / "scrfd.onnx"
    recognizer_path = tmp_path / "w600k_r50.onnx"
    detector_path.write_bytes(b"scrfd-model")
    recognizer_path.write_bytes(b"buffalo-recognizer-model")
    return BuffaloModelAssets(
        detector_path=detector_path,
        detector_id="scrfd",
        detector_version="10g-bnkps",
        recognizer_path=recognizer_path,
        recognizer_id="w600k_r50",
        recognizer_version="buffalo-m",
        preprocessing_version="insightface-bgr-v1",
        alignment_version="insightface-norm-crop-v1",
        normalization_version="insightface-normed-embedding-v1",
        embedding_dimension=3,
    )


def _revision(
    assets: BuffaloModelAssets,
    *,
    pipeline_code: PipelineCode = PipelineCode.INSIGHTFACE_BUFFALO_M,
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


def test_buffalo_adapter_runs_scrfd_native_alignment_and_normed_embedding(
    tmp_path: Path,
) -> None:
    assets = _assets(tmp_path)
    revision = _revision(assets)
    calls: list[str] = []
    detector = _ScrfdFixture(calls)
    adapter = BuffaloPhotoAdapter(
        revision=revision,
        assets=assets,
        detector=detector,
        recognizer=_BuffaloRecognizerFixture(calls),
    )

    assert adapter.ready is True
    adapter.warmup()
    faces = adapter.process_photo(np.zeros((32, 32, 3), dtype=np.uint8))

    assert calls == [
        "scrfd.detect",
        "buffalo.native_alignment",
        "buffalo.normed_embedding",
    ]
    assert len(faces) == 1
    assert faces[0].pipeline_revision_id == revision.id
    assert np.shares_memory(faces[0].native_face.kps, detector.landmarks)
    np.testing.assert_allclose(faces[0].embedding, np.array([0.6, 0.8, 0.0]))
    assert np.linalg.norm(faces[0].embedding) == pytest.approx(1.0)


def test_buffalo_adapter_rejects_dimension_and_asset_identity_mismatch(
    tmp_path: Path,
) -> None:
    assets = _assets(tmp_path)
    calls: list[str] = []

    with pytest.raises(BuffaloEmbeddingDimensionMismatchError):
        BuffaloPhotoAdapter(
            revision=_revision(assets, embedding_dimension=4),
            assets=assets,
            detector=_ScrfdFixture(calls),
            recognizer=_BuffaloRecognizerFixture(calls),
        )

    with pytest.raises(BuffaloEmbeddingDimensionMismatchError):
        BuffaloPhotoAdapter(
            revision=_revision(assets),
            assets=assets,
            detector=_ScrfdFixture(calls),
            recognizer=_BuffaloRecognizerFixture(
                calls,
                np.array([3.0, 4.0, 0.0, 0.0], dtype=np.float32),
            ),
        ).process_photo(np.zeros((32, 32, 3), dtype=np.uint8))

    mismatched_assets = BuffaloModelAssets(
        detector_path=assets.detector_path,
        detector_id="wrong-scrfd",
        detector_version=assets.detector_version,
        recognizer_path=assets.recognizer_path,
        recognizer_id=assets.recognizer_id,
        recognizer_version=assets.recognizer_version,
        preprocessing_version=assets.preprocessing_version,
        alignment_version=assets.alignment_version,
        normalization_version=assets.normalization_version,
        embedding_dimension=assets.embedding_dimension,
    )
    with pytest.raises(BuffaloModelAssetMismatchError):
        BuffaloPhotoAdapter(
            revision=_revision(assets),
            assets=mismatched_assets,
            detector=_ScrfdFixture(calls),
            recognizer=_BuffaloRecognizerFixture(calls),
        )
    assert calls == [
        "scrfd.detect",
        "buffalo.native_alignment",
        "buffalo.normed_embedding",
    ]


def test_buffalo_adapter_rejects_sface_revision_before_native_calls(
    tmp_path: Path,
) -> None:
    assets = _assets(tmp_path)
    calls: list[str] = []

    with pytest.raises(BuffaloRevisionMismatchError):
        BuffaloPhotoAdapter(
            revision=_revision(assets, pipeline_code=PipelineCode.OPENCV_SFACE),
            assets=assets,
            detector=_ScrfdFixture(calls),
            recognizer=_BuffaloRecognizerFixture(calls),
        )

    assert calls == []


def test_buffalo_adapter_rejects_an_sface_derived_value_as_photo_input(
    tmp_path: Path,
) -> None:
    class _SFaceDerivedValue:
        pass

    assets = _assets(tmp_path)
    calls: list[str] = []
    adapter = BuffaloPhotoAdapter(
        revision=_revision(assets),
        assets=assets,
        detector=_ScrfdFixture(calls),
        recognizer=_BuffaloRecognizerFixture(calls),
    )

    with pytest.raises(InvalidBuffaloPhotoError):
        adapter.process_photo(_SFaceDerivedValue())  # type: ignore[arg-type]

    assert calls == []

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from insightface.app.common import Face
from numpy.typing import NDArray

from face_moment.processing.buffalo_adapter import (
    BuffaloModelAssets,
    BuffaloPhotoAdapter,
)
from face_moment.processing.reference_query import (
    PreparedReferenceQuery,
    ReferenceOccurrence,
    ReferenceQualityObservation,
    select_reference_queries,
)
from face_moment.processing.revisions import EligiblePipelineRevision, PipelineCode
from face_moment.processing.sface_adapter import SFaceModelAssets, SFacePhotoAdapter


class _SelectionEngine:
    def __init__(self, scores: Mapping[int, float]) -> None:
        self._scores = scores
        self.inspected: list[int] = []
        self.prepared: list[int] = []

    def inspect_reference_crop(
        self,
        crop: NDArray[np.uint8],
        quality_settings: Mapping[str, object],
    ) -> ReferenceQualityObservation:
        del quality_settings
        index = int(crop[0, 0, 0])
        self.inspected.append(index)
        score = self._scores[index]
        return ReferenceQualityObservation(
            reference_quality_score=score,
            native_face_count=1 if score > 0 else 0,
            gate_observations=(
                ("native_detection_confidence", score),
            ),
        )

    def prepare_reference_query(
        self, crop: NDArray[np.uint8]
    ) -> PreparedReferenceQuery | None:
        index = int(crop[0, 0, 0])
        self.prepared.append(index)
        if self._scores[index] <= 0:
            return None
        return PreparedReferenceQuery(
            pipeline_revision_id=uuid.UUID(int=1),
            embedding=np.array([float(index), 1.0], dtype=np.float32),
        )


def _occurrences(count: int) -> tuple[ReferenceOccurrence, ...]:
    return tuple(
        ReferenceOccurrence(
            occurrence_index=index,
            crop=np.full((2, 2, 3), index, dtype=np.uint8),
        )
        for index in range(count)
    )


def test_selection_inspects_all_orders_ties_keeps_repeated_occurrences_and_caps_at_five() -> None:
    engine = _SelectionEngine(
        {0: 0.91, 1: 0.95, 2: 0.95, 3: 0.80, 4: 0.79, 5: 0.78, 6: 0.77}
    )

    selected = select_reference_queries(
        engine=engine,
        occurrences=_occurrences(7),
        min_query_face_quality=0.75,
        quality_settings={"fixture": "native"},
    )

    assert engine.inspected == list(range(7))
    assert [item.occurrence_index for item in selected] == [1, 2, 0, 3, 4]
    assert [item.rank for item in selected] == [1, 2, 3, 4, 5]
    assert all(item.quality_gate_passed for item in selected)
    assert all(item.query is not None for item in selected)
    assert engine.prepared == [1, 2, 0, 3, 4]


def test_selection_returns_bounded_rejected_observation_for_low_quality_without_preparing_it() -> None:
    engine = _SelectionEngine({0: 0.40, 1: 0.90})

    selected = select_reference_queries(
        engine=engine,
        occurrences=_occurrences(2),
        min_query_face_quality=0.75,
        quality_settings={},
    )

    assert [item.occurrence_index for item in selected] == [1, 0]
    rejected = selected[1]
    assert rejected.quality_gate_passed is False
    assert rejected.query is None
    assert rejected.rejection_reason == "low_quality"
    assert engine.prepared == [1]


class _SFaceDetector:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def setInputSize(self, size: tuple[int, int]) -> None:
        assert size == (32, 32)
        self.calls.append("yunet.setInputSize")

    def detect(
        self, photo: NDArray[np.uint8]
    ) -> tuple[bool, NDArray[np.float32] | None]:
        assert photo.shape == (32, 32, 3)
        self.calls.append("yunet.detect")
        return True, np.array(
            [[1, 2, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 0.93]],
            dtype=np.float32,
        )


class _SFaceRecognizer:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def alignCrop(
        self, photo: NDArray[np.uint8], detection: NDArray[np.float32]
    ) -> NDArray[np.uint8]:
        del detection
        assert photo.shape == (32, 32, 3)
        self.calls.append("sface.alignCrop")
        return np.zeros((112, 112, 3), dtype=np.uint8)

    def feature(self, aligned: NDArray[np.uint8]) -> NDArray[np.float32]:
        assert aligned.shape == (112, 112, 3)
        self.calls.append("sface.feature")
        return np.array([[3.0, 4.0]], dtype=np.float32)


def _sface_assets(tmp_path: Path) -> SFaceModelAssets:
    detector_path = tmp_path / "yunet.onnx"
    recognizer_path = tmp_path / "sface.onnx"
    detector_path.write_bytes(b"yunet")
    recognizer_path.write_bytes(b"sface")
    return SFaceModelAssets(
        detector_path=detector_path,
        detector_id="yunet",
        detector_version="v1",
        recognizer_path=recognizer_path,
        recognizer_id="sface",
        recognizer_version="v1",
        preprocessing_version="bgr-v1",
        alignment_version="aligncrop-v1",
        normalization_version="l2-v1",
    )


def test_sface_reference_operations_keep_yunet_aligncrop_and_revision_native(
    tmp_path: Path,
) -> None:
    assets = _sface_assets(tmp_path)
    revision = EligiblePipelineRevision(
        id=uuid.uuid4(),
        pipeline_code=PipelineCode.OPENCV_SFACE,
        detector_id=assets.detector_id,
        detector_version=assets.detector_version,
        recognizer_id=assets.recognizer_id,
        recognizer_version=assets.recognizer_version,
        weights_sha256=assets.weights_sha256(),
        preprocessing_version=assets.preprocessing_version,
        alignment_version=assets.alignment_version,
        normalization_version=assets.normalization_version,
        embedding_dimension=2,
        created_at=datetime.now(UTC),
        validated_at=datetime.now(UTC),
    )
    calls: list[str] = []
    adapter = SFacePhotoAdapter(
        revision=revision,
        assets=assets,
        detector=_SFaceDetector(calls),
        recognizer=_SFaceRecognizer(calls),
    )

    quality = adapter.inspect_reference_crop(
        np.zeros((32, 32, 3), dtype=np.uint8), {}
    )
    query = adapter.prepare_reference_query(
        np.zeros((32, 32, 3), dtype=np.uint8)
    )

    assert quality.reference_quality_score == pytest.approx(0.93)
    assert quality.native_face_count == 1
    assert query is not None
    assert query.pipeline_revision_id == revision.id
    np.testing.assert_allclose(query.embedding, np.array([0.6, 0.8]))
    assert calls == [
        "yunet.setInputSize",
        "yunet.detect",
        "sface.alignCrop",
        "sface.feature",
        "yunet.setInputSize",
        "yunet.detect",
        "sface.alignCrop",
        "sface.feature",
    ]


class _BuffaloDetector:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def detect(
        self,
        photo: NDArray[np.uint8],
        max_num: int = 0,
        metric: str = "default",
    ) -> tuple[NDArray[np.float32], NDArray[np.float32] | None]:
        assert photo.shape == (32, 32, 3)
        assert max_num == 0
        assert metric == "default"
        self.calls.append("scrfd.detect")
        return (
            np.array([[2, 3, 20, 21, 0.88]], dtype=np.float32),
            np.array(
                [[[4, 5], [18, 5], [11, 12], [6, 18], [16, 18]]],
                dtype=np.float32,
            ),
        )


class _BuffaloRecognizer:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def get(self, photo: NDArray[np.uint8], face: Face) -> NDArray[np.float32]:
        assert photo.shape == (32, 32, 3)
        self.calls.append("buffalo.native_alignment")
        embedding = np.array([3.0, 4.0], dtype=np.float32)
        face.embedding = embedding
        self.calls.append("buffalo.normed_embedding")
        return embedding


def test_buffalo_reference_operations_keep_scrfd_native_alignment_and_revision(
    tmp_path: Path,
) -> None:
    detector_path = tmp_path / "scrfd.onnx"
    recognizer_path = tmp_path / "buffalo.onnx"
    detector_path.write_bytes(b"scrfd")
    recognizer_path.write_bytes(b"buffalo")
    assets = BuffaloModelAssets(
        detector_path=detector_path,
        detector_id="scrfd",
        detector_version="v1",
        recognizer_path=recognizer_path,
        recognizer_id="buffalo",
        recognizer_version="v1",
        preprocessing_version="bgr-v1",
        alignment_version="native-v1",
        normalization_version="normed-v1",
        embedding_dimension=2,
    )
    now = datetime.now(UTC)
    revision = EligiblePipelineRevision(
        id=uuid.uuid4(),
        pipeline_code=PipelineCode.INSIGHTFACE_BUFFALO_M,
        detector_id=assets.detector_id,
        detector_version=assets.detector_version,
        recognizer_id=assets.recognizer_id,
        recognizer_version=assets.recognizer_version,
        weights_sha256=assets.weights_sha256(),
        preprocessing_version=assets.preprocessing_version,
        alignment_version=assets.alignment_version,
        normalization_version=assets.normalization_version,
        embedding_dimension=2,
        created_at=now,
        validated_at=now,
    )
    calls: list[str] = []
    adapter = BuffaloPhotoAdapter(
        revision=revision,
        assets=assets,
        detector=_BuffaloDetector(calls),
        recognizer=_BuffaloRecognizer(calls),
    )

    quality = adapter.inspect_reference_crop(
        np.zeros((32, 32, 3), dtype=np.uint8), {}
    )
    query = adapter.prepare_reference_query(
        np.zeros((32, 32, 3), dtype=np.uint8)
    )

    assert quality.reference_quality_score == pytest.approx(0.88)
    assert query is not None
    assert query.pipeline_revision_id == revision.id
    np.testing.assert_allclose(query.embedding, np.array([0.6, 0.8]))
    assert calls == [
        "scrfd.detect",
        "buffalo.native_alignment",
        "buffalo.normed_embedding",
        "scrfd.detect",
        "buffalo.native_alignment",
        "buffalo.normed_embedding",
    ]

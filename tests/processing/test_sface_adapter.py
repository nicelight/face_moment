from __future__ import annotations

import uuid
from datetime import UTC, datetime
from dataclasses import replace
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


class _RecordingYuNet:
    def __init__(self, detections: list[NDArray[np.float32] | None]) -> None:
        self.detections = detections
        self.sizes: list[tuple[int, int]] = []

    def setInputSize(self, size: tuple[int, int]) -> None:
        self.sizes.append(size)

    def detect(self, photo: NDArray[np.uint8]) -> tuple[bool, NDArray[np.float32] | None]:
        assert self.sizes[-1] == (photo.shape[1], photo.shape[0])
        return True, self.detections[(len(self.sizes) - 1) % len(self.detections)]


class _RecordingSFace:
    def __init__(self, original: NDArray[np.uint8]) -> None:
        self.original = original
        self.detections: list[NDArray[np.float32]] = []

    def alignCrop(self, photo: NDArray[np.uint8], detection: NDArray[np.float32]) -> NDArray[np.uint8]:
        assert photo is self.original
        self.detections.append(detection.copy())
        return np.full((112, 112, 3), 17, dtype=np.uint8)

    def feature(self, aligned: NDArray[np.uint8]) -> NDArray[np.float32]:
        assert aligned.shape == (112, 112, 3)
        return np.array([[3, 4, 0]], dtype=np.float32)


def test_versioned_photo_detection_maps_actual_ratios_and_aligns_original(tmp_path: Path) -> None:
    assets = replace(_assets(tmp_path), preprocessing_version="opencv-photo-640-v2")
    original = np.zeros((1001, 1503, 3), dtype=np.uint8)
    native = np.array([[12, 20, 30, 50, 18, 33, 35, 33, 26, 42, 20, 55, 33, 55, .98]], dtype=np.float32)
    detector = _RecordingYuNet([native])
    recognizer = _RecordingSFace(original)
    adapter = SFacePhotoAdapter(revision=_revision(assets), assets=assets, detector=detector, recognizer=recognizer)
    faces = adapter.process_for_terminal(original)

    assert detector.sizes == [(640, 426)]
    expected = native[0].copy()
    expected[[0, 2, 4, 6, 8, 10, 12]] *= 1503 / 640
    expected[[1, 3, 5, 7, 9, 11, 13]] *= 1001 / 426
    np.testing.assert_allclose(recognizer.detections[0], expected)
    assert len(faces) == 1
    np.testing.assert_allclose([faces[0].bbox_x, faces[0].bbox_y, faces[0].bbox_w, faces[0].bbox_h], expected[:4])
    np.testing.assert_allclose(faces[0].landmarks_json, expected[4:14].reshape(5, 2))
    np.testing.assert_allclose(faces[0].embedding, [.6, .8, 0])
    np.testing.assert_array_equal(native[0, :4], [12, 20, 30, 50])


@pytest.mark.parametrize("shape,sizes", [
    ((200, 300), [(300, 200)]),
    ((640, 640), [(640, 640)]),
    ((600, 900), [(640, 427), (900, 600)]),
    ((1401, 2003), [(640, 448), (1280, 895)]),
])
def test_multiscale_does_not_upscale_or_repeat_dimensions(tmp_path: Path, shape: tuple[int, int], sizes: list[tuple[int, int]]) -> None:
    assets = replace(_assets(tmp_path), preprocessing_version="opencv-photo-640-1280-v2")
    original = np.zeros((*shape, 3), dtype=np.uint8)
    detector = _RecordingYuNet([None])
    adapter = SFacePhotoAdapter(revision=_revision(assets), assets=assets, detector=detector, recognizer=_RecordingSFace(original))
    assert adapter.process_photo(original) == ()
    assert detector.sizes == sizes


def test_multiscale_merges_duplicate_but_preserves_overlapping_neighbour(tmp_path: Path) -> None:
    assets = replace(_assets(tmp_path), preprocessing_version="opencv-photo-640-1280-v2")
    original = np.zeros((1280, 1280, 3), dtype=np.uint8)
    face = np.array([100, 100, 100, 120, 120, 130, 180, 130, 150, 160, 130, 195, 170, 195, .95], dtype=np.float32)
    neighbour = face.copy()
    neighbour[[0, 4, 6, 8, 10, 12]] += 30
    neighbour[14] = .98
    coarse = np.stack([face, neighbour]); coarse[:, :14] /= 2
    fine = face.copy(); fine[14] = .99
    detector = _RecordingYuNet([coarse, fine[None]])
    recognizer = _RecordingSFace(original)
    adapter = SFacePhotoAdapter(revision=_revision(assets), assets=assets, detector=detector, recognizer=recognizer)
    faces = adapter.process_photo(original)
    assert detector.sizes == [(640, 640), (1280, 1280)]
    assert len(faces) == len(recognizer.detections) == 2
    np.testing.assert_array_equal(faces[0].native_detection, fine)
    np.testing.assert_array_equal(faces[1].native_detection, neighbour)


@pytest.mark.parametrize("version", ["opencv-bgr-v1", "opencv-photo-640-v2", "opencv-photo-640-1280-v2"])
def test_query_methods_always_use_single_native_pass(tmp_path: Path, version: str) -> None:
    assets = replace(_assets(tmp_path), preprocessing_version=version)
    original = np.zeros((1001, 1503, 3), dtype=np.uint8)
    row = np.array([[10, 10, 20, 20, 12, 14, 26, 14, 20, 20, 14, 26, 25, 26, .98]], dtype=np.float32)
    detector = _RecordingYuNet([row])
    adapter = SFacePhotoAdapter(revision=_revision(assets), assets=assets, detector=detector, recognizer=_RecordingSFace(original))
    assert adapter.inspect_reference_crop(original, {}).native_face_count == 1
    assert adapter.prepare_reference_query(original) is not None
    assert detector.sizes == [(1503, 1001), (1503, 1001)]
    if version == "opencv-bgr-v1":
        adapter.process_photo(original)
        assert detector.sizes[-1] == (1503, 1001)


def test_new_photo_clips_only_terminal_bbox_and_discards_empty_intersection(tmp_path: Path) -> None:
    assets = replace(_assets(tmp_path), preprocessing_version="opencv-photo-640-v2")
    original = np.zeros((80, 80, 3), dtype=np.uint8)
    row = np.array([-10, -15, 100, 100, -2, 4, 60, 4, 30, 30, 0, 70, 60, 70, .98], dtype=np.float32)
    outside = row.copy(); outside[0] = 90
    detector = _RecordingYuNet([np.stack([row, outside])])
    recognizer = _RecordingSFace(original)
    adapter = SFacePhotoAdapter(revision=_revision(assets), assets=assets, detector=detector, recognizer=recognizer)
    faces = adapter.process_for_terminal(original)
    assert len(faces) == len(recognizer.detections) == 1
    np.testing.assert_array_equal(recognizer.detections[0], row)
    assert (faces[0].bbox_x, faces[0].bbox_y, faces[0].bbox_w, faces[0].bbox_h) == (0, 0, 80, 80)
    np.testing.assert_array_equal(faces[0].landmarks_json, row[4:14].reshape(5, 2))


def test_photo_has_no_eight_face_cap_or_seven_percent_filter(tmp_path: Path) -> None:
    assets = replace(_assets(tmp_path), preprocessing_version="opencv-photo-640-v2")
    original = np.zeros((640, 640, 3), dtype=np.uint8)
    row = np.array([0, 10, 20, 20, 3, 14, 17, 14, 10, 20, 5, 26, 15, 26, .98], dtype=np.float32)
    detections = []
    for index in range(9):
        face = row.copy(); face[[0, 4, 6, 8, 10, 12]] += 50 * index
        detections.append(face)
    detector = _RecordingYuNet([np.stack(detections)])
    adapter = SFacePhotoAdapter(revision=_revision(assets), assets=assets, detector=detector, recognizer=_RecordingSFace(original))
    faces = adapter.process_for_terminal(original)
    assert len(faces) == 9
    assert [face.face_index for face in faces] == list(range(9))


def test_new_photo_rejects_nonfinite_detection_and_unknown_new_version(tmp_path: Path) -> None:
    assets = replace(_assets(tmp_path), preprocessing_version="opencv-photo-640-v2")
    original = np.zeros((32, 32, 3), dtype=np.uint8)
    detector = _RecordingYuNet([np.full((1, 15), np.nan, dtype=np.float32)])
    adapter = SFacePhotoAdapter(revision=_revision(assets), assets=assets, detector=detector, recognizer=_RecordingSFace(original))
    with pytest.raises(ValueError, match="finite"):
        adapter.process_photo(original)
    unknown = replace(assets, preprocessing_version="opencv-photo-unknown")
    with pytest.raises(ValueError, match="unsupported"):
        SFacePhotoAdapter(revision=_revision(unknown), assets=unknown, detector=detector, recognizer=_RecordingSFace(original))

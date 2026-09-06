from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from insightface.app.common import Face
from insightface.model_zoo import get_model as insightface_get_model
from numpy.typing import NDArray

import face_moment.processing.buffalo_adapter as buffalo_adapter_module
from face_moment.processing.buffalo_adapter import (
    BuffaloAdapterError,
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
        assert photo.ndim == 3
        assert photo.shape[2] == 3
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
        assert photo.ndim == 3
        assert photo.shape[2] == 3
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


def test_buffalo_native_dynamic_model_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_root = Path("models/insightface_buffalo_m")
    detector_path = model_root / "scrfd.onnx"
    recognizer_path = model_root / "w600k_r50.onnx"
    if not detector_path.is_file() or not recognizer_path.is_file():
        pytest.fail("required local Buffalo ONNX assets are absent")
    assets = BuffaloModelAssets(
        detector_path=detector_path,
        detector_id="scrfd",
        detector_version="10g-bnkps",
        recognizer_path=recognizer_path,
        recognizer_id="w600k_r50",
        recognizer_version="buffalo-m",
        preprocessing_version="insightface-bgr-v1",
        alignment_version="insightface-norm-crop-v1",
        normalization_version="insightface-normed-embedding-v1",
        embedding_dimension=512,
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
        embedding_dimension=assets.embedding_dimension,
        created_at=now,
        validated_at=now,
    )
    calls: list[str] = []
    recognizer_embedding: NDArray[np.float32] | None = None

    class _DetectorProxy:
        taskname = "detection"

        def __init__(self, native: object) -> None:
            self._native = native

        @property
        def input_size(self) -> tuple[int, int] | None:
            return getattr(self._native, "input_size", None)

        def prepare(self, *, ctx_id: int, input_size: tuple[int, int]) -> None:
            calls.append(f"detector.prepare:{ctx_id}:{input_size}")
            self._native.prepare(ctx_id=ctx_id, input_size=input_size)  # type: ignore[attr-defined]

        def detect(
            self,
            photo: NDArray[np.uint8],
            max_num: int = 0,
            metric: str = "default",
        ) -> tuple[NDArray[np.float32], NDArray[np.float32] | None]:
            calls.append(f"detector.detect:{photo.shape}")
            return self._native.detect(photo, max_num=max_num, metric=metric)  # type: ignore[attr-defined,return-value]

    class _RecognizerProxy:
        taskname = "recognition"

        def __init__(self, native: object) -> None:
            self._native = native

        def get(self, photo: NDArray[np.uint8], face: Face) -> NDArray[np.float32]:
            nonlocal recognizer_embedding
            calls.append(f"recognizer.get:{photo.shape}")
            result = self._native.get(photo, face)  # type: ignore[attr-defined]
            recognizer_embedding = np.asarray(face.normed_embedding, dtype=np.float32)
            return np.asarray(result, dtype=np.float32)

    def load(path: str, *, download: bool) -> object:
        native = insightface_get_model(path, download=download)
        if path.endswith("scrfd.onnx"):
            return _DetectorProxy(native)
        return _RecognizerProxy(native)

    monkeypatch.setattr(buffalo_adapter_module, "get_model", load)
    adapter = BuffaloPhotoAdapter.from_configured_assets(
        revision=revision, assets=assets
    )

    assert adapter.ready is False
    assert tuple(adapter._detector.input_size) == (640, 640)  # type: ignore[attr-defined]
    adapter.warmup()
    assert adapter.ready is True
    assert calls[:3] == [
        "detector.prepare:-1:(640, 640)",
        "detector.detect:(320, 320, 3)",
        "recognizer.get:(320, 320, 3)",
    ]
    assert recognizer_embedding is not None
    assert recognizer_embedding.shape == (512,)
    assert np.isfinite(recognizer_embedding).all()
    assert np.linalg.norm(recognizer_embedding) == pytest.approx(1.0, abs=1e-3)
    assert revision.weights_sha256 == assets.weights_sha256()

    assert adapter.process_photo(np.zeros((320, 320, 3), dtype=np.uint8)) == ()
    assert calls[-1] == "detector.detect:(320, 320, 3)"


def test_buffalo_configured_load_and_prepare_failures_are_wrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = _assets(tmp_path)
    revision = _revision(assets)

    def load_failure(_path: str, *, download: bool) -> object:
        del download
        raise RuntimeError("native model load failure")

    monkeypatch.setattr(buffalo_adapter_module, "get_model", load_failure)
    with pytest.raises(BuffaloAdapterError) as load_error:
        BuffaloPhotoAdapter.from_configured_assets(
            revision=revision, assets=assets
        )
    assert isinstance(load_error.value.__cause__, RuntimeError)

    class _Detector:
        taskname = "detection"

        def prepare(self, *, ctx_id: int, input_size: tuple[int, int]) -> None:
            del ctx_id, input_size
            raise RuntimeError("native detector prepare failure")

    class _Recognizer:
        taskname = "recognition"

    def prepare_failure(path: str, *, download: bool) -> object:
        del download
        return _Detector() if path == str(assets.detector_path) else _Recognizer()

    monkeypatch.setattr(buffalo_adapter_module, "get_model", prepare_failure)
    with pytest.raises(BuffaloAdapterError) as prepare_error:
        BuffaloPhotoAdapter.from_configured_assets(
            revision=revision, assets=assets
        )
    assert isinstance(prepare_error.value.__cause__, RuntimeError)


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

    assert adapter.ready is False
    adapter.warmup()
    assert adapter.ready is True
    faces = adapter.process_photo(np.zeros((32, 32, 3), dtype=np.uint8))

    assert calls == [
        "scrfd.detect",
        "buffalo.native_alignment",
        "buffalo.normed_embedding",
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


def test_buffalo_warmup_runs_recognizer_when_detector_is_empty(
    tmp_path: Path,
) -> None:
    assets = _assets(tmp_path)
    calls: list[str] = []
    detector = _ScrfdFixture(calls)
    detector.detections = np.empty((0, 5), dtype=np.float32)
    detector.landmarks = np.empty((0, 5, 2), dtype=np.float32)
    adapter = BuffaloPhotoAdapter(
        revision=_revision(assets),
        assets=assets,
        detector=detector,
        recognizer=_BuffaloRecognizerFixture(calls),
    )

    adapter.warmup()

    assert adapter.ready is True
    assert calls == [
        "scrfd.detect",
        "buffalo.native_alignment",
        "buffalo.normed_embedding",
    ]


@pytest.mark.parametrize("failure", ["detector", "recognizer"])
def test_buffalo_native_warmup_failure_keeps_readiness_closed(
    failure: str, tmp_path: Path
) -> None:
    assets = _assets(tmp_path)
    calls: list[str] = []

    class _FailingDetector(_ScrfdFixture):
        def detect(
            self,
            photo: NDArray[np.uint8],
            max_num: int = 0,
            metric: str = "default",
        ) -> tuple[NDArray[np.float32], NDArray[np.float32] | None]:
            if failure == "detector":
                raise RuntimeError("native detector failure")
            return super().detect(photo, max_num, metric)

    class _FailingRecognizer(_BuffaloRecognizerFixture):
        def get(self, photo: NDArray[np.uint8], face: Face) -> NDArray[np.float32]:
            if failure == "recognizer":
                raise RuntimeError("native recognizer failure")
            return super().get(photo, face)

    adapter = BuffaloPhotoAdapter(
        revision=_revision(assets),
        assets=assets,
        detector=_FailingDetector(calls),
        recognizer=_FailingRecognizer(calls),
    )

    with pytest.raises(BuffaloAdapterError) as error:
        adapter.warmup()

    assert isinstance(error.value.__cause__, RuntimeError)
    assert adapter.ready is False


def test_buffalo_failed_repeated_warmup_closes_previous_readiness(
    tmp_path: Path,
) -> None:
    assets = _assets(tmp_path)
    calls: list[str] = []

    class _FlakyDetector(_ScrfdFixture):
        failed = False

        def detect(
            self,
            photo: NDArray[np.uint8],
            max_num: int = 0,
            metric: str = "default",
        ) -> tuple[NDArray[np.float32], NDArray[np.float32] | None]:
            if self.failed:
                raise RuntimeError("repeated native detector failure")
            return super().detect(photo, max_num, metric)

    detector = _FlakyDetector(calls)
    adapter = BuffaloPhotoAdapter(
        revision=_revision(assets),
        assets=assets,
        detector=detector,
        recognizer=_BuffaloRecognizerFixture(calls),
    )
    adapter.warmup()
    assert adapter.ready is True

    detector.failed = True
    with pytest.raises(BuffaloAdapterError):
        adapter.warmup()
    assert adapter.ready is False


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

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pytest


def test_opencv5_runtime_supports_project_image_operations() -> None:
    assert int(cv2.__version__.split(".", maxsplit=1)[0]) == 5
    assert hasattr(cv2, "FaceDetectorYN")
    assert hasattr(cv2, "FaceRecognizerSF")

    source = np.full((32, 48, 3), 127, dtype=np.uint8)
    encoded_ok, encoded = cv2.imencode(
        ".jpg", source, [int(cv2.IMWRITE_JPEG_QUALITY), 85]
    )
    assert encoded_ok

    decoded = cv2.imdecode(
        np.frombuffer(encoded.tobytes(), dtype=np.uint8), cv2.IMREAD_COLOR
    )
    assert decoded is not None
    resized = cv2.resize(decoded, (24, 16), interpolation=cv2.INTER_AREA)
    assert resized.shape == (16, 24, 3)


def test_opencv5_sface_models_load_and_process_an_image() -> None:
    project_root = Path(__file__).parents[2]
    model_root = Path(
        os.environ.get(
            "OPENCV5_MODEL_DIR",
            project_root / "models" / "opencv_sface",
        )
    )
    detector_path = model_root / "yunet.onnx"
    recognizer_path = model_root / "sface.onnx"
    if not all(path.is_file() for path in (detector_path, recognizer_path)):
        pytest.skip("OpenCV SFace smoke assets are not mounted")

    image_path = (
        Path(os.environ["OPENCV5_SMOKE_IMAGE"])
        if "OPENCV5_SMOKE_IMAGE" in os.environ
        else project_root / "Untitled.jpeg"
    )
    image = (
        cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image_path.is_file()
        else np.zeros((64, 64, 3), dtype=np.uint8)
    )
    assert image is not None and image.size > 0
    height, width = image.shape[:2]

    detector = cv2.FaceDetectorYN.create(
        str(detector_path), "", (320, 320)
    )
    recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), "")
    detector.setInputSize((width, height))
    detected, faces = detector.detect(image)

    assert isinstance(detected, (bool, int, np.integer))
    if faces is not None and len(faces) > 0:
        aligned = recognizer.alignCrop(image, faces[0])
        feature = recognizer.feature(aligned)
        assert np.asarray(feature).reshape(-1).size == 128

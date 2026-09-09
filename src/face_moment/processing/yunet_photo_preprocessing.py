"""Bounded YuNet geometry; alignment still consumes the oriented original.

@docs .memory-bank/domains/photo-processing.md#versioned-photographer-preprocessing
"""

from collections.abc import Callable, Iterator
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

PHOTO_640_VERSION = "opencv-photo-640-v2"
PHOTO_MULTISCALE_VERSION = "opencv-photo-640-1280-v2"


def photo_detection_edges(version: str) -> tuple[int, ...] | None:
    if version == PHOTO_640_VERSION:
        return (640,)
    if version == PHOTO_MULTISCALE_VERSION:
        return (640, 1280)
    if version.startswith("opencv-photo-"):
        raise ValueError("unsupported SFace Photo preprocessing version")
    # Historical configured labels predate bounded Photo detection.
    return None


def detection_images(
    original: NDArray[np.uint8], edges: tuple[int, ...]
) -> Iterator[NDArray[np.uint8]]:
    height, width = original.shape[:2]
    seen: set[tuple[int, int]] = set()
    for edge in edges:
        scale = min(1.0, edge / max(height, width))
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        if size in seen:
            continue
        seen.add(size)
        yield original if size == (width, height) else cast(
            NDArray[np.uint8], cv2.resize(original, size, interpolation=cv2.INTER_AREA)
        )


def detect_photo_faces(
    original: NDArray[np.uint8],
    edges: tuple[int, ...],
    detect: Callable[[NDArray[np.uint8]], NDArray[np.float32] | None],
) -> tuple[NDArray[np.float32], ...]:
    height, width = original.shape[:2]
    candidates: list[tuple[int, NDArray[np.float32]]] = []
    for pass_index, image in enumerate(detection_images(original, edges)):
        detected = detect(image)
        if detected is None:
            continue
        for row in detected:
            mapped = np.array(row, dtype=np.float32, copy=True)
            if mapped.shape != (15,) or not np.isfinite(mapped).all():
                raise ValueError("YuNet must return finite native detections")
            mapped[[0, 2, 4, 6, 8, 10, 12]] *= width / image.shape[1]
            mapped[[1, 3, 5, 7, 9, 11, 13]] *= height / image.shape[0]
            x, y, w, h = (float(value) for value in mapped[:4])
            if min(width, x + w) <= max(0, x) or min(height, y + h) <= max(0, y):
                continue
            candidates.append((pass_index, mapped))

    # Stable confidence ordering keeps the first/coarser pass on an exact tie.
    selected: list[tuple[int, NDArray[np.float32]]] = []
    for pass_index, face in sorted(candidates, key=lambda item: -float(item[1][14])):
        if not any(
            pass_index != other_pass and _same_face(face, other)
            for other_pass, other in selected
        ):
            selected.append((pass_index, face))
    return tuple(face for _, face in selected)


def _same_face(first: NDArray[np.float32], second: NDArray[np.float32]) -> bool:
    ax, ay, aw, ah = (float(value) for value in first[:4])
    bx, by, bw, bh = (float(value) for value in second[:4])
    intersection = max(0.0, min(ax + aw, bx + bw) - max(ax, bx)) * max(
        0.0, min(ay + ah, by + bh) - max(ay, by)
    )
    union = aw * ah + bw * bh - intersection
    if union <= 0 or intersection / union < 0.3:
        return False
    landmark_distance = float(np.linalg.norm(
        first[4:14].reshape(5, 2) - second[4:14].reshape(5, 2), axis=1
    ).mean())
    return landmark_distance <= 0.15 * min(aw, ah, bw, bh)

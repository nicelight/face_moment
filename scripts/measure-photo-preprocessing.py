"""Read-only native scale comparison; writes only local metrics/PNG overlays.

Usage: uv run --locked python scripts/measure-photo-preprocessing.py \
    --output .tasks/TASK-117-T2-FT-002-W7/measurement \
    --portraits '/tmp/!datasets/serg_1/me_1/'*.jpg \
    '/tmp/!datasets/serg_1/IMG_20230523_185218.jpg' \
    --groups '/tmp/!datasets/serg_1/FansChildrenTJ.jpg' \
    '/tmp/!datasets/serg_1/sirious-guys.jpg'
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time
import uuid

import cv2
import numpy as np
from PIL import Image

from face_moment.processing.revisions import EligiblePipelineRevision, PipelineCode
from face_moment.processing.sface_adapter import SFaceModelAssets, SFacePhotoAdapter
from face_moment.processing.yunet_photo_preprocessing import PHOTO_640_VERSION, PHOTO_MULTISCALE_VERSION


class TimedDetector:
    def __init__(self, model: object) -> None:
        self.model = model
        self.calls: list[dict] = []
        self.size = None

    def setInputSize(self, size: tuple[int, int]) -> None:
        self.size = size
        self.model.setInputSize(size)

    def detect(self, image: np.ndarray) -> tuple:
        started = time.perf_counter()
        result = self.model.detect(image)
        self.calls.append({"size": self.size, "faces": 0 if result[1] is None else len(result[1]),
                           "ms": 1000 * (time.perf_counter() - started)})
        return result


def decode(payload: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("sample JPEG decode failed")
    return image


def save_overlay(path: Path, original: np.ndarray, faces: tuple) -> None:
    scale = min(1, 1280 / max(original.shape[:2]))
    view = cv2.resize(original, (round(original.shape[1] * scale), round(original.shape[0] * scale)))
    for i, face in enumerate(faces):
        row = face.native_detection
        x, y, w, h = (float(v) for v in row[:4])
        cv2.rectangle(view, (round(x * scale), round(y * scale)), (round((x+w)*scale), round((y+h)*scale)), (0, 255, 0), 2)
        cv2.putText(view, f'{i} {row[14]:.3f}', (max(0, round(x*scale)), max(20, round(y*scale)-5)), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 0), 2)
        for lx, ly in row[4:14].reshape(5, 2):
            cv2.circle(view, (round(float(lx)*scale), round(float(ly)*scale)), 3, (0, 100, 255), -1)
    if not cv2.imwrite(str(path), view):
        raise RuntimeError("overlay write failed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portraits', nargs='+', type=Path, required=True)
    parser.add_argument('--groups', nargs='*', type=Path, default=[])
    parser.add_argument('--model-dir', type=Path, default=Path('models/opencv_sface'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--threads', type=int, default=1)
    args = parser.parse_args()
    if args.repeats < 3 or args.threads < 1:
        parser.error('at least three repeats and one CPU thread required')
    args.output.mkdir(parents=True, exist_ok=True)
    cv2.setNumThreads(args.threads)
    assets = SFaceModelAssets(
        detector_path=args.model_dir/'yunet.onnx', detector_id='yunet', detector_version='local-testing-v1',
        recognizer_path=args.model_dir/'sface.onnx', recognizer_id='sface', recognizer_version='local-testing-v1',
        preprocessing_version='opencv-bgr-v1', alignment_version='opencv-aligncrop-v1', normalization_version='l2-v1')
    now = datetime.now(timezone.utc)
    revision = EligiblePipelineRevision(id=uuid.uuid4(), pipeline_code=PipelineCode.OPENCV_SFACE,
        detector_id=assets.detector_id, detector_version=assets.detector_version,
        recognizer_id=assets.recognizer_id, recognizer_version=assets.recognizer_version,
        preprocessing_version=assets.preprocessing_version, alignment_version=assets.alignment_version,
        normalization_version=assets.normalization_version, weights_sha256=assets.weights_sha256(),
        embedding_dimension=128, created_at=now, validated_at=now)
    detector = TimedDetector(cv2.FaceDetectorYN.create(str(assets.detector_path), '', (320, 320)))
    recognizer = cv2.FaceRecognizerSF.create(str(assets.recognizer_path), '')
    report = {'opencv': cv2.__version__, 'threads': cv2.getNumThreads(), 'repeats': args.repeats,
              'weights_sha256': assets.weights_sha256(), 'samples': [],
              'timing_scope': 'decode + adapter validation/detection/alignment/embedding; excludes model load, storage and derivatives',
              'matching_scope': 'same-photo synthetic query sanity only, not camera identity accuracy; fixed 320px query inputs shared across variants'}
    for index, path in enumerate(args.portraits + args.groups):
        payload = path.read_bytes()
        original = decode(payload)
        with Image.open(path) as pil:
            orientation = pil.getexif().get(274)
        sample = {'name': path.name, 'kind': 'portrait' if path in args.portraits else 'group',
                  'sha256': hashlib.sha256(payload).hexdigest(), 'width': original.shape[1], 'height': original.shape[0],
                  'orientation': orientation, 'variants': {}}
        result_faces = {}
        adapters = {}
        for version in ('opencv-bgr-v1', PHOTO_640_VERSION, PHOTO_MULTISCALE_VERSION):
            adapter = SFacePhotoAdapter(revision=replace(revision, id=uuid.uuid4(), preprocessing_version=version),
                assets=replace(assets, preprocessing_version=version), detector=detector, recognizer=recognizer)
            adapters[version] = adapter
            adapter.process_photo(original)  # Native per-shape warmup, including recognizer when faces exist.
            elapsed, detection_elapsed, trace = [], [], []
            for _ in range(args.repeats):
                detector.calls.clear()
                started = time.perf_counter()
                faces = adapter.process_photo(decode(payload))
                elapsed.append(1000 * (time.perf_counter() - started))
                detection_elapsed.append(sum(c['ms'] for c in detector.calls))
                trace = list(detector.calls)
            result_faces[version] = faces
            save_overlay(args.output/f'{index:02d}-{version}.png', original, faces)
            sample['variants'][version] = {'faces': len(faces), 'raw_counts': [c['faces'] for c in trace],
                'sizes': [c['size'] for c in trace], 'detection_ms_median': statistics.median(detection_elapsed),
                'processing_ms_median': statistics.median(elapsed),
                'detections': [f.native_detection.tolist() for f in faces]}
        # Use exactly the same queries for both candidates; no cross-photo identity labels are inferred.
        queries = []
        for face in result_faces[PHOTO_640_VERSION]:
            x, y, w, h = (float(v) for v in face.native_detection[:4])
            crop = original[max(0, int(y-h*.35)):min(original.shape[0], int(y+h*1.35)),
                            max(0, int(x-w*.35)):min(original.shape[1], int(x+w*1.35))]
            scale = min(1, 320/max(crop.shape[:2]))
            queries.append(cv2.resize(crop, (max(1, round(crop.shape[1]*scale)), max(1, round(crop.shape[0]*scale)))))
        for version, adapter in adapters.items():
            scores = []
            for query_image in queries:
                query = adapter.prepare_reference_query(query_image)
                scores.append(None if query is None or not result_faces[version] else
                              max(float(np.dot(query.embedding, f.embedding)) for f in result_faces[version]))
            sample['variants'][version]['self_query_max_cosines'] = scores
        report['samples'].append(sample)
        print(json.dumps({'name': path.name, 'variants': {k: {a: v[a] for a in ('faces','raw_counts','detection_ms_median','processing_ms_median','self_query_max_cosines')} for k,v in sample['variants'].items()}}), flush=True)
    (args.output/'measurements.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()

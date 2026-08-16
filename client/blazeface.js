const FIRST_OCCURRENCE_LIMIT = 20;
const MEDIAPIPE_WASM_ROOT = new URL(
  "./vendor/mediapipe/wasm",
  import.meta.url,
).href.replace(/\/$/, "");
const BLAZEFACE_MODEL_ASSET = new URL(
  "./models/blaze_face_full_range/float16/1/blaze_face_full_range.tflite",
  import.meta.url,
).href;

export const BLAZEFACE_MODEL_ID = "blaze_face_full_range";
export const BLAZEFACE_MODEL_VERSION = "1";
export const BLAZEFACE_MODEL_ASSET_URL = BLAZEFACE_MODEL_ASSET;
export const BLAZEFACE_WASM_ROOT = MEDIAPIPE_WASM_ROOT;

export class BlazeFaceUnavailableError extends Error {
  constructor(message, cause) {
    super(message, { cause });
    this.name = "BlazeFaceUnavailableError";
    this.code = "blazeface_unavailable";
  }
}

async function loadMediaPipeVisionRuntime() {
  return import("./vendor/mediapipe/vision_bundle.mjs");
}

function unavailable(message, cause) {
  if (cause instanceof BlazeFaceUnavailableError) return cause;
  return new BlazeFaceUnavailableError(message, cause);
}

export async function createBlazeFaceDetector({
  runtimeLoader = loadMediaPipeVisionRuntime,
  wasmRoot = MEDIAPIPE_WASM_ROOT,
  modelAssetUrl = BLAZEFACE_MODEL_ASSET,
} = {}) {
  try {
    const runtime = await runtimeLoader();
    if (
      typeof runtime.FilesetResolver?.forVisionTasks !== "function" ||
      typeof runtime.FaceDetector?.createFromOptions !== "function"
    ) {
      throw new Error("mediapipe_face_detector_api_missing");
    }

    const vision = await runtime.FilesetResolver.forVisionTasks(wasmRoot);
    const detector = await runtime.FaceDetector.createFromOptions(vision, {
      baseOptions: {
        delegate: "CPU",
        modelAssetPath: modelAssetUrl,
      },
      runningMode: "IMAGE",
      minDetectionConfidence: 0.5,
    });

    return {
      detect(image) {
        return detector.detect(image);
      },
      close() {
        detector.close();
      },
    };
  } catch (error) {
    throw unavailable("blazeface_model_load_or_validation_failed", error);
  }
}

function frameInput(frame) {
  if (frame && typeof frame === "object" && "image" in frame) {
    return frame.image;
  }
  return frame;
}

function proposalFromDetection(detection, frame, frameIndex, detectionIndex) {
  return {
    frameIndex,
    detectionIndex,
    frameId: frame?.id ?? null,
    timestampMs: frame?.timestampMs ?? null,
    boundingBox: detection?.boundingBox ?? null,
    keypoints: detection?.keypoints ?? [],
    categories: detection?.categories ?? [],
  };
}

/**
 * Walk a ready series in the order supplied by capture. BlazeFace's returned
 * detection array is already ordered; this function deliberately performs no
 * score comparison, filtering, tracking or identity operation.
 */
export async function traverseChronologicalBlazeFaceProposals(
  frames,
  { detector, onFrame } = {},
) {
  if (!Array.isArray(frames)) {
    throw new TypeError("reference_series_must_be_an_array");
  }
  if (!detector || typeof detector.detect !== "function") {
    throw new TypeError("blazeface_detector_required");
  }

  const proposals = [];
  for (
    let frameIndex = 0;
    frameIndex < frames.length && proposals.length < FIRST_OCCURRENCE_LIMIT;
    frameIndex += 1
  ) {
    const frame = frames[frameIndex];
    const result = await detector.detect(frameInput(frame));
    const detections = Array.isArray(result?.detections) ? result.detections : [];
    const emitted = [];

    for (
      let detectionIndex = 0;
      detectionIndex < detections.length &&
      proposals.length < FIRST_OCCURRENCE_LIMIT;
      detectionIndex += 1
    ) {
      const proposal = proposalFromDetection(
        detections[detectionIndex],
        frame,
        frameIndex,
        detectionIndex,
      );
      proposals.push(proposal);
      emitted.push(proposal);
    }

    onFrame?.({
      frameIndex,
      detectionCount: detections.length,
      emittedCount: emitted.length,
      stopped: proposals.length === FIRST_OCCURRENCE_LIMIT,
    });
  }

  return proposals;
}

export async function detectReferenceSeries(frames, options = {}) {
  let detector = options.detector;
  let ownedDetector = false;

  try {
    if (!detector) {
      detector = await createBlazeFaceDetector(options);
      ownedDetector = true;
    }
    return await traverseChronologicalBlazeFaceProposals(frames, { detector });
  } catch (error) {
    throw unavailable("blazeface_reference_series_failed", error);
  } finally {
    if (ownedDetector) detector?.close();
  }
}

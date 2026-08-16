import assert from "node:assert/strict";
import {
  BLAZEFACE_MODEL_ASSET_URL,
  BLAZEFACE_MODEL_ID,
  BLAZEFACE_MODEL_VERSION,
  BlazeFaceUnavailableError,
  createBlazeFaceDetector,
  traverseChronologicalBlazeFaceProposals,
} from "../../client/blazeface.js";

function detection(label) {
  return {
    categories: [{ score: 0.99, label }],
    boundingBox: { originX: label, originY: 10, width: 20, height: 20 },
    keypoints: [],
  };
}

async function provesChronologicalDetectorOrderAndImmediateFirst20Stop() {
  const calls = [];
  const frames = [
    { id: "frame-early", timestampMs: 100, image: "early" },
    { id: "frame-middle", timestampMs: 200, image: "middle" },
    { id: "frame-late", timestampMs: 300, image: "late" },
  ];
  const detections = {
    early: [detection(1), detection(2)],
    middle: Array.from({ length: 19 }, (_, index) => detection(index + 3)),
    late: [detection(22)],
  };

  const proposals = await traverseChronologicalBlazeFaceProposals(frames, {
    detector: {
      detect(image) {
        calls.push(image);
        return { detections: detections[image] };
      },
    },
  });

  assert.equal(proposals.length, 20);
  assert.deepEqual(calls, ["early", "middle"]);
  assert.deepEqual(
    proposals.slice(0, 4).map(({ frameId, detectionIndex }) => [frameId, detectionIndex]),
    [
      ["frame-early", 0],
      ["frame-early", 1],
      ["frame-middle", 0],
      ["frame-middle", 1],
    ],
  );
  assert.equal(proposals.at(-1).boundingBox.originX, 20);
}

async function provesRepeatedOccurrencesRemainDistinct() {
  const repeated = detection(7);
  const proposals = await traverseChronologicalBlazeFaceProposals(
    [{ id: "same-person", image: "frame" }],
    { detector: { detect: () => ({ detections: [repeated, repeated] }) } },
  );

  assert.equal(proposals.length, 2);
  assert.deepEqual(
    proposals.map(({ frameId, detectionIndex }) => [frameId, detectionIndex]),
    [["same-person", 0], ["same-person", 1]],
  );
}

async function provesOnlyThePinnedMediaPipeAssetIsLoaded() {
  const calls = [];
  const detector = await createBlazeFaceDetector({
    wasmRoot: "/client/vendor/mediapipe/wasm/",
    modelAssetUrl: "/client/models/blaze_face_full_range/float16/1/blaze_face_full_range.tflite",
    runtimeLoader: async () => ({
      FilesetResolver: {
        forVisionTasks: async (root) => {
          calls.push(["wasm", root]);
          return { wasm: true };
        },
      },
      FaceDetector: {
        createFromOptions: async (_vision, options) => {
          calls.push(["model", options]);
          return { detect: () => ({ detections: [] }), close: () => {} };
        },
      },
    }),
  });

  detector.close();
  assert.equal(BLAZEFACE_MODEL_ID, "blaze_face_full_range");
  assert.equal(BLAZEFACE_MODEL_VERSION, "1");
  assert.match(BLAZEFACE_MODEL_ASSET_URL, /blaze_face_full_range\/float16\/1/);
  assert.deepEqual(calls, [
    ["wasm", "/client/vendor/mediapipe/wasm/"],
    [
      "model",
      {
        baseOptions: {
          delegate: "CPU",
          modelAssetPath: "/client/models/blaze_face_full_range/float16/1/blaze_face_full_range.tflite",
        },
        runningMode: "IMAGE",
        minDetectionConfidence: 0.5,
      },
    ],
  ]);
}

async function provesLoadFailureIsRecoverableAndHasNoFallback() {
  await assert.rejects(
    () =>
      createBlazeFaceDetector({
        runtimeLoader: async () => {
          throw new Error("fixture_model_validation_failure");
        },
      }),
    (error) => {
      assert.ok(error instanceof BlazeFaceUnavailableError);
      assert.equal(error.code, "blazeface_unavailable");
      return true;
    },
  );
}

await provesChronologicalDetectorOrderAndImmediateFirst20Stop();
await provesRepeatedOccurrencesRemainDistinct();
await provesOnlyThePinnedMediaPipeAssetIsLoaded();
await provesLoadFailureIsRecoverableAndHasNoFallback();
console.log(
  "blazeface traversal GREEN: chronological order, repeated occurrences, immediate first-20 stop, pinned asset and recoverable load failure",
);

import assert from "node:assert/strict";
import {
  buildRealtimeAttemptRequest,
  submitRealtimeAttempt,
} from "../../client/realtime-attempt.js";

const ATTEMPT_ID = "11111111-1111-4111-8111-111111111111";
const READY_AT = "2026-08-18T10:00:00.000Z";

function proposal(frameIndex, score = 0.9) {
  return {
    frameIndex,
    boundingBox: { originX: 1, originY: 2, width: 20, height: 20 },
    categories: [{ score }],
  };
}

function options(overrides = {}) {
  return {
    attemptId: ATTEMPT_ID,
    triggerSource: "physical",
    clientRelease: "task052-test",
    jpegQuality: 0.85,
    cameraDeviceId: "camera-1",
    clientToken: "secret-token-never-in-manifest",
    timing: {
      referenceSeriesReadyAt: READY_AT,
      localDetectionCompletedMs: 241,
      requestStartedMs: 278,
    },
    frames: [{ width: 32, height: 32 }, { width: 32, height: 32 }],
    frameTimestampsMs: [1000, 1120],
    proposals: [proposal(0), proposal(1, 0.8)],
    cropEncoder: async (_source, _bbox, { quality }) => ({
      blob: new Blob([`jpeg-${quality}`], { type: "image/jpeg" }),
    }),
    ...overrides,
  };
}

async function manifestFrom(body) {
  const first = body.get("manifest");
  return JSON.parse(await first.text());
}

async function provesOrdinaryRequestShapeAndOrder() {
  const request = await buildRealtimeAttemptRequest(options());
  const entries = [...request.body.entries()];
  assert.deepEqual(entries.map(([name]) => name), [
    "manifest",
    "crop_000",
    "crop_001",
  ]);
  const manifest = await manifestFrom(request.body);
  assert.deepEqual(Object.keys(manifest), [
    "schema_version",
    "attempt_id",
    "trigger_source",
    "client_release",
    "detector_id",
    "model_version",
    "jpeg_quality",
    "camera_device_id",
    "timing",
    "occurrences",
  ]);
  assert.equal(manifest.trigger_source, "sensor");
  assert.equal(manifest.detector_id, "mediapipe_blazeface_full_range");
  assert.deepEqual(manifest.timing, {
    reference_series_ready_at: READY_AT,
    local_detection_completed_ms: 241,
    request_started_ms: 278,
  });
  assert.deepEqual(manifest.occurrences, [
    {
      occurrence_index: 0,
      frame_index: 0,
      frame_offset_ms: 0,
      detector_confidence: 0.9,
      crop_part: "crop_000",
    },
    {
      occurrence_index: 1,
      frame_index: 1,
      frame_offset_ms: 120,
      detector_confidence: 0.8,
      crop_part: "crop_001",
    },
  ]);
  assert.equal(entries[0][1].type, "application/json; charset=utf-8");
  assert.equal(entries[1][1].type, "image/jpeg");
  assert.equal(entries[1][1].name, "crop_000.jpg");
  assert.equal(entries[2][1].name, "crop_001.jpg");
  assert.equal(request.headers.Authorization, "Bearer secret-token-never-in-manifest");
  assert.equal(JSON.stringify(manifest).includes("secret-token"), false);
}

async function provesZeroOccurrenceIsManifestOnly() {
  let cropCalls = 0;
  const request = await buildRealtimeAttemptRequest(options({
    proposals: [],
    cropEncoder: async () => {
      cropCalls += 1;
      throw new Error("crop encoder must not run for zero occurrences");
    },
  }));
  assert.deepEqual([...request.body.keys()], ["manifest"]);
  assert.deepEqual((await manifestFrom(request.body)).occurrences, []);
  assert.equal(cropCalls, 0);
}

async function provesTheBoundIsRejectedWithoutClientTruncation() {
  await assert.rejects(
    () => buildRealtimeAttemptRequest(options({
      proposals: Array.from({ length: 21 }, (_, index) => proposal(index)),
      frames: Array.from({ length: 21 }, () => ({ width: 32, height: 32 })),
      frameTimestampsMs: Array.from({ length: 21 }, (_, index) => index),
    })),
    /exceed_limit/,
  );
}

async function provesSubmissionUsesExactlyOnePostAndDoesNotBranch() {
  const calls = [];
  const result = await submitRealtimeAttempt({
    ...options({ proposals: [] }),
    fetchImpl: async (path, init) => {
      calls.push({ path, init });
      return { status: 200, json: async () => ({ outcome: "no_proposals" }) };
    },
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, "/api/realtime/attempts");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers["Content-Type"], undefined);
  assert.equal(result.response.status, 200);
  assert.equal(result.manifest.occurrences.length, 0);
}

await provesOrdinaryRequestShapeAndOrder();
await provesZeroOccurrenceIsManifestOnly();
await provesTheBoundIsRejectedWithoutClientTruncation();
await provesSubmissionUsesExactlyOnePostAndDoesNotBranch();
console.log(
  "realtime attempt GREEN: exact v1 manifest/parts, first-20 boundary, zero-occurrence manifest-only request and one POST",
);

import assert from "node:assert/strict";

import { createAttemptTimingRecorder } from "../../client/attempt-timing.js";

let nowMs = 1_000;
const recorder = createAttemptTimingRecorder({
  attemptId: "d7938b68-31e8-44ce-bdaa-32755a64b067",
  captureId: "attempt-7",
  referenceSeriesReadyMonotonicMs: 1_000,
  clock: () => nowMs,
  timeOriginMs: Date.parse("2026-08-01T08:12:12.456Z"),
});

nowMs = 1_241;
assert.equal(recorder.recordLocalDetectionCompleted(), 241);
nowMs = 1_278;
assert.equal(recorder.recordRequestStarted(), 278);
assert.deepEqual(recorder.manifestTiming(), {
  referenceSeriesReadyAt: "2026-08-01T08:12:13.456Z",
  localDetectionCompletedMs: 241,
  requestStartedMs: 278,
});

nowMs = 1_460;
assert.equal(recorder.recordResponseReceived(), 460);
assert.deepEqual(recorder.snapshot(), {
  attemptId: "d7938b68-31e8-44ce-bdaa-32755a64b067",
  captureId: "attempt-7",
  referenceSeriesReadyAt: "2026-08-01T08:12:13.456Z",
  referenceSeriesReadyMonotonicMs: 1000,
  referenceSeriesReadyElapsedMs: 0,
  localDetectionCompletedMs: 241,
  requestStartedMs: 278,
  responseReceivedMs: 460,
});

assert.equal(recorder.recordResponseReceived(), 460, "markers are idempotent");

assert.throws(
  () =>
    createAttemptTimingRecorder({
      referenceSeriesReadyMonotonicMs: 100,
      clock: () => 99,
      timeOriginMs: 1_000,
    }).recordLocalDetectionCompleted(),
  /client_monotonic_markers_out_of_order/,
);

assert.throws(
  () =>
    createAttemptTimingRecorder({
      referenceSeriesReadyMonotonicMs: 100,
      clock: () => 120,
      timeOriginMs: 1_000,
    }).recordRequestStarted(),
  /localDetectionCompletedMs_marker_missing/,
);

console.log(
  "attempt timing GREEN: one origin yields ordered ready/local/request/response markers and exact manifest offsets",
);

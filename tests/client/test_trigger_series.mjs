import assert from "node:assert/strict";
import {
  createReferenceCaptureController,
  normalizeCaptureConfig,
} from "../../client/trigger-series.js";

assert.deepEqual(normalizeCaptureConfig(), {
  preTriggerMs: 400,
  postTriggerMs: 2000,
  frameIntervalMs: 300,
});

let now = 0;
const pendingTimeouts = [];
const events = [];
const ignored = [];
const controller = createReferenceCaptureController({
  clock: () => now,
  captureFrame: () => null,
  cloneFrame: (frame) => frame,
  config: { preTriggerMs: 400, postTriggerMs: 1000, frameIntervalMs: 100 },
  setIntervalImpl: () => 1,
  clearIntervalImpl: () => {},
  setTimeoutImpl: (callback, delay) => {
    pendingTimeouts.push({ callback, delay });
    return pendingTimeouts.length;
  },
  clearTimeoutImpl: () => {},
  onAttemptStart: (detail) => events.push({ type: "attempt-start", detail }),
  onReferenceSeriesReady: (detail) => events.push({ type: "series-ready", detail }),
  onIgnoredTrigger: (detail) => ignored.push(detail),
});

for (const timestampMs of [0, 200, 400, 500]) {
  now = timestampMs;
  controller.recordFrame({ id: `pre-${timestampMs}` }, timestampMs);
}

now = 500;
const physical = controller.acceptTrigger("physical", { fixture: "esp32" });
assert.equal(physical.accepted, true);
assert.equal(physical.trigger_source, "physical");
assert.equal(events[0].detail.trigger_source, "physical");

const overlap = controller.acceptTrigger("test");
assert.deepEqual(overlap, {
  accepted: false,
  reason: "busy",
  state: "capturing",
  trigger_source: "test",
  ignoredAtMs: 500,
});
assert.equal(ignored[0].reason, "busy");

for (const timestampMs of [700, 900, 1200, 1400]) {
  now = timestampMs;
  controller.recordFrame({ id: `post-${timestampMs}` }, timestampMs);
}
now = 1500;
pendingTimeouts.shift().callback();

const ready = events.find((event) => event.type === "series-ready").detail;
assert.equal(ready.trigger_source, "physical");
assert.deepEqual(ready.frame_timestamps_ms, [200, 400, 500, 700, 900, 1200, 1400]);
assert.deepEqual(ready.frames.map((frame) => frame.id), [
  "pre-200",
  "pre-400",
  "pre-500",
  "post-700",
  "post-900",
  "post-1200",
  "post-1400",
]);
assert.equal(controller.state, "searching");

controller.finishAttempt();
assert.equal(controller.state, "advertising");
now = 1600;
controller.recordFrame({ id: "fresh-1600" }, now);
const testTrigger = controller.acceptTrigger("test", { fixture: "button" });
assert.equal(testTrigger.accepted, true);
assert.equal(testTrigger.trigger_source, "test");
now = 2600;
pendingTimeouts.shift().callback();
assert.equal(controller.finishAttempt({ success: true }), true);
assert.equal(controller.state, "cooldown");
const cooldownOverlap = controller.acceptTrigger("physical");
assert.equal(cooldownOverlap.reason, "busy");
pendingTimeouts.shift().callback();
assert.equal(controller.state, "advertising");

console.log("trigger series GREEN: shared physical/test path, freshness, source metadata, busy rejection");

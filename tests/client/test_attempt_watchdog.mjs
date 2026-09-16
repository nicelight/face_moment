import assert from "node:assert/strict";
import test from "node:test";
import { AttemptOutcomeController } from "../../client/attempt-outcome.js";
import { ReferenceCaptureController } from "../../client/trigger-series.js";
import { submitRealtimeAttempt } from "../../client/realtime-attempt.js";

function response(attemptId) {
  return { status: 200, json: async () => ({
    schema_version: 1, attempt_id: attemptId, outcome: "no_proposals",
  }) };
}

test("pending transport aborts at 20 seconds and permits a fresh capture", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const capture = new ReferenceCaptureController({ captureFrame: () => ({}) });
  capture.setState("searching");
  const timeouts = [];
  const controller = new AttemptOutcomeController({ onTimeout: detail => {
    timeouts.push(detail);
    capture.finishAttempt({ success: false });
  } });
  const id = "11111111-1111-4111-8111-111111111111";
  controller.beginAttempt({ attemptId: id, captureId: "capture-old" });
  const signal = controller.signal;
  let sent;
  const started = new Promise(resolve => { sent = resolve; });
  void submitRealtimeAttempt({
    attemptId: id, signal, triggerSource: "test", jpegQuality: 0.85,
    cameraDeviceId: "camera", clientToken: "fixture-token",
    timing: { referenceSeriesReadyAt: "2026-09-16T00:00:00Z",
      localDetectionCompletedMs: 0, requestStartedMs: 0 },
    fetchImpl: (_path, init) => {
      assert.equal(init.signal, signal);
      sent();
      return new Promise(() => {}); // Deliberately ignores abort.
    },
  });
  await started;
  t.mock.timers.tick(19999);
  assert.equal(controller.state, "searching");
  t.mock.timers.tick(1);
  assert.equal(signal.aborted, true);
  assert.equal(controller.state, "advertising");
  assert.equal(capture.state, "advertising");
  assert.equal(timeouts.length, 1);
  assert.equal(timeouts[0].captureId, "capture-old");
  capture.recordFrame({});
  assert.equal(capture.acceptTrigger("test").accepted, true);
  capture.stop();
  controller.beginAttempt({ attemptId: "fresh", captureId: "capture-fresh" });
  await controller.handleResponse("fresh", response("fresh"));
  t.mock.timers.tick(20000);
  assert.equal(timeouts.length, 1);
});

for (const lateFailure of [false, true]) {
  test(`pending JSON times out; late ${lateFailure ? "failure" : "success"} is stale`, async (t) => {
    t.mock.timers.enable({ apis: ["setTimeout"] });
    const timeouts = [];
    const controller = new AttemptOutcomeController({ onTimeout: x => timeouts.push(x) });
    controller.beginAttempt({ attemptId: "old" });
    let resolveBody, rejectBody;
    const body = new Promise((resolve, reject) => { resolveBody = resolve; rejectBody = reject; });
    const pending = controller.handleResponse("old", { status: 200, json: () => body });
    const signal = controller.signal;
    t.mock.timers.tick(20000);
    assert.equal(signal.aborted, true);
    assert.equal(controller.state, "advertising");
    controller.beginAttempt({ attemptId: "new" });
    if (lateFailure) rejectBody(new Error("late body failure"));
    else resolveBody({ schema_version: 1, attempt_id: "old", outcome: "result", result: {} });
    assert.equal((await pending).stale, true);
    assert.equal(controller.isCurrent("new"), true);
    await controller.handleResponse("new", response("new"));
    t.mock.timers.tick(20000);
    assert.equal(timeouts.length, 1);
  });
}

test("normal result and immediate failure clear the watchdog", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const timeouts = [];
  const controller = new AttemptOutcomeController({ onTimeout: x => timeouts.push(x) });
  controller.beginAttempt({ attemptId: "success" });
  await controller.handleResponse("success", {
    status: 200, json: async () => ({ schema_version: 1,
      attempt_id: "success", outcome: "result", result: {} }),
  });
  t.mock.timers.tick(20000);
  assert.equal(controller.state, "result");
  controller.releaseResult("success");
  controller.beginAttempt({ attemptId: "failure" });
  controller.handleTransportFailure("failure");
  t.mock.timers.tick(20000);
  assert.equal(timeouts.length, 0);
});

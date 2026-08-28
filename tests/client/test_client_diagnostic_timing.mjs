import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { createAttemptTimingRecorder } from "../../client/attempt-timing.js";
import {
  CLIENT_TIMING_SCHEMA_VERSION,
  reportClientResponseTiming,
} from "../../client/diagnostic-timing.js";

const ATTEMPT_ID = "d7938b68-31e8-44ce-bdaa-32755a64b067";

async function provesOneClockExactBestEffortReport() {
  let nowMs = 1_000;
  const recorder = createAttemptTimingRecorder({
    attemptId: ATTEMPT_ID,
    referenceSeriesReadyMonotonicMs: 1_000,
    clock: () => nowMs,
    timeOriginMs: Date.parse("2026-08-28T00:00:00.000Z"),
  });
  nowMs = 1_120;
  recorder.recordLocalDetectionCompleted();
  nowMs = 1_240;
  recorder.recordRequestStarted();
  nowMs = 1_842;
  const responseReceivedMs = recorder.recordResponseReceived();

  const calls = [];
  const expectedResponse = { status: 200 };
  const response = await reportClientResponseTiming({
    attemptId: ATTEMPT_ID,
    responseReceivedMs,
    clientToken: "task083-disposable-token",
    fetchImpl: async (path, init) => {
      calls.push({ path, init });
      return expectedResponse;
    },
  });

  assert.equal(response, expectedResponse);
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].path,
    `/api/realtime/attempts/${ATTEMPT_ID}/client-timing`,
  );
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(calls[0].init.headers, {
    Authorization: "Bearer task083-disposable-token",
    "Content-Type": "application/json",
  });
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    schema_version: CLIENT_TIMING_SCHEMA_VERSION,
    response_received_ms: 842,
  });
  assert.equal(calls[0].init.body.includes("task083-disposable-token"), false);
}

async function provesNetworkFailureHasNoRetryOrQueue() {
  let calls = 0;
  await assert.rejects(
    () =>
      reportClientResponseTiming({
        attemptId: ATTEMPT_ID,
        responseReceivedMs: 842,
        clientToken: "task083-offline-token",
        fetchImpl: async () => {
          calls += 1;
          throw new Error("offline");
        },
      }),
    /offline/,
  );
  assert.equal(calls, 1);
  await assert.rejects(
    () =>
      reportClientResponseTiming({
        attemptId: ATTEMPT_ID,
        responseReceivedMs: true,
        clientToken: "task083-offline-token",
        fetchImpl: async () => ({ status: 200 }),
      }),
    /response_received_ms_must_be_non_negative_integer/,
  );
}

async function provesProductionWiringDoesNotBlockOutcomeHandling() {
  const app = await readFile("client/app.js", "utf8");
  const sender = await readFile("client/diagnostic-timing.js", "utf8");
  assert.match(
    app,
    /import \{ reportClientResponseTiming \} from "\.\/diagnostic-timing\.js";/,
  );
  assert.match(app, /void reportClientResponseTiming\(\{/);
  assert.match(app, /\}\)\.catch\(\(\) => \{\}\);/);
  assert.doesNotMatch(app, /await reportClientResponseTiming\(/);

  const marker = app.indexOf("timingRecorder.recordResponseReceived()");
  const report = app.indexOf("void reportClientResponseTiming({");
  const outcomeDispatch = app.indexOf(
    'new CustomEvent("face-moment:attempt-response"',
    report,
  );
  assert.ok(marker >= 0 && marker < report);
  assert.ok(report < outcomeDispatch);
  assert.doesNotMatch(sender, /localStorage|indexedDB|setTimeout|retry|queue/i);
}

await provesOneClockExactBestEffortReport();
await provesNetworkFailureHasNoRetryOrQueue();
await provesProductionWiringDoesNotBlockOutcomeHandling();

console.log(
  "client diagnostic timing GREEN: one monotonic response marker is reported once without blocking, retry, queue, or credential body retention",
);

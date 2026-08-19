import assert from "node:assert/strict";
import {
  AttemptOutcomeController,
  REALTIME_ATTEMPT_OUTCOMES,
} from "../../client/attempt-outcome.js";

const RESPONSE_ATTEMPT = "attempt-a";

function response(attemptId, outcome, result = undefined) {
  return {
    status: 200,
    json: async () => ({
      schema_version: 1,
      attempt_id: attemptId,
      outcome,
      ...(result === undefined ? {} : { result }),
    }),
  };
}

async function provesTypedNonSuccessReturnsToAdvertising() {
  const states = [];
  const outcomes = [];
  const controller = new AttemptOutcomeController({
    onStateChange: (state) => states.push(state),
    onOutcome: (outcome) => outcomes.push(outcome),
  });

  controller.beginAttempt({ attemptId: RESPONSE_ATTEMPT, captureId: "series-a" });
  const result = await controller.handleResponse(
    RESPONSE_ATTEMPT,
    response(RESPONSE_ATTEMPT, "insufficient_results"),
  );

  assert.deepEqual(result, {
    handled: true,
    stale: false,
    attemptId: RESPONSE_ATTEMPT,
    state: "advertising",
    outcome: "insufficient_results",
    retryEligible: true,
  });
  assert.equal(controller.state, "advertising");
  assert.equal(states.at(-1).state, "advertising");
  assert.deepEqual(outcomes, [result]);
}

async function provesTransportFailureAndFreshCaptureRetry() {
  const controller = new AttemptOutcomeController();
  controller.beginAttempt({ attemptId: "attempt-b", captureId: "series-b" });
  const failed = controller.handleTransportFailure("attempt-b");
  assert.deepEqual(failed, {
    handled: true,
    stale: false,
    attemptId: "attempt-b",
    state: "advertising",
    retryEligible: true,
    reason: "transport_failure",
  });

  controller.beginAttempt({ attemptId: "attempt-c", captureId: "series-c" });
  assert.equal(controller.state, "searching");
  assert.throws(
    () => controller.beginAttempt({ attemptId: "attempt-c", captureId: "series-c" }),
    /attempt_already_active/,
  );
  controller.handleTransportFailure("attempt-c");
  assert.throws(
    () => controller.beginAttempt({ attemptId: "attempt-b", captureId: "series-new" }),
    /fresh_capture_required/,
  );
  assert.throws(
    () => controller.beginAttempt({ attemptId: "attempt-new", captureId: "series-c" }),
    /fresh_capture_required/,
  );
}

async function provesLateWorkCannotReplaceNewerState() {
  const controller = new AttemptOutcomeController();
  controller.beginAttempt({ attemptId: "attempt-old", captureId: "series-old" });
  controller.handleTransportFailure("attempt-old");
  controller.beginAttempt({ attemptId: "attempt-new", captureId: "series-new" });

  const stale = await controller.handleResponse(
    "attempt-old",
    response("attempt-old", "result", { session_id: "old" }),
  );
  assert.equal(stale.stale, true);
  assert.equal(controller.state, "searching");
  assert.equal(controller.isCurrent("attempt-new"), true);
}

async function provesHttpAndTypedResponseFailuresUseNoProse() {
  const controller = new AttemptOutcomeController();
  controller.beginAttempt({ attemptId: "attempt-http", captureId: "series-http" });
  let parsed = false;
  const httpFailure = await controller.handleResponse("attempt-http", {
    status: 503,
    json: async () => {
      parsed = true;
      return { message: "server unavailable" };
    },
  });
  assert.equal(httpFailure.reason, "http_failure");
  assert.equal(httpFailure.status, 503);
  assert.equal(parsed, false);

  controller.beginAttempt({ attemptId: "attempt-invalid", captureId: "series-invalid" });
  const invalid = await controller.handleResponse("attempt-invalid", {
    status: 200,
    json: async () => ({ message: "not a machine outcome" }),
  });
  assert.equal(invalid.reason, "typed_response_invalid");
  assert.equal(controller.state, "advertising");
}

async function provesResultUsesMinimalHoldingStateWithoutCooldown() {
  const controller = new AttemptOutcomeController();
  controller.beginAttempt({ attemptId: "attempt-result", captureId: "series-result" });
  const result = await controller.handleResponse(
    "attempt-result",
    response("attempt-result", "result", {
      session_id: "opaque-session",
      teasers: [],
    }),
  );

  assert.equal(result.state, "result");
  assert.equal(result.retryEligible, false);
  assert.equal(controller.state, "result");
  assert.deepEqual(controller.snapshot(), { state: "result" });
  assert.equal(controller.releaseResult("attempt-result"), true);
  assert.equal(controller.state, "advertising");
}

await provesTypedNonSuccessReturnsToAdvertising();
await provesTransportFailureAndFreshCaptureRetry();
await provesLateWorkCannotReplaceNewerState();
await provesHttpAndTypedResponseFailuresUseNoProse();
await provesResultUsesMinimalHoldingStateWithoutCooldown();
assert.deepEqual([...REALTIME_ATTEMPT_OUTCOMES].sort(), [
  "busy",
  "deadline",
  "in_progress",
  "insufficient_results",
  "interrupted",
  "no_proposals",
  "result",
  "unacceptable_query",
]);
console.log(
  "attempt outcome GREEN: typed branches, transport recovery, stale discard, fresh capture identity and result holding",
);

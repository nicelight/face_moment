import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  PromoDisplayController,
  validateDisplayConfiguration,
} from "../../client/promo-display.js";
import { createAttemptOutcomeController } from "../../client/attempt-outcome.js";
import { createReferenceCaptureController } from "../../client/trigger-series.js";

const ORIGIN = "https://central.example.test";

class FakeElement {
  constructor() {
    this.children = [];
    this.classList = { add: () => {} };
    this.dataset = {};
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  setAttribute() {}

  getBoundingClientRect() {
    return { width: 320, height: 320 };
  }
}

function displayDocument() {
  return {
    createElement: () => new FakeElement(),
    createElementNS: () => new FakeElement(),
  };
}

function result() {
  return {
    session_id: "session-078",
    teasers: Array.from({ length: 4 }, (_, index) => ({
      photo_id: `photo-${index}`,
      media_url: `${ORIGIN}/api/promo/media/${String(index).padStart(43, "r")}`,
    })),
    n: 4,
    qr_url: `${ORIGIN}/q?ticket=fixture-ticket-078`,
  };
}

function mediaResponse() {
  return {
    ok: true,
    status: 200,
    blob: async () => new Blob(["jpeg"], { type: "image/jpeg" }),
  };
}

function displayController({ timers, expired }) {
  globalThis.localStorage = { getItem: () => "fixture-display-token" };
  return new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: displayDocument(),
    fetchImpl: async () => mediaResponse(),
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: { createObjectURL: () => "blob:fixture" },
    setTimeoutImpl: (callback, delay) => {
      const timer = { callback, delay };
      timers.push(timer);
      return timer;
    },
    clearTimeoutImpl: (timer) => {
      timer.cleared = true;
    },
    onExpired: expired,
  });
}

test("validates exact independent positive display configuration", () => {
  assert.deepEqual(
    validateDisplayConfiguration({
      schema_version: 1,
      result_display_ms: 150,
      success_cooldown_ms: 300,
    }),
    {
      schema_version: 1,
      result_display_ms: 150,
      success_cooldown_ms: 300,
    },
  );
  for (const configuration of [
    { schema_version: 1, result_display_ms: 0, success_cooldown_ms: 300 },
    { schema_version: 1, result_display_ms: 150, success_cooldown_ms: -1 },
    { schema_version: 1, result_display_ms: 150, success_cooldown_ms: 150, extra: true },
  ]) {
    assert.throws(() => validateDisplayConfiguration(configuration));
  }
});

test("display expiry and success cooldown use separate controlled timers", async () => {
  const displayTimers = [];
  const expired = [];
  const controller = displayController({
    timers: displayTimers,
    expired: (detail) => expired.push(detail),
  });

  const detail = await controller.showResult({
    attemptId: "attempt-078",
    result: result(),
    displayConfig: {
      schema_version: 1,
      result_display_ms: 150,
      success_cooldown_ms: 300,
    },
  });
  assert.equal(detail.resultDisplayMs, 150);
  assert.equal(detail.successCooldownMs, 300);
  assert.equal(displayTimers.length, 1);
  assert.equal(displayTimers[0].delay, 150);
  assert.equal(controller.isVisible, true);

  const cooldownTimers = [];
  const trigger = createReferenceCaptureController({
    captureFrame: () => null,
    setIntervalImpl: () => null,
    setTimeoutImpl: (callback, delay) => {
      const timer = { callback, delay };
      cooldownTimers.push(timer);
      return timer;
    },
    clearTimeoutImpl: () => {},
  });
  assert.equal(trigger.finishAttempt({ success: true, cooldownMs: 300 }), true);
  assert.equal(trigger.state, "cooldown");
  assert.equal(cooldownTimers[0].delay, 300);

  displayTimers[0].callback();
  assert.deepEqual(expired, [{
    handled: true,
    stale: false,
    attemptId: "attempt-078",
    state: "advertising",
    reason: "display_expired",
    resultDisplayMs: 150,
  }]);
  assert.equal(controller.isVisible, false);
  assert.equal(trigger.state, "cooldown");
  cooldownTimers[0].callback();
  assert.equal(trigger.state, "advertising");
});

test("delayed confirmed acknowledgement cannot extend or revive expired display", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token-ack-delay" };
  const config = {
    schema_version: 1,
    result_display_ms: 150,
    success_cooldown_ms: 300,
  };
  const displayTimers = [];
  const expired = [];
  const completions = [];
  const failures = [];
  const calls = [];
  let releaseAcknowledgement;
  let resolveAcknowledgementStarted;
  const acknowledgementStarted = new Promise((resolve) => {
    resolveAcknowledgementStarted = resolve;
  });
  const container = new FakeElement();
  let replaceChildrenCalls = 0;
  const replaceChildren = container.replaceChildren.bind(container);
  container.replaceChildren = (...children) => {
    replaceChildrenCalls += 1;
    replaceChildren(...children);
  };
  const controller = new PromoDisplayController({
    container,
    origin: ORIGIN,
    documentImpl: displayDocument(),
    clock: () => 100,
    fetchImpl: (url) => {
      calls.push(url);
      if (String(url).includes("/api/promo/media/")) {
        return Promise.resolve(mediaResponse());
      }
      resolveAcknowledgementStarted();
      return new Promise((resolve) => {
        releaseAcknowledgement = resolve;
      });
    },
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: { createObjectURL: () => "blob:ack-delay" },
    setTimeoutImpl: (callback, delay) => {
      const timer = { callback, delay };
      displayTimers.push(timer);
      return timer;
    },
    clearTimeoutImpl: (timer) => {
      timer.cleared = true;
    },
    onComplete: (detail) => completions.push(detail),
    onFailure: (detail) => failures.push(detail),
    onExpired: (detail) => expired.push(detail),
    requireDisplayConfig: true,
  });

  const pendingResult = controller.showResult({
    attemptId: "attempt-078-ack-delay",
    result: result(),
    timing: { referenceSeriesReadyMonotonicMs: 100 },
    displayConfig: config,
  });
  await acknowledgementStarted;

  assert.equal(controller.isVisible, true);
  assert.equal(displayTimers.length, 1);
  assert.equal(displayTimers[0].delay, config.result_display_ms);
  assert.equal(calls.filter((url) => String(url).endsWith("/display")).length, 1);

  const cooldownTimers = [];
  const trigger = createReferenceCaptureController({
    captureFrame: () => null,
    setIntervalImpl: () => null,
    setTimeoutImpl: (callback, delay) => {
      const timer = { callback, delay };
      cooldownTimers.push(timer);
      return timer;
    },
    clearTimeoutImpl: () => {},
  });
  assert.equal(trigger.finishAttempt({ success: true, cooldownMs: config.success_cooldown_ms }), true);
  assert.equal(trigger.state, "cooldown");
  assert.equal(cooldownTimers.length, 1);
  assert.equal(cooldownTimers[0].delay, config.success_cooldown_ms);

  displayTimers[0].callback();
  assert.equal(expired.length, 1);
  assert.equal(controller.isVisible, false);
  assert.deepEqual(expired[0], {
    handled: true,
    stale: false,
    attemptId: "attempt-078-ack-delay",
    state: "advertising",
    reason: "display_expired",
    resultDisplayMs: config.result_display_ms,
  });
  assert.equal(trigger.state, "cooldown");
  const replaceCallsAfterExpiry = replaceChildrenCalls;

  displayTimers[0].callback();
  assert.equal(expired.length, 1);
  assert.equal(replaceChildrenCalls, replaceCallsAfterExpiry);

  releaseAcknowledgement({ ok: true, status: 200 });
  const staleDetail = await pendingResult;
  assert.deepEqual(staleDetail, {
    stale: true,
    attemptId: "attempt-078-ack-delay",
  });
  assert.equal(calls.filter((url) => String(url).endsWith("/display")).length, 1);
  assert.deepEqual(completions, []);
  assert.deepEqual(failures, []);
  assert.equal(displayTimers.length, 1);
  assert.equal(controller.isVisible, false);
  assert.equal(replaceChildrenCalls, replaceCallsAfterExpiry);
  assert.equal(trigger.state, "cooldown");

  cooldownTimers[0].callback();
  assert.equal(trigger.state, "advertising");
});

test("app display expiry releases capture for the next trigger without success cooldown", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token-app-expiry" };
  const config = {
    schema_version: 1,
    result_display_ms: 150,
    success_cooldown_ms: 300,
  };
  const sessionResult = {
    ...result(),
    session_id: "session-078-app-expiry",
    qr_url: `${ORIGIN}/q?ticket=app-expiry-ticket`,
  };
  const sessionSnapshot = JSON.stringify(sessionResult);
  let now = 0;
  const triggerTimers = [];
  const trigger = createReferenceCaptureController({
    captureFrame: () => ({ frame: "camera-frame" }),
    config: { preTriggerMs: 100, postTriggerMs: 20, frameIntervalMs: 10 },
    clock: () => now,
    setIntervalImpl: () => null,
    setTimeoutImpl: (callback, delay) => {
      const timer = { callback, delay };
      triggerTimers.push(timer);
      return timer;
    },
    clearTimeoutImpl: () => {},
  });
  trigger.recordFrame({ frame: "camera-frame" }, now);
  const captured = trigger.acceptTrigger("test");
  assert.equal(captured.accepted, true);
  trigger.finishCapture(captured.attemptId);
  assert.equal(trigger.state, "searching");

  const lifecycleSnapshots = [];
  const outcome = createAttemptOutcomeController({
    onStateChange: (snapshot) => lifecycleSnapshots.push(snapshot),
  });
  const realtimeAttemptId = "realtime-attempt-078-app-expiry";
  outcome.beginAttempt({
    attemptId: realtimeAttemptId,
    captureId: captured.attemptId,
  });
  const responseResult = await outcome.handleResponse(realtimeAttemptId, {
    status: 200,
    json: async () => ({
      schema_version: 1,
      attempt_id: realtimeAttemptId,
      outcome: "result",
      result: sessionResult,
    }),
  });
  assert.equal(responseResult.state, "result");

  const appWindow = new EventTarget();
  const finishedEvents = [];
  appWindow.addEventListener("face-moment:attempt-finished", (event) => {
    finishedEvents.push({ ...event.detail });
    trigger.finishAttempt({
      success: event.detail?.success === true,
      cooldownMs: event.detail?.cooldownMs ?? 0,
    });
  });

  const displayTimers = [];
  const expiryHandlerCalls = [];
  const completions = [];
  const failures = [];
  const reportCalls = [];
  let releaseAcknowledgement;
  let resolveAcknowledgementStarted;
  const acknowledgementStarted = new Promise((resolve) => {
    resolveAcknowledgementStarted = resolve;
  });
  const promo = new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: displayDocument(),
    fetchImpl: (url) => {
      if (String(url).includes("/api/promo/media/")) {
        return Promise.resolve(mediaResponse());
      }
      reportCalls.push(url);
      resolveAcknowledgementStarted();
      return new Promise((resolve) => {
        releaseAcknowledgement = resolve;
      });
    },
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: { createObjectURL: () => "blob:app-expiry" },
    clock: () => 100,
    setTimeoutImpl: (callback, delay) => {
      const timer = { callback, delay };
      displayTimers.push(timer);
      return timer;
    },
    clearTimeoutImpl: (timer) => {
      timer.cleared = true;
    },
    onComplete: (detail) => completions.push(detail),
    onFailure: (detail) => failures.push(detail),
    onExpired: (detail) => {
      expiryHandlerCalls.push(detail);
      if (detail?.handled !== true || detail?.stale === true) return;
      const released = outcome.releaseResult(detail.attemptId);
      if (!released) return;
      appWindow.dispatchEvent(new CustomEvent("face-moment:attempt-finished", {
        detail: {
          attemptId: detail.attemptId,
          success: false,
          reason: detail.reason ?? "display_expired",
        },
      }));
    },
    requireDisplayConfig: true,
  });
  let nextTriggerResult;
  appWindow.addEventListener("face-moment:trigger-request", (event) => {
    if (promo.isVisible) {
      nextTriggerResult = { accepted: false, reason: "busy" };
      return;
    }
    nextTriggerResult = trigger.acceptTrigger(
      event.detail?.trigger_source,
      event.detail,
    );
  });

  const pendingRender = promo.showResult({
    attemptId: realtimeAttemptId,
    result: sessionResult,
    timing: { referenceSeriesReadyMonotonicMs: 100 },
    displayConfig: config,
  });
  await acknowledgementStarted;
  assert.equal(displayTimers.length, 1);
  assert.equal(displayTimers[0].delay, config.result_display_ms);
  assert.equal(promo.isVisible, true);
  assert.equal(outcome.state, "result");
  assert.equal(trigger.state, "searching");
  assert.equal(triggerTimers.filter((timer) => timer.delay === config.success_cooldown_ms).length, 0);

  displayTimers[0].callback();
  assert.equal(expiryHandlerCalls.length, 1);
  assert.equal(finishedEvents.length, 1);
  assert.deepEqual(finishedEvents[0], {
    attemptId: realtimeAttemptId,
    success: false,
    reason: "display_expired",
  });
  assert.equal(outcome.state, "advertising");
  assert.equal(trigger.state, "advertising");
  assert.equal(triggerTimers.filter((timer) => timer.delay === config.success_cooldown_ms).length, 0);

  const staleExpiry = {
    handled: true,
    stale: true,
    attemptId: realtimeAttemptId,
    reason: "display_expired",
  };
  const failedReleaseExpiry = {
    handled: true,
    stale: false,
    attemptId: realtimeAttemptId,
    reason: "display_expired",
  };
  promo.onExpired(staleExpiry);
  promo.onExpired(failedReleaseExpiry);
  assert.equal(finishedEvents.length, 1);
  assert.equal(outcome.state, "advertising");
  assert.equal(trigger.state, "advertising");

  now = 1;
  trigger.recordFrame({ frame: "next-camera-frame" }, now);
  appWindow.dispatchEvent(new CustomEvent("face-moment:trigger-request", {
    detail: { trigger_source: "test", requested_from: "expiry-regression" },
  }));
  const nextTrigger = nextTriggerResult;
  assert.equal(nextTrigger.accepted, true);
  trigger.finishCapture(nextTrigger.attemptId);
  appWindow.dispatchEvent(new CustomEvent("face-moment:attempt-finished", {
    detail: {
      attemptId: nextTrigger.attemptId,
      success: true,
      cooldownMs: config.success_cooldown_ms,
    },
  }));
  assert.equal(trigger.state, "cooldown");
  const cooldownTimers = triggerTimers.filter(
    (timer) => timer.delay === config.success_cooldown_ms,
  );
  assert.equal(cooldownTimers.length, 1);

  const stateBeforeLateAcknowledgement = {
    outcome: outcome.snapshot(),
    triggerState: trigger.state,
    finishedEvents: finishedEvents.map((event) => ({ ...event })),
    displayTimerCount: displayTimers.length,
    reportCount: reportCalls.length,
    session: JSON.stringify(sessionResult),
    lifecycleCount: lifecycleSnapshots.length,
  };
  releaseAcknowledgement({ ok: true, status: 200 });
  const lateAcknowledgement = await pendingRender;
  assert.deepEqual(lateAcknowledgement, {
    stale: true,
    attemptId: realtimeAttemptId,
  });
  assert.deepEqual(completions, []);
  assert.deepEqual(failures, []);
  assert.equal(finishedEvents.filter((event) => event.success === false).length, 1);
  assert.equal(expiryHandlerCalls.length, 3);
  assert.equal(displayTimers.length, stateBeforeLateAcknowledgement.displayTimerCount);
  assert.equal(reportCalls.length, stateBeforeLateAcknowledgement.reportCount);
  assert.equal(JSON.stringify(sessionResult), sessionSnapshot);
  assert.deepEqual(
    {
      outcome: outcome.snapshot(),
      triggerState: trigger.state,
      finishedEvents,
      displayTimerCount: displayTimers.length,
      reportCount: reportCalls.length,
      session: JSON.stringify(sessionResult),
      lifecycleCount: lifecycleSnapshots.length,
    },
    stateBeforeLateAcknowledgement,
  );

  cooldownTimers[0].callback();
  assert.equal(trigger.state, "advertising");
});

test("ordinary successful acknowledgement keeps capture cooldown after display expiry", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token-success-cooldown" };
  const config = {
    schema_version: 1,
    result_display_ms: 150,
    success_cooldown_ms: 300,
  };
  const sessionResult = {
    ...result(),
    session_id: "session-078-success-cooldown",
    qr_url: `${ORIGIN}/q?ticket=success-cooldown-ticket`,
  };
  const sessionSnapshot = JSON.stringify(sessionResult);
  let now = 0;
  const triggerTimers = [];
  const trigger = createReferenceCaptureController({
    captureFrame: () => ({ frame: "camera-frame" }),
    config: { preTriggerMs: 100, postTriggerMs: 20, frameIntervalMs: 10 },
    clock: () => now,
    setIntervalImpl: () => null,
    setTimeoutImpl: (callback, delay) => {
      const timer = { callback, delay };
      triggerTimers.push(timer);
      return timer;
    },
    clearTimeoutImpl: () => {},
  });
  trigger.recordFrame({ frame: "camera-frame" }, now);
  const captured = trigger.acceptTrigger("test");
  assert.equal(captured.accepted, true);
  trigger.finishCapture(captured.attemptId);
  assert.equal(trigger.state, "searching");

  const outcome = createAttemptOutcomeController();
  const realtimeAttemptId = "realtime-attempt-078-success-cooldown";
  outcome.beginAttempt({
    attemptId: realtimeAttemptId,
    captureId: captured.attemptId,
  });
  const responseResult = await outcome.handleResponse(realtimeAttemptId, {
    status: 200,
    json: async () => ({
      schema_version: 1,
      attempt_id: realtimeAttemptId,
      outcome: "result",
      result: sessionResult,
    }),
  });
  assert.equal(responseResult.state, "result");

  const appWindow = new EventTarget();
  const finishedEvents = [];
  let successfulCooldownAttemptId = null;
  appWindow.addEventListener("face-moment:attempt-finished", (event) => {
    finishedEvents.push({ ...event.detail });
    const finished = trigger.finishAttempt({
      success: event.detail?.success === true,
      cooldownMs: event.detail?.cooldownMs ?? 0,
    });
    if (event.detail?.success === true && finished) {
      successfulCooldownAttemptId = event.detail.attemptId;
    }
  });

  const displayTimers = [];
  const reportCalls = [];
  const expiryDetails = [];
  const promo = new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: displayDocument(),
    fetchImpl: (url) => {
      if (String(url).includes("/api/promo/media/")) {
        return Promise.resolve(mediaResponse());
      }
      reportCalls.push(url);
      return Promise.resolve({ ok: true, status: 200 });
    },
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: { createObjectURL: () => "blob:success-cooldown" },
    clock: () => 100,
    setTimeoutImpl: (callback, delay) => {
      const timer = { callback, delay };
      displayTimers.push(timer);
      return timer;
    },
    clearTimeoutImpl: (timer) => {
      timer.cleared = true;
    },
    onComplete: (detail) => {
      appWindow.dispatchEvent(new CustomEvent("face-moment:attempt-finished", {
        detail: {
          attemptId: detail.attemptId,
          success: true,
          cooldownMs: detail.successCooldownMs,
        },
      }));
    },
    onExpired: (detail) => {
      expiryDetails.push(detail);
      if (detail?.handled !== true || detail?.stale === true) return;
      const released = outcome.releaseResult(detail.attemptId);
      if (!released) return;
      if (successfulCooldownAttemptId !== detail.attemptId) {
        appWindow.dispatchEvent(new CustomEvent("face-moment:attempt-finished", {
          detail: {
            attemptId: detail.attemptId,
            success: false,
            reason: detail.reason ?? "display_expired",
          },
        }));
      }
    },
    requireDisplayConfig: true,
  });

  const rendered = await promo.showResult({
    attemptId: realtimeAttemptId,
    result: sessionResult,
    timing: { referenceSeriesReadyMonotonicMs: 100 },
    displayConfig: config,
  });
  assert.equal(rendered.state, "result");
  assert.equal(displayTimers.length, 1);
  assert.equal(displayTimers[0].delay, config.result_display_ms);
  assert.deepEqual(finishedEvents, [{
    attemptId: realtimeAttemptId,
    success: true,
    cooldownMs: config.success_cooldown_ms,
  }]);
  assert.equal(trigger.state, "cooldown");
  assert.deepEqual(
    triggerTimers.filter((timer) => timer.delay === config.success_cooldown_ms).length,
    1,
  );
  assert.equal(reportCalls.length, 1);

  displayTimers[0].callback();
  assert.equal(expiryDetails.length, 1);
  assert.equal(promo.isVisible, false);
  assert.equal(outcome.state, "advertising");
  assert.equal(trigger.state, "cooldown");
  assert.equal(finishedEvents.length, 1);
  assert.equal(
    triggerTimers.filter((timer) => timer.delay === config.success_cooldown_ms).length,
    1,
  );
  assert.equal(JSON.stringify(sessionResult), sessionSnapshot);

  now = 1;
  trigger.recordFrame({ frame: "cooldown-frame" }, now);
  assert.deepEqual(trigger.acceptTrigger("test"), {
    accepted: false,
    reason: "busy",
    state: "cooldown",
    trigger_source: "test",
    ignoredAtMs: now,
  });

  displayTimers[0].callback();
  assert.equal(expiryDetails.length, 1);
  assert.equal(finishedEvents.length, 1);
  assert.equal(trigger.state, "cooldown");

  const cooldownTimer = triggerTimers.find(
    (timer) => timer.delay === config.success_cooldown_ms,
  );
  cooldownTimer.callback();
  assert.equal(trigger.state, "advertising");

  const appSource = await readFile("client/app.js", "utf8");
  const expirySource = appSource.slice(
    appSource.indexOf("function returnToAdvertisingAfterDisplayExpiry"),
    appSource.indexOf("function mountTriggerConfiguration"),
  );
  assert.match(expirySource, /successfulCooldownAttemptId === null/);
  assert.match(expirySource, /successfulCooldownAttemptId !== detail\.attemptId/);
});

test("configuration loader uses authenticated no-store request and exact response", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token" };
  const calls = [];
  const controller = new PromoDisplayController({
    container: new FakeElement(),
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return {
        ok: true,
        status: 200,
        json: async () => ({
          schema_version: 1,
          result_display_ms: 111,
          success_cooldown_ms: 222,
        }),
      };
    },
    documentImpl: displayDocument(),
  });

  assert.deepEqual(await controller.loadDisplayConfiguration(), {
    schema_version: 1,
    result_display_ms: 111,
    success_cooldown_ms: 222,
  });
  assert.equal(calls[0].url, "/api/promo/display/config");
  assert.equal(calls[0].options.credentials, "same-origin");
  assert.equal(calls[0].options.cache, "no-store");
  assert.equal(calls[0].options.headers.Authorization, "Bearer fixture-display-token");
});

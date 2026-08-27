import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { PromoDisplayController } from "../../client/promo-display.js";

const ORIGIN = "https://central.example.test";

function result(sessionId = "session-077") {
  return {
    session_id: sessionId,
    teasers: Array.from({ length: 4 }, (_, index) => ({
      photo_id: `${sessionId}-photo-${index}`,
      media_url: `${ORIGIN}/api/promo/media/${String(index).padStart(43, "r")}`,
    })),
    n: 4,
    qr_url: `${ORIGIN}/q?ticket=${sessionId}-ticket`,
  };
}

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

function mediaResponse() {
  return {
    ok: true,
    status: 200,
    blob: async () => new Blob(["jpeg"], { type: "image/jpeg" }),
  };
}

test("complete render sends one authenticated confirmed acknowledgement on the same clock", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token" };
  const calls = [];
  const controller = new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: displayDocument(),
    clock: () => 9_421,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return calls.length === 5 ? { ok: true, status: 200 } : mediaResponse();
    },
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: { createObjectURL: () => "blob:fixture-preview" },
  });

  const detail = await controller.showResult({
    attemptId: "attempt-077",
    result: result(),
    timing: { referenceSeriesReadyMonotonicMs: 1_000 },
  });

  assert.equal(detail.qrFullyVisible, true);
  assert.equal(detail.qrFullyVisibleElapsedMs, 8_421);
  assert.deepEqual(detail.acknowledgement, { sent: true, status: 200 });
  assert.equal(calls.length, 5);
  assert.equal(calls[4].url, "/api/promo/sessions/session-077/display");
  assert.equal(calls[4].options.method, "PUT");
  assert.equal(calls[4].options.credentials, "same-origin");
  assert.equal(calls[4].options.cache, "no-store");
  assert.equal(calls[4].options.headers.Authorization, "Bearer fixture-display-token");
  assert.equal(calls[4].options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[4].options.body), {
    schema_version: 1,
    status: "confirmed",
    qr_fully_visible_elapsed_ms: 8_421,
  });
});

test("render failure sends best-effort failed acknowledgement without a QR elapsed value", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token" };
  const calls = [];
  const failures = [];
  const controller = new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: displayDocument(),
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return calls.length === 5 ? { ok: true, status: 200 } : mediaResponse();
    },
    imageFactory: () => ({
      decode: async () => {
        throw new Error("decode failed");
      },
    }),
    urlApi: { createObjectURL: () => "blob:fixture-preview" },
    onFailure: (detail) => failures.push(detail),
  });

  const detail = await controller.showResult({
    attemptId: "attempt-077-failed",
    result: result(),
  });

  assert.equal(detail.state, "advertising");
  assert.equal(detail.reason, "invalid_result");
  assert.deepEqual(detail.acknowledgement, { sent: true, status: 200 });
  assert.equal(calls.length, 5);
  assert.equal(calls[4].url, "/api/promo/sessions/session-077/display");
  assert.deepEqual(JSON.parse(calls[4].options.body), {
    schema_version: 1,
    status: "failed",
  });
  assert.deepEqual(failures, [detail]);
});

test("delayed failed acknowledgement is discarded for a stale render failure", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token" };
  const calls = [];
  const completions = [];
  const failures = [];
  let failNextDecode = true;
  let releaseOldAcknowledgement;
  let resolveOldAcknowledgementStarted;
  const oldAcknowledgementStarted = new Promise((resolve) => {
    resolveOldAcknowledgementStarted = resolve;
  });
  const container = new FakeElement();
  const controller = new PromoDisplayController({
    container,
    origin: ORIGIN,
    documentImpl: displayDocument(),
    clock: () => 9_421,
    fetchImpl: (url, options) => {
      calls.push({ url, options });
      if (!url.endsWith("/display")) return Promise.resolve(mediaResponse());
      if (url.includes("session-stale-failed-old")) {
        resolveOldAcknowledgementStarted();
        return new Promise((resolve) => {
          releaseOldAcknowledgement = resolve;
        });
      }
      return Promise.resolve({ ok: true, status: 200 });
    },
    imageFactory: () => ({
      decode: async () => {
        if (failNextDecode) {
          failNextDecode = false;
          throw new Error("decode failed");
        }
      },
    }),
    urlApi: { createObjectURL: () => "blob:fixture-preview" },
    onComplete: (detail) => completions.push(detail),
    onFailure: (detail) => failures.push(detail),
  });

  const oldResult = controller.showResult({
    attemptId: "attempt-077-stale-failed-old",
    result: result("session-stale-failed-old"),
  });
  await oldAcknowledgementStarted;

  const newDetail = await controller.showResult({
    attemptId: "attempt-077-stale-failed-new",
    result: result("session-stale-failed-new"),
    timing: { referenceSeriesReadyMonotonicMs: 1_000 },
  });
  const newerCard = container.children[0];

  releaseOldAcknowledgement({ ok: true, status: 200 });
  const staleDetail = await oldResult;

  assert.deepEqual(staleDetail, {
    stale: true,
    attemptId: "attempt-077-stale-failed-old",
  });
  assert.deepEqual(completions, [newDetail]);
  assert.deepEqual(failures, []);
  assert.equal(controller.isVisible, true);
  assert.strictEqual(container.children[0], newerCard);
  assert.equal(calls.length, 10);
});

test("acknowledgement HTTP 409 returns to advertising without completion", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token" };
  const calls = [];
  const completions = [];
  const failures = [];
  const controller = new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: displayDocument(),
    clock: () => 9_421,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return calls.length === 5
        ? { ok: false, status: 409 }
        : mediaResponse();
    },
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: { createObjectURL: () => "blob:fixture-preview" },
    onComplete: (detail) => completions.push(detail),
    onFailure: (detail) => failures.push(detail),
  });

  const detail = await controller.showResult({
    attemptId: "attempt-077-ack-conflict",
    result: result(),
    timing: { referenceSeriesReadyMonotonicMs: 1_000 },
  });

  assert.equal(detail.state, "advertising");
  assert.equal(detail.reason, "acknowledgement_failure");
  assert.deepEqual(detail.acknowledgement, {
    sent: false,
    reason: "acknowledgement_failed",
  });
  assert.equal(controller.isVisible, false);
  assert.deepEqual(completions, []);
  assert.deepEqual(failures, [detail]);
  assert.equal(calls.length, 5);
  assert.deepEqual(JSON.parse(calls[4].options.body), {
    schema_version: 1,
    status: "confirmed",
    qr_fully_visible_elapsed_ms: 8_421,
  });
});

test("delayed successful confirmed acknowledgement is discarded for a stale result", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token" };
  const calls = [];
  const completions = [];
  const failures = [];
  let releaseOldAcknowledgement;
  let resolveOldAcknowledgementStarted;
  const oldAcknowledgementStarted = new Promise((resolve) => {
    resolveOldAcknowledgementStarted = resolve;
  });
  const container = new FakeElement();
  const controller = new PromoDisplayController({
    container,
    origin: ORIGIN,
    documentImpl: displayDocument(),
    clock: () => 9_421,
    fetchImpl: (url, options) => {
      calls.push({ url, options });
      if (!url.endsWith("/display")) return Promise.resolve(mediaResponse());
      if (calls.length === 5) {
        resolveOldAcknowledgementStarted();
        return new Promise((resolve) => {
          releaseOldAcknowledgement = resolve;
        });
      }
      return Promise.resolve({ ok: true, status: 200 });
    },
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: { createObjectURL: () => "blob:fixture-preview" },
    onComplete: (detail) => completions.push(detail),
    onFailure: (detail) => failures.push(detail),
  });

  const oldResult = controller.showResult({
    attemptId: "attempt-077-stale-success-old",
    result: result("session-stale-success-old"),
    timing: { referenceSeriesReadyMonotonicMs: 1_000 },
  });
  await oldAcknowledgementStarted;

  const newDetail = await controller.showResult({
    attemptId: "attempt-077-stale-success-new",
    result: result("session-stale-success-new"),
    timing: { referenceSeriesReadyMonotonicMs: 2_000 },
  });
  const newerCard = container.children[0];

  releaseOldAcknowledgement({ ok: true, status: 200 });
  const staleDetail = await oldResult;

  assert.deepEqual(staleDetail, {
    stale: true,
    attemptId: "attempt-077-stale-success-old",
  });
  assert.deepEqual(completions, [newDetail]);
  assert.deepEqual(failures, []);
  assert.equal(controller.isVisible, true);
  assert.strictEqual(container.children[0], newerCard);
  assert.equal(calls.length, 10);
});

test("stale rejected confirmed acknowledgement skips failure and newer result mutation", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token" };
  const calls = [];
  const completions = [];
  const failures = [];
  let rejectOldAcknowledgement;
  let resolveOldAcknowledgementStarted;
  const oldAcknowledgementStarted = new Promise((resolve) => {
    resolveOldAcknowledgementStarted = resolve;
  });
  const container = new FakeElement();
  const controller = new PromoDisplayController({
    container,
    origin: ORIGIN,
    documentImpl: displayDocument(),
    clock: () => 9_421,
    fetchImpl: (url, options) => {
      calls.push({ url, options });
      if (!url.endsWith("/display")) return Promise.resolve(mediaResponse());
      if (url.includes("session-stale-rejected-old")) {
        resolveOldAcknowledgementStarted();
        return new Promise((resolve, reject) => {
          rejectOldAcknowledgement = reject;
        });
      }
      return Promise.resolve({ ok: true, status: 200 });
    },
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: { createObjectURL: () => "blob:fixture-preview" },
    onComplete: (detail) => completions.push(detail),
    onFailure: (detail) => failures.push(detail),
  });

  const oldResult = controller.showResult({
    attemptId: "attempt-077-stale-rejected-old",
    result: result("session-stale-rejected-old"),
    timing: { referenceSeriesReadyMonotonicMs: 1_000 },
  });
  await oldAcknowledgementStarted;

  const newDetail = await controller.showResult({
    attemptId: "attempt-077-stale-rejected-new",
    result: result("session-stale-rejected-new"),
    timing: { referenceSeriesReadyMonotonicMs: 2_000 },
  });
  const newerCard = container.children[0];

  rejectOldAcknowledgement(new Error("network failure"));
  const staleDetail = await oldResult;

  assert.deepEqual(staleDetail, {
    stale: true,
    attemptId: "attempt-077-stale-rejected-old",
  });
  assert.deepEqual(completions, [newDetail]);
  assert.deepEqual(failures, []);
  assert.equal(controller.isVisible, true);
  assert.strictEqual(container.children[0], newerCard);
  assert.equal(calls.length, 10);
});

test("stale aborted confirmed acknowledgement skips failure and keeps the newer result", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token" };
  const calls = [];
  const completions = [];
  const failures = [];
  const scheduled = [];
  const cleared = [];
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  let resolveOldAcknowledgementStarted;
  const oldAcknowledgementStarted = new Promise((resolve) => {
    resolveOldAcknowledgementStarted = resolve;
  });
  const container = new FakeElement();
  globalThis.setTimeout = (callback, delay) => {
    const timer = { callback, delay };
    scheduled.push(timer);
    return timer;
  };
  globalThis.clearTimeout = (timer) => {
    cleared.push(timer);
  };

  try {
    const controller = new PromoDisplayController({
      container,
      origin: ORIGIN,
      documentImpl: displayDocument(),
      clock: () => 9_421,
      fetchImpl: (url, options) => {
        calls.push({ url, options });
        if (!url.endsWith("/display")) return Promise.resolve(mediaResponse());
        if (url.includes("session-stale-aborted-old")) {
          resolveOldAcknowledgementStarted(options.signal);
          return new Promise((resolve, reject) => {
            options.signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
          });
        }
        return Promise.resolve({ ok: true, status: 200 });
      },
      imageFactory: () => ({ decode: async () => {} }),
      urlApi: { createObjectURL: () => "blob:fixture-preview" },
      onComplete: (detail) => completions.push(detail),
      onFailure: (detail) => failures.push(detail),
    });

    const oldResult = controller.showResult({
      attemptId: "attempt-077-stale-aborted-old",
      result: result("session-stale-aborted-old"),
      timing: { referenceSeriesReadyMonotonicMs: 1_000 },
    });
    const oldSignal = await oldAcknowledgementStarted;

    const newDetail = await controller.showResult({
      attemptId: "attempt-077-stale-aborted-new",
      result: result("session-stale-aborted-new"),
      timing: { referenceSeriesReadyMonotonicMs: 2_000 },
    });
    const newerCard = container.children[0];
    const oldTimer = scheduled[0];

    oldTimer.callback();
    const staleDetail = await oldResult;

    assert.equal(oldSignal.aborted, true);
    assert.deepEqual(staleDetail, {
      stale: true,
      attemptId: "attempt-077-stale-aborted-old",
    });
    assert.deepEqual(completions, [newDetail]);
    assert.deepEqual(failures, []);
    assert.equal(controller.isVisible, true);
    assert.strictEqual(container.children[0], newerCard);
    assert.equal(calls.length, 10);
    assert.equal(cleared.includes(oldTimer), true);
    assert.equal(cleared.includes(scheduled[1]), true);
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
  }
});

test("stalled confirmed acknowledgement aborts, clears its timer and returns to advertising", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token" };
  const calls = [];
  const completions = [];
  const failures = [];
  const scheduled = [];
  const cleared = [];
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  let resolveAcknowledgementStart;
  const acknowledgementStarted = new Promise((resolve) => {
    resolveAcknowledgementStart = resolve;
  });
  globalThis.setTimeout = (callback, delay) => {
    const timer = { callback, delay };
    scheduled.push(timer);
    return timer;
  };
  globalThis.clearTimeout = (timer) => {
    cleared.push(timer);
  };

  try {
    const controller = new PromoDisplayController({
      container: new FakeElement(),
      origin: ORIGIN,
      documentImpl: displayDocument(),
      clock: () => 9_421,
      fetchImpl: async (url, options) => {
        calls.push({ url, options });
        if (calls.length < 5) return mediaResponse();
        resolveAcknowledgementStart(options.signal);
        return new Promise((resolve, reject) => {
          options.signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
        });
      },
      imageFactory: () => ({ decode: async () => {} }),
      urlApi: { createObjectURL: () => "blob:fixture-preview" },
      onComplete: (detail) => completions.push(detail),
      onFailure: (detail) => failures.push(detail),
    });

    const pending = controller.showResult({
      attemptId: "attempt-077-ack-timeout",
      result: result(),
      timing: { referenceSeriesReadyMonotonicMs: 1_000 },
    });
    const signal = await acknowledgementStarted;
    assert.equal(calls.length, 5);
    assert.equal(scheduled.length, 1);
    assert.equal(scheduled[0].delay, 5_000);

    scheduled[0].callback();
    const detail = await pending;

    assert.equal(signal.aborted, true);
    assert.equal(detail.state, "advertising");
    assert.equal(detail.reason, "acknowledgement_failure");
    assert.deepEqual(detail.acknowledgement, {
      sent: false,
      reason: "acknowledgement_failed",
    });
    assert.equal(controller.isVisible, false);
    assert.deepEqual(completions, []);
    assert.deepEqual(failures, [detail]);
    assert.deepEqual(cleared, [scheduled[0]]);
    assert.equal(calls.length, 5);
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
  }
});

test("application wiring carries the existing one-clock timing snapshot into Promo render", async () => {
  const app = await readFile("client/app.js", "utf8");
  assert.match(app, /const attemptTimingSnapshots = new Map\(\);/);
  assert.match(app, /attemptTimingSnapshots\.set\(event\.detail\.attemptId, event\.detail\.timing\)/);
  assert.match(app, /timing,\n\s*\}\);/);
});

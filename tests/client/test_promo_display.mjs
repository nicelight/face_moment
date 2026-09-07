import assert from "node:assert/strict";
import test from "node:test";

import {
  PromoDisplayController,
  PROMO_COPY_TEXT,
  qrMatrixForText,
  validatePromoResult,
} from "../../client/promo-display.js";

const ORIGIN = "https://central.example.test";

function result({ teaserCount = 4, duplicate = false } = {}) {
  const teasers = Array.from({ length: teaserCount }, (_, index) => ({
    photo_id: duplicate && index === teaserCount - 1 ? "photo-0" : `photo-${index}`,
    media_url: `${ORIGIN}/api/promo/media/${String(index).padStart(43, "r")}`,
  }));
  return {
    session_id: "session-076",
    teasers,
    n: 8,
    qr_url: `${ORIGIN}/q?ticket=fixture-ticket-076`,
    qr_first_open_expires_at: "2026-08-25T12:00:00Z",
  };
}

class FakeElement {
  constructor() {
    this.children = [];
    this.dataset = {};
    this.classList = { add: (...names) => { this.classes = names; } };
    this.attributes = {};
    this.style = {};
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getBoundingClientRect() {
    return { width: 320, height: 320 };
  }
}

function fakeDocument() {
  return {
    createElement: () => new FakeElement(),
    createElementNS: () => new FakeElement(),
  };
}

function trackedUrlApi() {
  const created = [];
  const revoked = [];
  return {
    created,
    revoked,
    api: {
      createObjectURL: () => {
        const objectUrl = `blob:fixture-preview-${created.length}`;
        created.push(objectUrl);
        return objectUrl;
      },
      revokeObjectURL: (objectUrl) => revoked.push(objectUrl),
    },
  };
}

test("validates exact four unique same-origin teasers and QR", () => {
  const normalized = validatePromoResult(result(), { origin: ORIGIN });
  assert.equal(normalized.teasers.length, 4);
  assert.equal(new Set(normalized.teasers.map((item) => item.photo_id)).size, 4);
  assert.equal(normalized.qr_url, `${ORIGIN}/q?ticket=fixture-ticket-076`);
  assert.equal(PROMO_COPY_TEXT, "Ваши фотографии найдены — откройте по QR-коду");
});

test("rejects partial, duplicate and foreign result shapes", () => {
  assert.throws(
    () => validatePromoResult(result({ teaserCount: 3 }), { origin: ORIGIN }),
    /promo_teasers_must_contain_four/,
  );
  assert.throws(
    () => validatePromoResult(result({ duplicate: true }), { origin: ORIGIN }),
    /promo_teasers_not_unique/,
  );
  const foreign = result();
  foreign.teasers[0].media_url = "https://foreign.example.test/image.jpg";
  assert.throws(
    () => validatePromoResult(foreign, { origin: ORIGIN }),
    /promo_media_url_origin_invalid/,
  );
  const emptyTicket = result();
  emptyTicket.qr_url = `${ORIGIN}/q?ticket=`;
  assert.throws(
    () => validatePromoResult(emptyTicket, { origin: ORIGIN }),
    /promo_qr_url_path_invalid/,
  );
});

test("local QR matrix is high-contrast and uses a target-sized supported version", () => {
  const matrix = qrMatrixForText(`${ORIGIN}/q?ticket=fixture-ticket-076`);
  assert.equal(matrix.length, 33);
  assert.equal(matrix.every((row) => row.length === 33), true);
  assert.equal(matrix.every((row) => row.every((cell) => typeof cell === "boolean")), true);
  assert.equal(matrix[0].slice(0, 7).filter(Boolean).length, 7);
});

test("invalid result returns to advertising without fetching partial media", async () => {
  const container = new FakeElement();
  const failures = [];
  let fetchCalls = 0;
  const controller = new PromoDisplayController({
    container,
    origin: ORIGIN,
    documentImpl: fakeDocument(),
    fetchImpl: async () => {
      fetchCalls += 1;
      throw new Error("must_not_fetch_partial");
    },
    onFailure: (detail) => failures.push(detail),
  });

  const detail = await controller.showResult({
    attemptId: "attempt-076",
    result: result({ teaserCount: 3 }),
  });
  assert.equal(detail.state, "advertising");
  assert.equal(detail.retryEligible, true);
  assert.equal(detail.reason, "invalid_result");
  assert.equal(fetchCalls, 0);
  assert.deepEqual(failures, [detail]);
  assert.equal(controller.isVisible, false);
});

test("complete result renders four decoded previews and a visible local QR", async () => {
  globalThis.localStorage = { getItem: () => "fixture-display-token" };
  const container = new FakeElement();
  const complete = [];
  const controller = new PromoDisplayController({
    container,
    origin: ORIGIN,
    documentImpl: fakeDocument(),
    fetchImpl: async () => ({
      ok: true,
      blob: async () => new Blob(["jpeg-fixture"], { type: "image/jpeg" }),
    }),
    imageFactory: () => ({
      decode: async () => {},
      addEventListener: () => {},
    }),
    urlApi: { createObjectURL: () => "blob:fixture-preview" },
    onComplete: (detail) => complete.push(detail),
  });

  const detail = await controller.showResult({
    attemptId: "attempt-076",
    result: result(),
  });
  assert.equal(detail.state, "result");
  assert.equal(detail.teaserCount, 4);
  assert.equal(detail.qrFullyVisible, true);
  assert.equal(controller.isVisible, true);
  assert.equal(container.children.length, 1);
  assert.deepEqual(complete, [detail]);
});

test("visible previews keep their Blob URLs until expiry, then release all four", async () => {
  const urls = trackedUrlApi();
  let expire;
  const controller = new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: fakeDocument(),
    fetchImpl: async () => ({
      ok: true,
      blob: async () => new Blob(["jpeg-fixture"], { type: "image/jpeg" }),
    }),
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: urls.api,
    setTimeoutImpl: (callback) => {
      expire = callback;
      return "display-expiry";
    },
    clearTimeoutImpl: () => {},
  });

  await controller.showResult({
    attemptId: "attempt-blob-visible",
    result: result(),
    displayConfig: {
      schema_version: 1,
      result_display_ms: 100,
      success_cooldown_ms: 200,
    },
  });
  assert.deepEqual(urls.created, [
    "blob:fixture-preview-0",
    "blob:fixture-preview-1",
    "blob:fixture-preview-2",
    "blob:fixture-preview-3",
  ]);
  assert.deepEqual(urls.revoked, []);

  expire();
  assert.deepEqual(urls.revoked, urls.created);
});

test("render failure releases every preview URL, including late decode completions", async () => {
  const urls = trackedUrlApi();
  const pendingDecodes = [];
  let imageIndex = 0;
  const failures = [];
  const controller = new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: fakeDocument(),
    fetchImpl: async () => ({
      ok: true,
      blob: async () => new Blob(["jpeg-fixture"], { type: "image/jpeg" }),
    }),
    imageFactory: () => {
      const index = imageIndex++;
      return {
        decode: index === 0
          ? async () => { throw new Error("fixture decode"); }
          : () => new Promise((resolve) => pendingDecodes.push(resolve)),
      };
    },
    urlApi: urls.api,
    onFailure: (detail) => failures.push(detail),
  });

  const detail = await controller.showResult({
    attemptId: "attempt-blob-failure",
    result: result(),
  });
  assert.equal(detail.reason, "media_decode_failure");
  assert.deepEqual(urls.revoked, urls.created);
  for (const resolve of pendingDecodes) resolve();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(urls.revoked, urls.created);
  assert.deepEqual(failures, [detail]);
});

test("one hundred result cycles release all four hundred preview URLs", async () => {
  const urls = trackedUrlApi();
  let expire;
  const controller = new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: fakeDocument(),
    fetchImpl: async () => ({
      ok: true,
      blob: async () => new Blob(["jpeg-fixture"], { type: "image/jpeg" }),
    }),
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: urls.api,
    setTimeoutImpl: (callback) => {
      expire = callback;
      return `display-expiry-${urls.created.length}`;
    },
    clearTimeoutImpl: () => {},
  });

  for (let index = 0; index < 100; index += 1) {
    const detail = await controller.showResult({
      attemptId: `attempt-blob-cycle-${index}`,
      result: result(),
      displayConfig: {
        schema_version: 1,
        result_display_ms: 100,
        success_cooldown_ms: 200,
      },
    });
    assert.equal(detail.state, "result");
    expire();
  }

  assert.equal(urls.created.length, 400);
  assert.equal(urls.revoked.length, 400);
  assert.deepEqual(urls.revoked, urls.created);
});

test("superseding a pending render releases only its URLs, preserving the new result", async () => {
  const urls = trackedUrlApi();
  let releaseOldDecode;
  let oldDecodeStarted;
  const oldDecodeReady = new Promise((resolve) => {
    oldDecodeStarted = resolve;
  });
  let imageIndex = 0;
  const container = new FakeElement();
  const controller = new PromoDisplayController({
    container,
    origin: ORIGIN,
    documentImpl: fakeDocument(),
    fetchImpl: async () => ({
      ok: true,
      blob: async () => new Blob(["jpeg-fixture"], { type: "image/jpeg" }),
    }),
    imageFactory: () => {
      const index = imageIndex++;
      if (index !== 0) return { decode: async () => {} };
      return {
        decode: () => {
          oldDecodeStarted();
          return new Promise((resolve) => { releaseOldDecode = resolve; });
        },
      };
    },
    urlApi: urls.api,
  });

  const oldRender = controller.showResult({
    attemptId: "attempt-blob-old",
    result: result(),
  });
  await oldDecodeReady;
  assert.deepEqual(urls.created, [
    "blob:fixture-preview-0",
    "blob:fixture-preview-1",
    "blob:fixture-preview-2",
    "blob:fixture-preview-3",
  ]);

  const newRender = controller.showResult({
    attemptId: "attempt-blob-new",
    result: result(),
  });
  const newDetail = await newRender;
  assert.equal(newDetail.state, "result");
  assert.deepEqual(urls.created, [
    "blob:fixture-preview-0",
    "blob:fixture-preview-1",
    "blob:fixture-preview-2",
    "blob:fixture-preview-3",
    "blob:fixture-preview-4",
    "blob:fixture-preview-5",
    "blob:fixture-preview-6",
    "blob:fixture-preview-7",
  ]);
  assert.deepEqual(urls.revoked, urls.created.slice(0, 4));

  releaseOldDecode();
  await oldRender;
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(urls.revoked, urls.created.slice(0, 4));
  assert.equal(controller.isVisible, true);
  assert.equal(container.children.length, 1);
});

test("preview timeout releases URLs already created by completed siblings", async () => {
  const urls = trackedUrlApi();
  let releaseStalledFetch;
  let mediaCalls = 0;
  const controller = new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: fakeDocument(),
    loadingDeadlineMs: 10,
    fetchImpl: (url) => {
      if (String(url).includes("/api/promo/media/") && mediaCalls++ === 0) {
        return new Promise((resolve) => { releaseStalledFetch = resolve; });
      }
      return Promise.resolve({
        ok: true,
        blob: async () => new Blob(["jpeg-fixture"], { type: "image/jpeg" }),
      });
    },
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: urls.api,
  });

  const detail = await controller.showResult({
    attemptId: "attempt-blob-timeout",
    result: result(),
  });
  assert.equal(detail.reason, "media_failure");
  assert.equal(urls.created.length, 3);
  assert.deepEqual(urls.revoked, urls.created);

  releaseStalledFetch({
    ok: true,
    blob: async () => new Blob(["late-jpeg"], { type: "image/jpeg" }),
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(urls.revoked, urls.created);
});

test("configuration fetch and JSON each settle at the bounded deadline", async () => {
  for (const response of [
    new Promise(() => {}),
    Promise.resolve({
      ok: true,
      status: 200,
      json: () => new Promise(() => {}),
    }),
  ]) {
    let signal;
    const controller = new PromoDisplayController({
      container: new FakeElement(),
      origin: ORIGIN,
      documentImpl: fakeDocument(),
      loadingDeadlineMs: 10,
      fetchImpl: (_url, options) => {
        signal = options.signal;
        return response;
      },
    });

    await assert.rejects(
      controller.loadDisplayConfiguration({ attemptId: "attempt-config-deadline" }),
      /promo_display_configuration_timeout/,
    );
    assert.equal(signal.aborted, true);
  }
});

test("one stalled preview fails the complete preparation and cancels transport", async () => {
  let stalledSignal;
  let mediaCalls = 0;
  const failures = [];
  const controller = new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: fakeDocument(),
    loadingDeadlineMs: 10,
    fetchImpl: (url, options) => {
      if (String(url).includes("/api/promo/media/") && mediaCalls++ === 0) {
        stalledSignal = options.signal;
        return new Promise(() => {});
      }
      if (String(url).includes("/api/promo/media/")) {
        return Promise.resolve({
          ok: true,
          blob: async () => new Blob(["jpeg-fixture"], { type: "image/jpeg" }),
        });
      }
      return Promise.resolve({ ok: true, status: 200 });
    },
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: { createObjectURL: () => "blob:fixture-preview" },
    onFailure: (detail) => failures.push(detail),
  });

  const detail = await controller.showResult({
    attemptId: "attempt-preview-deadline",
    result: result(),
  });

  assert.equal(detail.state, "advertising");
  assert.equal(detail.reason, "media_failure");
  assert.equal(stalledSignal.aborted, true);
  assert.deepEqual(failures, [detail]);
  assert.equal(controller.isVisible, false);
});

test("a stalled decode is bounded and an actual decode error is normalized", async () => {
  let decodeCalls = 0;
  const stalledFailures = [];
  const controller = new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: fakeDocument(),
    loadingDeadlineMs: 10,
    fetchImpl: async (url) => {
      if (String(url).includes("/api/promo/media/")) {
        return {
          ok: true,
          blob: async () => new Blob(["jpeg-fixture"], { type: "image/jpeg" }),
        };
      }
      return { ok: true, status: 200 };
    },
    imageFactory: () => ({
      decode: () => {
        decodeCalls += 1;
        return new Promise(() => {});
      },
    }),
    urlApi: { createObjectURL: () => "blob:fixture-preview" },
    onFailure: (detail) => stalledFailures.push(detail),
  });

  const stalled = await controller.showResult({
    attemptId: "attempt-decode-deadline",
    result: result(),
  });
  assert.equal(stalled.reason, "media_failure");
  assert.equal(decodeCalls, 4);
  assert.deepEqual(stalledFailures, [stalled]);

  const failures = [];
  const failing = new PromoDisplayController({
    container: new FakeElement(),
    origin: ORIGIN,
    documentImpl: fakeDocument(),
    loadingDeadlineMs: 10,
    fetchImpl: async (url) => String(url).includes("/api/promo/media/")
      ? {
          ok: true,
          blob: async () => new Blob(["jpeg-fixture"], { type: "image/jpeg" }),
        }
      : { ok: true, status: 200 },
    imageFactory: () => ({ decode: async () => { throw new Error("fixture decode"); } }),
    urlApi: { createObjectURL: () => "blob:fixture-preview" },
    onFailure: (detail) => failures.push(detail),
  });

  const decoded = await failing.showResult({
    attemptId: "attempt-decode-failure",
    result: result(),
  });
  assert.equal(decoded.reason, "media_decode_failure");
  assert.deepEqual(failures, [decoded]);
});

test("late completion after a deadline cannot replace the next usable result", async () => {
  let releaseStalledPreview;
  let firstAttempt = true;
  let mediaCalls = 0;
  const container = new FakeElement();
  const completions = [];
  const controller = new PromoDisplayController({
    container,
    origin: ORIGIN,
    documentImpl: fakeDocument(),
    loadingDeadlineMs: 10,
    fetchImpl: (url) => {
      if (String(url).includes("/api/promo/media/")) {
        if (firstAttempt && mediaCalls++ === 0) {
          return new Promise((resolve) => {
            releaseStalledPreview = () => resolve({
              ok: true,
              blob: async () => new Blob(["late-jpeg"], { type: "image/jpeg" }),
            });
          });
        }
        return Promise.resolve({
          ok: true,
          blob: async () => new Blob(["jpeg-fixture"], { type: "image/jpeg" }),
        });
      }
      return Promise.resolve({ ok: true, status: 200 });
    },
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: { createObjectURL: () => "blob:fixture-preview" },
    onComplete: (detail) => completions.push(detail),
  });

  const failed = await controller.showResult({
    attemptId: "attempt-late-old",
    result: result(),
  });
  assert.equal(failed.reason, "media_failure");
  firstAttempt = false;
  const next = await controller.showResult({
    attemptId: "attempt-late-new",
    result: result(),
  });
  const nextCard = container.children[0];
  releaseStalledPreview();
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(next.state, "result");
  assert.deepEqual(completions, [next]);
  assert.strictEqual(container.children[0], nextCard);
  assert.equal(controller.isVisible, true);
});

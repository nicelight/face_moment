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

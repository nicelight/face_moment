import assert from "node:assert/strict";
import test from "node:test";

import { animatePromoEntrance } from "../../client/promo-entrance.js";

function entranceElement(name, animations) {
  return {
    name,
    getBoundingClientRect: () => ({ left: 100, top: 100, right: 300, bottom: 300 }),
    animate: (_frames, options) => {
      animations.push({ name, options });
      return { finished: Promise.resolve(), cancel() {} };
    },
  };
}

test("Promo paper photos enter at half speed before the QR", async () => {
  const animations = [];
  const photos = Array.from({ length: 4 }, (_, index) => entranceElement(`photo-${index}`, animations));
  const qr = entranceElement("qr", animations);
  const text = entranceElement("text", animations);
  const card = {
    classList: { add() {} },
    querySelectorAll: (selector) => selector === ".promo-photo-card" ? photos : [],
    querySelector: (selector) => ({
      ".promo-qr-panel": qr,
      ".promo-copy h2": text,
    })[selector] ?? null,
  };
  const previous = {
    window: globalThis.window,
    getComputedStyle: globalThis.getComputedStyle,
    matchMedia: globalThis.matchMedia,
  };

  globalThis.window = { innerWidth: 1920, innerHeight: 1080 };
  globalThis.getComputedStyle = () => ({ boxShadow: "none" });
  globalThis.matchMedia = () => ({ matches: false });
  try {
    await animatePromoEntrance(card);
  } finally {
    globalThis.window = previous.window;
    globalThis.getComputedStyle = previous.getComputedStyle;
    globalThis.matchMedia = previous.matchMedia;
  }

  const photoAnimations = animations.filter(({ name }) => name.startsWith("photo-"));
  assert.deepEqual(photoAnimations.map(({ options }) => options.delay), [0, 540, 1080, 1620]);
  assert.deepEqual(photoAnimations.map(({ options }) => options.duration), [2700, 2700, 2700, 2700]);
  assert.equal(animations.find(({ name }) => name === "qr").options.delay, 4320);
});

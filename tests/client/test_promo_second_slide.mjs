import assert from 'node:assert/strict';
import test from 'node:test';
import { PromoDisplayController } from '../../client/promo-display.js';

const origin = 'https://second-slide.test';
const settingsKey = 'face-moment.promo-second-slide';
class Element {
  constructor(tag = 'div') { this.tag = tag; this.children = []; this.dataset = {}; this.style = {}; this.classList = { add() {} }; this.animations = []; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute() {}
  getBoundingClientRect() { return { width: 320, height: 320 }; }
  animate(frames, options) { const animation = { frames, options, cancel() {} }; this.animations.push(animation); return animation; }
  getAnimations() { return this.animations; }
}
function result(gallery = true) {
  const photos = Array.from({ length: 7 }, (_, i) => ({ photo_id: `p${i}`, kind: i === 6 ? 'common' : 'matched', media_url: `${origin}/api/promo/sessions/s1/gallery/media/p${i}` }));
  return { session_id: 's1', n: 6, qr_url: `${origin}/q?ticket=fixture`,
    teasers: photos.slice(0, 4).map(p => ({ photo_id: p.photo_id, media_url: p.media_url.replace('/gallery', '') })),
    ...(gallery ? { gallery_photos: photos } : {}) };
}
function fixture({ enabled = true, reduced = false } = {}) {
  const storage = new Map([[settingsKey, JSON.stringify({ enabled, seconds: 3 })], ['face-moment.display-client-token', 'test-token']]);
  globalThis.localStorage = { getItem: k => storage.get(k) ?? null, setItem: (k,v) => storage.set(k,v) };
  globalThis.matchMedia = () => ({ matches: reduced });
  const timers = [], calls = [], revoked = [], completions = [], expired = [], pending = new Map();
  let presented = false, objectCount = 0;
  const container = new Element();
  const controller = new PromoDisplayController({ container, origin,
    documentImpl: { createElement: tag => new Element(tag), createElementNS: (_,tag) => new Element(tag) },
    imageFactory: () => ({ decode: async () => {} }),
    urlApi: { createObjectURL: () => `blob:${++objectCount}`, revokeObjectURL: value => revoked.push(value) },
    clock: () => 100,
    onPresent: () => { presented = true; }, onComplete: detail => completions.push(detail), onExpired: detail => expired.push(detail),
    setTimeoutImpl: (callback, delay) => { const t = { callback, delay }; timers.push(t); return t; },
    clearTimeoutImpl: timer => { timer.cleared = true; },
    fetchImpl: async (url, options) => {
      calls.push({ url, method: options.method ?? 'GET', presented });
      if (url.includes('/gallery/')) return new Promise(resolve => pending.set(url.split('/').at(-1), resolve));
      return response();
    },
  });
  const show = () => controller.showResult({ attemptId: 'a1', result: result(), timing: { referenceSeriesReadyMonotonicMs: 0 }, displayConfig: { schema_version: 1, result_display_ms: 1000, success_cooldown_ms: 9000 } });
  return { controller, container, timers, calls, pending, completions, expired, revoked, show, storage };
}
const response = (ok = true) => ({ ok, status: ok ? 200 : 404, blob: async () => new Blob(['JPEG']) });
const flush = async () => { for(let i=0;i<20;i++) await Promise.resolve(); };

test('enabled first result transitions on time before extras and late fills fixed cells', async () => {
  const f = fixture();
  await f.show();
  assert.equal(f.calls.filter(c => c.method === 'PUT').length, 1);
  assert.equal(f.timers[0].delay, 1000);
  await f.timers[0].callback();
  assert.match(f.controller.renderedCard?.className ?? "", /promo-gallery/, 'enabled result must transition to the photo-only second grid');
  assert.equal(f.controller.renderedCard.children.length, 12);
  f.controller.dispose();
});

test('background requests start after full presentation; transition and second duration are distinct', async () => {
  const f = fixture(); await f.show(); await flush();
  assert.equal(f.calls.filter(c => c.url.includes('/gallery/')).length, 3);
  assert.ok(f.calls.filter(c => c.url.includes('/gallery/')).every(c => c.presented));
  assert.equal(f.completions[0].qrFullyVisible, true);
  const first = f.controller.renderedCard;
  await f.timers[0].callback();
  const second = f.controller.renderedCard;
  assert.equal(f.container.children.length, 2);
  assert.equal(f.timers[1].delay, 2000);
  assert.deepEqual(second.animations[0].frames, [{ opacity: 0 }, { opacity: 1 }]);
  assert.deepEqual(first.animations[0].frames, [{ opacity: 1 }, { opacity: 0 }]);
  assert.equal(second.children.filter(c => c.children.length).length, 4);
  f.pending.get('p4')(response()); f.pending.get('p5')(response(false)); await flush();
  assert.equal(second.children[4].children.length, 1);
  assert.equal(second.children[5].children.length, 0);
  await f.timers[1].callback();
  assert.deepEqual(f.container.children, [second]);
  assert.equal(f.timers[2].delay, 3000);
  assert.equal(f.expired.length, 0);
  await f.timers[2].callback();
  assert.equal(f.expired.length, 1);
  f.pending.get('p6')(response()); await flush();
  assert.equal(second.children[6].children.length, 0);
  assert.equal(f.container.children.length, 0);
  assert.equal(new Set(f.revoked).size, 5);
  assert.equal(f.calls.filter(c => c.method === 'PUT').length, 1);
  f.controller.dispose();
});

test('reduced motion transitions immediately; replay begins at the grid without search QR or ACK', async () => {
  const f = fixture({ reduced: true }); await f.show(); await flush();
  await f.timers[0].callback();
  assert.equal(f.timers[1].delay, 3000);
  assert.equal(f.container.children.length, 1);
  assert.equal(f.controller.renderedCard.animations.length, 0);
  await f.timers[1].callback();
  const before = f.calls.length;
  await f.controller.replayLastResult(); await flush();
  assert.match(f.controller.renderedCard.className, /promo-gallery/);
  assert.equal(f.controller.renderedCard.children.length, 12);
  assert.equal(f.timers[2].delay, 3000);
  assert.equal(f.completions.at(-1).replay, true);
  assert.equal(f.completions.at(-1).qrFullyVisible, false);
  assert.equal(f.calls.slice(before).length, 7);
  assert.ok(f.calls.slice(before).every(c => c.method === 'GET' && c.url.includes('/gallery/')));
  f.controller.dispose(); await flush();
  assert.equal(f.timers[2].cleared, true);
  assert.equal(f.container.children.length, 0);
});

test('disabled or legacy result preserves first-only behavior; replacement invalidates late cells and transition', async () => {
  for (const legacy of [false, true]) {
    const f = fixture({ enabled: legacy });
    await f.controller.showResult({ attemptId: 'old', result: result(!legacy), displayConfig: { schema_version: 1, result_display_ms: 1000, success_cooldown_ms: 3000 } });
    assert.equal(f.calls.length, 4);
    await f.timers[0].callback();
    assert.equal(f.expired.length, 1); assert.equal(f.container.children.length, 0);
    await f.controller.replayLastResult();
    assert.ok(!f.controller.renderedCard.className.includes('promo-gallery'));
    f.controller.dispose();
  }
  const f = fixture(); await f.show(); await f.timers[0].callback();
  const obsolete = f.controller.renderedCard; const oldTimer = f.timers[1];
  const oldLoad = f.pending.get('p4');
  await f.show(); oldLoad(response()); await flush();
  await oldTimer.callback();
  assert.equal(oldTimer.cleared, true);
  assert.equal(obsolete.children[4].children.length, 0);
  assert.ok(!f.controller.renderedCard.className.includes('promo-gallery'));
  f.controller.dispose(); await flush();
  assert.equal(f.container.children.length, 0);
});

test('second-slide settings require positive whole seconds, persist and default off safely', async () => {
  const { readPromoSecondSlide, savePromoSecondSlide } = await import('../../client/promo-display-preferences.js');
  const f = fixture({ enabled: false });
  assert.equal(readPromoSecondSlide().enabled, false);
  for (const value of ['', null, 0, -1, 1.2, 'bad']) assert.throws(() => savePromoSecondSlide(true, value));
  assert.deepEqual(savePromoSecondSlide(true, '9'), { enabled: true, seconds: 9 });
  assert.deepEqual(readPromoSecondSlide(), { enabled: true, seconds: 9 });
  assert.deepEqual(savePromoSecondSlide(false, ''), { enabled: false, seconds: null });
  f.storage.set(settingsKey, 'corrupt'); assert.equal(readPromoSecondSlide().enabled, false);
  f.controller.dispose();
});

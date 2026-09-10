import assert from 'node:assert/strict';
import { PROMO_LAYOUT_KEY, PROMO_PARTS, readPromoLayout, validPromoLayout } from '../../client/promo-layout.js';
const layout = { version: 1, textScale: 1, parts: Object.fromEntries(PROMO_PARTS.map(key => [key, { x: 50, y: 50, w: 30, h: 30, angle: -12 }])) };
assert.equal(validPromoLayout(layout), true);
for (const bad of [null, {}, { ...layout, version: 2 }, { ...layout, textScale: 100 }, { ...layout, parts: {} }]) {
  assert.ok(!validPromoLayout(bad));
}
for (const value of [NaN, Infinity, -10, 201]) {
  assert.ok(!validPromoLayout({ ...layout, parts: { ...layout.parts, qr: { ...layout.parts.qr, w: value } } }));
}
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem(key) { assert.equal(key, PROMO_LAYOUT_KEY); return JSON.stringify(layout); } } });
assert.deepEqual(readPromoLayout(), layout);
globalThis.localStorage.getItem = () => '{broken';
assert.equal(readPromoLayout(), null);
Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('denied'); } });
assert.equal(readPromoLayout(), null);
delete globalThis.localStorage;
console.log('Promo layout validation and denied/corrupt storage fallback passed');

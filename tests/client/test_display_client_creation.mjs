import assert from 'node:assert/strict';
import { test } from 'node:test';
globalThis.document = { querySelectorAll: () => [], cookie: 'fm_staff_csrf=test' };
const { mountDisplayCreate } = await import('../../client/display-client-create.js');
const event = { preventDefault() {} };
function el(value = '') { return { value, listeners: {}, focus() {}, setAttribute() {},
  addEventListener(type, fn) { this.listeners[type] = fn; } }; }
function fixture() {
  const name = el(' Экран '), venue = el(''), opener = el(), cancel = el(), submit = el(), status = {};
  const section = { hidden: true };
  globalThis.document.querySelector = () => opener;
  const form = { listeners: {}, closest: () => section, reset() { name.value = venue.value = ''; },
    elements: { namedItem: key => key === 'name' ? name : venue },
    querySelector: key => ({ '[data-cancel-display-create]': cancel, 'button[type="submit"]': submit, '[role="status"]': status })[key],
    addEventListener(type, fn) { this.listeners[type] = fn; } };
  mountDisplayCreate(form);
  return { form, name, venue, opener, cancel, submit, status, section };
}
test('venue must be selected; create sends chosen venue and CSRF then reloads', async () => {
  const f = fixture(); let reloads = 0;
  globalThis.window = { location: { reload() { reloads++; } } };
  f.opener.listeners.click(); assert.equal(f.section.hidden, false);
  await f.form.listeners.submit(event); assert.match(f.status.textContent, /выберите площадку/);
  f.venue.value = 'venue-b';
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/serving/display-clients');
    assert.equal(options.headers['X-CSRF-Token'], 'test');
    assert.deepEqual(JSON.parse(options.body), { name: 'Экран', spa_id: 'venue-b' });
    return { ok: true };
  };
  await f.form.listeners.submit(event); assert.equal(reloads, 1);
  f.cancel.listeners.click(); assert.equal(f.section.hidden, true); assert.equal(f.venue.value, '');
});
test('pending creation cannot be resubmitted and rejected venue keeps draft', async () => {
  const f = fixture(); f.venue.value = 'venue-b'; let finish, calls = 0;
  globalThis.fetch = () => { calls++; return new Promise(resolve => { finish = resolve; }); };
  const first = f.form.listeners.submit(event);
  await f.form.listeners.submit(event); assert.equal(calls, 1);
  finish({ ok: false, status: 409 }); await first;
  assert.match(f.status.textContent, /отключена/); assert.equal(f.venue.value, 'venue-b');
  assert.equal(f.submit.disabled, false);
});

import assert from 'node:assert/strict';
import { test } from 'node:test';

globalThis.document = { querySelectorAll: () => [], cookie: 'fm_staff_csrf=test' };
const { mountSpaCreate } = await import('../../client/spa-search-settings.js');
const event = { preventDefault() {} };
function element(value = '') {
  return { value, listeners: {}, disabled: false, focus() {}, setAttribute() {},
    addEventListener(type, fn) { this.listeners[type] = fn; } };
}
function fixture() {
  const opener = element(), cancel = element(), submit = element(), status = {};
  const is_free = { checked: false };
  const name = element('  Новая  '), timezone = element('Europe/Moscow'), section = { hidden: true };
  globalThis.document.querySelector = () => opener;
  const form = { listeners: {}, closest: () => section, reset() { name.value = ''; },
    elements: { namedItem: key => ({ name, timezone, is_free })[key] },
    querySelector: key => ({ '[data-cancel-spa-create]': cancel, 'button[type="submit"]': submit, '[role="status"]': status })[key],
    addEventListener(type, fn) { this.listeners[type] = fn; } };
  mountSpaCreate(form);
  return { form, opener, cancel, submit, status, section, is_free };
}

test('creation opens, cancels and sends explicit paid mode/name/timezone with CSRF', async () => {
  const f = fixture();
  f.opener.listeners.click(); assert.equal(f.section.hidden, false);
  f.cancel.listeners.click(); assert.equal(f.section.hidden, true);
  const g = fixture();
  let reloaded = false;
  globalThis.window = { location: { reload() { reloaded = true; } } };
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/serving/spas'); assert.equal(options.method, 'POST');
    assert.equal(options.headers['X-CSRF-Token'], 'test');
    assert.deepEqual(JSON.parse(options.body), { name: 'Новая', timezone: 'Europe/Moscow', is_free: false });
    return { ok: true };
  };
  await g.form.listeners.submit(event);
  assert.equal(reloaded, true);
});

test('pending submit is not duplicated and failure leaves form usable', async () => {
  const f = fixture(); let finish, calls = 0;
  globalThis.fetch = () => { calls++; return new Promise(resolve => { finish = resolve; }); };
  const first = f.form.listeners.submit(event);
  await f.form.listeners.submit(event);
  assert.equal(calls, 1); assert.equal(f.cancel.disabled, true);
  finish({ ok: false, status: 409 }); await first;
  assert.match(f.status.textContent, /Общая модель недоступна/);
  assert.equal(f.submit.disabled, false);
});

test('invalid initial model gives an actionable error and permits retry', async () => {
  const f = fixture();
  globalThis.fetch = async () => ({ ok: false, status: 503 });
  await f.form.listeners.submit(event);
  assert.match(f.status.textContent, /SFace.*SFACE_.*Площадка не создана/);
  assert.equal(f.submit.disabled, false);
  assert.equal(f.cancel.disabled, false);
});

test('free creation cancel/close emits no mutation; confirm sends strict true', async () => {
 const f=fixture(); f.is_free.checked=true; let calls=0, reload=false;
 globalThis.window={confirm:()=>false,location:{reload(){reload=true;}}};
 globalThis.fetch=async(url,options)=>{calls++;assert.equal(JSON.parse(options.body).is_free,true);return {ok:true};};
 await f.form.listeners.submit(event);assert.equal(calls,0);assert.equal(f.submit.disabled,false);
 window.confirm=()=>true;await f.form.listeners.submit(event);assert.equal(calls,1);assert.equal(reload,true);
});

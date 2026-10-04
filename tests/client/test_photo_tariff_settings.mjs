import assert from 'node:assert/strict';
import { test } from 'node:test';
globalThis.document = { querySelectorAll: () => [], cookie: 'fm_staff_csrf=fixture' };
const { mountPhotoTariff } = await import('../../client/photo-tariff-settings.js');
const names = ['base_kopecks', 'd1', 'd2', 'd3'];
const canonical = { base_kopecks: 10000, d1: '0.8', d2: '0.6', d3: '0.4' };
const event = { preventDefault() {} };
function fixture() {
  const fields = Object.fromEntries(names.map(name => [name, { value: '', disabled: true }]));
  const button = { disabled: true }, status = {}, listeners = {};
  return { fields, button, status, listeners,
    elements: { namedItem: name => fields[name] },
    querySelector: selector => selector === '[role="status"]' ? status : button,
    addEventListener: (name, fn) => { listeners[name] = fn; } };
}
const response = (values = canonical) => ({ ok: true, json: async () => values });
test('server canonical values, credentials/CSRF and canonical save response', async () => {
  globalThis.fetch = async () => response();
  const form = fixture(); await mountPhotoTariff(form);
  assert.equal(form.fields.base_kopecks.value, '10000');
  form.fields.base_kopecks.value = '20000';
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/serving/photo-tariff');
    assert.equal(options.credentials, 'same-origin'); assert.equal(options.cache, 'no-store');
    assert.equal(options.headers['X-CSRF-Token'], 'fixture');
    assert.deepEqual(JSON.parse(options.body), { ...canonical, base_kopecks: 20000 });
    return response({ ...canonical, base_kopecks: 20000, d1: '0.800' });
  };
  await form.listeners.submit(event);
  assert.equal(form.fields.base_kopecks.value, '20000');
  assert.equal(form.fields.d1.value, '0.800');
  assert.match(form.status.textContent, /Тариф сохранён/); assert.equal(form.button.disabled, false);
});
test('missing tariff permits explicit provision without fabricated defaults; failed read blocks save', async () => {
  globalThis.fetch = async () => ({ ok: false, status: 503 });
  const form = fixture(); await mountPhotoTariff(form);
  assert.match(form.status.textContent, /ещё не задан/); assert.equal(form.button.disabled, false);
  for (const input of Object.values(form.fields)) assert.equal(input.value, '');
  globalThis.fetch = async () => ({ ok: false, status: 403 });
  const denied = fixture(); await mountPhotoTariff(denied); assert.equal(denied.button.disabled, true);
});
test('invalid drafts never call API', async () => {
  for (const changes of [{ base_kopecks: '' }, { base_kopecks: '1.5' }, { d1: 'NaN' }, { d3: '0' }, { d2: '0.9' }]) {
    globalThis.fetch = async () => response();
    const form = fixture(); await mountPhotoTariff(form);
    for (const [key, value] of Object.entries(changes)) form.fields[key].value = value;
    globalThis.fetch = async () => { assert.fail('invalid draft must not be sent'); };
    await form.listeners.submit(event);
    assert.match(form.status.textContent, /1 ≥ d1 ≥ d2 ≥ d3 > 0/);
  }
});
test('API validation/access and network failures are explained without accepting draft as saved', async () => {
  for (const [failure, message] of [[422, /отклонён сервером/], [403, /Нет прав/], [401, /Войдите/], [0, /соединение/]]) {
    globalThis.fetch = async () => response();
    const form = fixture(); await mountPhotoTariff(form);
    form.fields.base_kopecks.value = '30000';
    globalThis.fetch = async () => { if (!failure) throw new Error('network'); return { ok: false, status: failure }; };
    await form.listeners.submit(event);
    assert.match(form.status.textContent, message); assert.equal(form.button.disabled, false);
    globalThis.fetch = async () => response();
    const reload = fixture(); await mountPhotoTariff(reload);
    assert.equal(reload.fields.base_kopecks.value, '10000');
  }
});

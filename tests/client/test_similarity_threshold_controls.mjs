import assert from 'node:assert/strict';
import { test } from 'node:test';

globalThis.document = { querySelectorAll: () => [], cookie: 'fm_staff_csrf=test' };
const { mountSimilarityThreshold } = await import('../../client/spa-search-settings.js');
const event = { preventDefault() {} };
const current = { spa_id: 'venue-a', pipeline_code: 'opencv_sface', pipeline_revision_id: 'revision-a',
  settings_revision: 7, threshold: 0.45 };
function fixture() {
  const input = { value: '', disabled: true };
  const toggle = { checked: false, disabled: true, listeners: {},
    addEventListener(type, fn) { this.listeners[type] = fn; } };
  const button = { disabled: true }, status = {}, model = {};
  return { dataset: { spaId: 'venue-a' }, input, toggle, button, status, model, listeners: {},
    elements: { namedItem: name => name === 'edit_threshold' ? toggle : input },
    querySelector: selector => ({ 'button[type="submit"]': button, '[role="status"]': status,
      '[data-serving-model]': model })[selector],
    addEventListener(type, fn) { this.listeners[type] = fn; } };
}

test('current model, explicit snapshot save, reopen, and stale form block', async () => {
  globalThis.fetch = async () => ({ ok: true, json: async () => current });
  const form = fixture();
  await mountSimilarityThreshold(form);
  assert.equal(form.model.textContent, 'opencv_sface');
  assert.equal(form.input.value, '0.45');
  assert.equal(form.button.disabled, true);
  form.toggle.checked = true; form.toggle.listeners.change();
  form.input.value = '0.9';
  form.toggle.checked = false; form.toggle.listeners.change();
  assert.equal(form.input.value, '0.45');
  form.toggle.checked = true; form.toggle.listeners.change();
  form.input.value = '0.6';
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/serving/spas/venue-a/similarity-threshold');
    assert.equal(options.headers['X-CSRF-Token'], 'test');
    assert.deepEqual(JSON.parse(options.body), { threshold: 0.6, pipeline_revision_id: 'revision-a', settings_revision: 7 });
    return { ok: true, json: async () => ({ ...current, threshold: 0.6, settings_revision: 8 }) };
  };
  await form.listeners.submit(event);
  assert.equal(form.input.value, '0.6');
  assert.match(form.status.textContent, /сохранён/);
  assert.equal(form.toggle.checked, false);
  assert.equal(form.input.disabled, true);
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ ...current, threshold: 0.6, settings_revision: 8 }) });
  const reopened = fixture();
  await mountSimilarityThreshold(reopened);
  assert.equal(reopened.input.value, '0.6');
  globalThis.fetch = async () => ({ ok: false, status: 409 });
  form.toggle.checked = true; form.toggle.listeners.change();
  await form.listeners.submit(event);
  assert.equal(form.button.disabled, true);
  assert.match(form.status.textContent, /Обновите страницу/);
  assert.equal(form.toggle.disabled, true);
  assert.equal(reopened.button.disabled, true);
  assert.equal(reopened.toggle.disabled, false);
});

test('missing settings have no invented threshold; blank and nonfinite inputs cannot save', async () => {
  globalThis.fetch = async () => ({ ok: false, status: 503 });
  const missing = fixture();
  await mountSimilarityThreshold(missing);
  assert.equal(missing.input.value, '');
  assert.equal(missing.button.disabled, true);
  assert.equal(missing.toggle.disabled, true);
  assert.match(missing.status.textContent, /Не удалось загрузить/);
  globalThis.fetch = async () => ({ ok: true, json: async () => current });
  const form = fixture();
  await mountSimilarityThreshold(form);
  form.toggle.checked = true; form.toggle.listeners.change();
  globalThis.fetch = async () => { throw new Error('must not fetch'); };
  for (const value of ['', 'NaN', 'Infinity', '1.1', '-1.1']) {
    form.input.value = value;
    await form.listeners.submit(event);
    assert.match(form.status.textContent, /Введите число/);
  }
});

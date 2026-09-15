import assert from 'node:assert/strict';
import { test } from 'node:test';

globalThis.document = { querySelectorAll: () => [], cookie: 'fm_staff_csrf=test' };
globalThis.window = { StaffDateTime: { dateValue: input => input.value, setDate: (input, value) => { input.value = value; } } };
const { mountDetectorThreshold, mountSearchDates } = await import('../../client/spa-search-settings.js');

function control(value = '') {
  return { value, checked: false, disabled: false, hidden: false, textContent: '',
    listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; } };
}
function formFixture() {
  const fields = { edit_threshold: control(), threshold: control('0.9'),
    search_today: control(), date_from: control('2026-09-08'), date_to: control('2026-09-20') };
  const nodes = { 'button[type="submit"]': control(), '[role="status"]': control(),
    '[data-manual-dates]': control(), '[data-manual-search]': control() };
  return { ...control(), dataset: { spaId: 'venue-a', detector: 'photo_yunet' }, fields, nodes,
    elements: { namedItem: name => fields[name] }, querySelector: selector => nodes[selector] };
}
const event = { preventDefault() {} };

test('threshold edit cancellation, save, failed save and independent venue controls', async () => {
  const form = formFixture(), other = formFixture();
  mountDetectorThreshold(form); mountDetectorThreshold(other);
  const toggle = form.fields.edit_threshold, input = form.fields.threshold;
  assert.equal(input.disabled, true);
  toggle.checked = true; toggle.listeners.change();
  input.value = '0.72'; toggle.checked = false; toggle.listeners.change();
  assert.equal(input.value, '0.9'); assert.equal(input.disabled, true);
  toggle.checked = true; toggle.listeners.change(); input.value = '0.72';
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/serving/spas/venue-a/detector-thresholds/photo_yunet');
    assert.equal(options.body, '{"threshold":0.72}');
    return { ok: true, json: async () => ({ threshold: 0.72 }) };
  };
  await form.listeners.submit(event);
  assert.equal(toggle.checked, false); assert.equal(input.disabled, true);
  assert.equal(input.value, '0.72'); assert.equal(other.fields.threshold.value, '0.9');
  toggle.checked = true; toggle.listeners.change(); input.value = '0.6';
  globalThis.fetch = async () => ({ ok: false });
  await form.listeners.submit(event);
  assert.equal(toggle.checked, true); assert.equal(input.disabled, false); assert.equal(input.value, '0.6');
  toggle.checked = false; toggle.listeners.change(); assert.equal(input.value, '0.72');
});

test('today hides dates and autosaves; failed autosave restores saved mode', async () => {
  const form = formFixture();
  mountSearchDates(form);
  const toggle = form.fields.search_today, manual = form.nodes['[data-manual-search]'];
  assert.equal(manual.hidden, false);
  let calls = 0;
  globalThis.fetch = async (_url, options) => {
    calls++;
    assert.deepEqual(JSON.parse(options.body), { search_today: true });
    return { ok: true, json: async () => ({ search_today: true,
      date_from: '2026-09-08', date_to: '2026-09-20', today: '2026-09-14' }) };
  };
  toggle.checked = true; toggle.listeners.change();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 1); assert.equal(manual.hidden, true);
  globalThis.fetch = async () => ({ ok: false });
  toggle.checked = false; toggle.listeners.change();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(toggle.checked, true); assert.equal(manual.hidden, true);
  globalThis.fetch = async (_url, options) => {
    assert.deepEqual(JSON.parse(options.body), { search_today: false, date_from: '2026-09-08', date_to: '2026-09-20' });
    return { ok: true, json: async () => ({ search_today: false,
      date_from: '2026-09-08', date_to: '2026-09-20', today: '2026-09-14' }) };
  };
  toggle.checked = false; toggle.listeners.change();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(manual.hidden, false); assert.equal(form.nodes['[data-manual-dates]'].disabled, false);
});

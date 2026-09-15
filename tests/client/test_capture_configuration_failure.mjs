import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';

const source = await readFile('client/app.js', 'utf8');
const start = source.indexOf('window.addEventListener("face-moment:reference-series-ready", async');
const handlerSource = source.slice(start, source.indexOf('\nconst cameraConfig', start));

function fixture() {
  let handler;
  const events = [];
  const context = {
    window: { addEventListener: (_, fn) => { handler = fn; }, dispatchEvent: event => events.push(event) },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    signalProgress: { begin() {} },
    jpegQualityController: { getActiveAttemptSnapshot: () => ({ attemptId: 'one' }) },
    promoDisplayController: { loadDisplayConfiguration: async () => ({}) },
    getBlazeFaceDetector: async () => ({ setThreshold: async () => {} }),
    detectReferenceSeries: async () => [],
    document: { body: { dataset: {} }, querySelectorAll: () => [{ remove() { context.removed = true; } }] },
    detectorFailureMessage: false,
    renderDetectorFailure() { context.detectorFailureMessage = true; },
    updateTriggerStatus(_, message) { context.message = message; },
    submitReadyReferenceSeries() { context.submitted = true; },
  };
  runInNewContext(handlerSource, context);
  return { context, events, run: () => handler({ detail: { attemptId: 'one', frames: [] } }) };
}

for (const failure of ['network', 'timeout', 'unauthorized']) {
  test(`configuration ${failure} is not a detector failure and permits recovery`, async () => {
    const f = fixture();
    f.context.promoDisplayController.loadDisplayConfiguration = async () => { throw new Error(failure); };
    await f.run();
    assert.equal(f.context.detectorFailureMessage, false);
    assert.equal(f.events.at(-1).detail.reason, 'configuration_failure');
    assert.equal(f.events.some(event => event.type === 'face-moment:detector-failure'), false);
    assert.match(f.context.message, /конфигурацию/);
    f.context.promoDisplayController.loadDisplayConfiguration = async () => ({});
    await f.run();
    assert.equal(f.context.submitted, true);
    assert.match(f.context.message, /Конфигурация получена/);
  });
}

test('real detector failure is reported and its warning is cleared on recovery', async () => {
  const f = fixture();
  f.context.detectReferenceSeries = async () => { throw new Error('detector'); };
  await f.run();
  assert.equal(f.context.detectorFailureMessage, true);
  assert.equal(f.events.at(-1).type, 'face-moment:detector-failure');
  f.context.detectReferenceSeries = async () => [];
  await f.run();
  assert.equal(f.context.detectorFailureMessage, false);
  assert.equal(f.context.removed, true);
  assert.equal(f.context.document.body.dataset.detectorState, 'ready');
});

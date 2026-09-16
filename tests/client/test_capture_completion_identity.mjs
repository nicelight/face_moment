import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';
import { createJpegQualityController } from '../../client/jpeg-quality.js';

const source = await readFile('client/app.js', 'utf8');
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));

function fixture() {
  const listeners = new Map();
  const completed = [];
  const submitted = [];
  const quality = createJpegQualityController({ storage: null });
  const context = {
    activeRequestCapture: null, successfulCooldownAttemptId: null,
    clearPromoHandoff() {},
    advertisingPlayer: { start() {}, stop() {} },
    currentView: () => 'advertising',
    jpegQualityController: quality,
    attemptOutcomeController: { beginAttempt() {} },
    triggerController: { finishAttempt(detail) { completed.push(detail); return true; } },
    signalProgress: { begin() {}, cancel() {} },
    displayConfigSnapshots: new Map(),
    promoDisplayController: { loadDisplayConfiguration: async () => ({}) },
    document: { body: { dataset: {} }, querySelectorAll: () => [] },
    updateTriggerStatus() {}, getBlazeFaceDetector: async () => ({ setThreshold: async () => {} }),
    detectReferenceSeries: async () => [], detectorFailureMessage: false,
    submitReadyReferenceSeries(detail) { submitted.push(detail.attemptId); },
    CustomEvent: class { constructor(type, { detail }) { this.type = type; this.detail = detail; } },
    window: {
      addEventListener(type, fn) { listeners.set(type, [...(listeners.get(type) ?? []), fn]); },
      dispatchEvent(event) { for (const fn of listeners.get(event.type) ?? []) fn(event); },
    },
  };
  runInNewContext(section('window.addEventListener("face-moment:attempt-request-start"', 'window.addEventListener("face-moment:attempt-response"'), context);
  runInNewContext(section('function finishingCaptureId(', '\nconst cameraConfig'), context);
  return {
    quality, completed, submitted, context,
    emit(type, detail) { context.window.dispatchEvent({ type: `face-moment:${type}`, detail }); },
    ready(id) { return listeners.get('face-moment:reference-series-ready')[0]({ detail: { attemptId: id, frames: [] } }); },
  };
}

for (const success of [true, false]) {
  test(`request-ID completion (${success ? 'success' : 'render failure'}) releases capture and permits next search`, async () => {
    const f = fixture();
    f.emit('attempt-start', { attemptId: 'capture-1' });
    f.emit('attempt-request-start', { attemptId: 'request-1', captureId: 'capture-1', displayConfig: {} });
    f.emit('attempt-finished', { attemptId: 'request-1', success });
    assert.equal(f.quality.getActiveAttemptSnapshot(), null);
    assert.equal(f.completed.length, 1);
    f.emit('attempt-start', { attemptId: 'capture-2' });
    f.emit('attempt-finished', { attemptId: 'request-1', success });
    assert.equal(f.quality.getActiveAttemptSnapshot().attemptId, 'capture-2');
    assert.equal(f.completed.length, 1, 'late completion must not finish a new capture');
    await f.ready('capture-2');
    assert.deepEqual(f.submitted, ['capture-2']);
  });
}

test('pre-request failure completes by capture ID', () => {
  const f = fixture();
  f.emit('attempt-start', { attemptId: 'capture-1' });
  f.emit('attempt-finished', { attemptId: 'capture-1', success: false });
  assert.equal(f.quality.getActiveAttemptSnapshot(), null);
  assert.equal(f.completed.length, 1);
});

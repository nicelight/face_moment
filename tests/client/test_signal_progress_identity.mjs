import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createSignalProgress } from '../../client/signal-progress.js';

test('only the current server identity is displayed and a new capture clears it', () => {
  const identity = { textContent: '', hidden: false };
  const caption = {};
  const classes = { add() {}, remove() {} };
  const element = {
    dataset: {}, classList: classes, setAttribute() {},
    querySelector: selector => selector === '.signal-caption' ? caption : identity,
    querySelectorAll: () => [],
  };
  const document = { body: { append() {}, classList: classes }, createElement: () => element };
  const progress = createSignalProgress({ document });
  const serverId = '00ee73b7-ea3a-46f6-92ab-573989988fd6';
  progress.begin('capture-1');
  progress.bind('capture-1', 'client-1');
  assert.equal(identity.hidden, true);
  progress.serverIdentity('client-1', null);
  assert.equal(identity.hidden, true);
  progress.serverIdentity('client-1', serverId);
  assert.equal(identity.textContent, `Attempt ID: ${serverId}`);
  assert.equal(identity.hidden, false);
  progress.phase('client-1', 'photos');
  assert.equal(identity.hidden, false);
  progress.begin('capture-2');
  progress.bind('capture-2', 'client-2');
  progress.serverIdentity('client-1', serverId);
  assert.equal(identity.hidden, true);
  assert.equal(identity.textContent, '');
});

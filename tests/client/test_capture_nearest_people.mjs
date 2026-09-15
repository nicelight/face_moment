import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';

const source = await readFile('client/capture-identity.js', 'utf8');
const cardSource = source.slice(source.indexOf('  function cropCard('), source.indexOf('  function renderCaptureDetails('));
function element(tag, text = '') {
  return { tag, text, children: [], append(...nodes) { this.children.push(...nodes); }, add(node) { this.children.push(node); } };
}
const context = { element, reasons: { below_threshold: 'Сходство ниже порога площадки' },
  Option: class { constructor(text, value) { this.text = text; this.value = value; } } };
runInNewContext(cardSource, context);
const id = '00000000-0000-0000-0000-000000b9cce7';

test('all three candidates are displayed below threshold with names, short IDs and scores', () => {
  const card = context.cropCard({ person_id: null, reason: 'below_threshold', score: .29,
    nearest_people: [
      { person_id: id, identity_name: 'Андрей', score: .29 },
      { person_id: id.replace('b9cce7', '128502'), identity_name: 'БроСергей', score: .225 },
      { person_id: id.replace('b9cce7', 'f6c97f'), identity_name: 'Васим', score: -.1 },
    ] }, { threshold: .38 });
  assert.equal(card.children.find(node => node.tag === 'strong').text, 'Не распознан');
  assert.deepEqual(card.children.find(node => node.tag === 'ol').children.map(node => node.text), [
    'Андрей · b9cce7 — 0.290', 'БроСергей · 128502 — 0.225', 'Васим · f6c97f — -0.100',
  ]);
});

test('historical recognized identity has short ID; missing historical candidates are not invented', () => {
  const recognized = context.cropCard({ person_id: id, identity_name: 'Андрей', score: .8 }, { threshold: .38 });
  assert.equal(recognized.children.find(node => node.tag === 'strong').text, 'Андрей · b9cce7');
  const old = context.cropCard({ person_id: null, reason: 'below_threshold', score: .2 }, { threshold: .38 });
  assert.equal(old.children.some(node => node.tag === 'ol'), false);
});

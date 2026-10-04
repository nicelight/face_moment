import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createPhotoSelection } from '../../client/public-photo-selection.js';

const deferred = () => { let resolve, reject; const promise=new Promise((a,b)=>{resolve=a;reject=b;}); return {promise,resolve,reject}; };
const quote = (n,total) => ({selected_count:n,total_kopecks:total,currency:'RUB'});
test('combined selection sends exact IDs; all keeps other venues; pending and failed totals are non-actionable', async () => {
  const requests=[],changes=[];
  const state=createPhotoSelection({resultId:'current',onChange:s=>changes.push(s),requestQuote:body=>{requests.push(body);return Promise.resolve(quote(body.photo_ids.length,12345));}});
  await state.set('paid',true); await state.setAll(['free','common'],true);
  assert.deepEqual(requests.at(-1),{result_id:'current',photo_ids:['paid','free','common']});
  assert.equal(state.snapshot().quote.total_kopecks,12345);
  await state.setAll(['free','common'],false);assert.deepEqual(state.snapshot().photo_ids,['paid']);
  assert.ok(changes.some(s=>s.status==='pending' && s.quote===null));
  await state.clear();assert.equal(state.snapshot().status,'empty');assert.equal(state.snapshot().quote,null);
});
test('late response or error cannot replace latest quote or resurrect a cleared result', async () => {
  const requests=[];
  const state=createPhotoSelection({resultId:'current',onChange:()=>{},requestQuote:()=>{const d=deferred();requests.push(d);return d.promise;}});
  const first=state.set('paid',true),second=state.set('free',true);
  requests[1].resolve(quote(2,987));await second;
  requests[0].resolve(quote(1,111));await first;assert.equal(state.snapshot().quote.total_kopecks,987);
  const third=state.set('common',true);assert.equal(state.snapshot().quote,null);
  requests[2].reject(Error('offline'));await third;assert.equal(state.snapshot().status,'error');assert.equal(state.snapshot().quote,null);
  const fourth=state.set('common',false);await state.clear();requests[3].resolve(quote(2,222));await fourth;
  assert.equal(state.snapshot().status,'empty');assert.equal(state.snapshot().quote,null);
});

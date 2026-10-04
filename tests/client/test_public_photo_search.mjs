import assert from 'node:assert/strict';
import { test } from 'node:test';
import { searchCurrentSelfie } from '../../client/public-photo-search.js';

test('explicit search multipart contains only supplied current JPEG and selected venues; reset strict bool', async () => {
  const selfie = new Blob(['current only'], {type:'image/jpeg'});
  const calls=[];
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return{ok:true,json:async()=>({schema_version:1,outcome:'no_matches'})};};
  await searchCurrentSelfie(selfie,['a','b']);
  await searchCurrentSelfie(selfie,['a'],true);
  assert.equal(calls[0].url,'/api/public/search');
  assert.equal(calls[0].options.credentials,'same-origin');
  assert.equal(calls[0].options.cache,'no-store');
  assert.deepEqual([...calls[0].options.body.keys()],['selfie','venue_ids']);
  assert.equal(await calls[0].options.body.get('selfie').text(),'current only');
  assert.equal(calls[0].options.body.get('venue_ids'),'["a","b"]');
  assert.equal(calls[1].options.body.get('confirm_reset'),'true');
});
test('empty/overlarge/duplicate selection and missing/non-JPEG current capture never send',async()=>{
  globalThis.fetch=async()=>assert.fail('invalid input must not send');
  const selfie=new Blob(['current'],{type:'image/jpeg'});
  for(const selection of [[],['a','b','c','d'],['a','a']]) await assert.rejects(searchCurrentSelfie(selfie,selection),/invalid_search_input/);
  await assert.rejects(searchCurrentSelfie(null,['a']),/invalid_search_input/);
  await assert.rejects(searchCurrentSelfie(new Blob(['x'],{type:'image/png'}),['a']),/invalid_search_input/);
});
test('HTTP and network failures cannot return a successful outcome',async()=>{
  const selfie=new Blob(['x'],{type:'image/jpeg'});
  for(const status of [429,403,422,500,503]) {
    globalThis.fetch=async()=>({ok:false,status,json:()=>assert.fail('HTTP failure must not be accepted')});
    await assert.rejects(searchCurrentSelfie(selfie,['a']),status===429?/rate_limited/:/request_failed/);
  }
  globalThis.fetch=async()=>{throw new Error('network');};
  await assert.rejects(searchCurrentSelfie(selfie,['a']),/network/);
});

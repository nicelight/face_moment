import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createPhotoDownload } from '../../client/public-photo-download.js';
const free = (ids=['free']) => ({result_id:'result',photo_ids:ids,quote:{total_kopecks:0,paid_count:0}});
test('ambiguous create retries reuse client_request_id; known order refresh creates no duplicate', async () => {
  const calls=[],states=[];let fail=true,ids=0;
  const controller=createPhotoDownload({makeId:()=>`attempt-${++ids}`,onChange:s=>states.push(s),request:async(url,body)=>{
    calls.push({url,body});if(body){if(fail){fail=false;throw Error('lost response');}return {id:'order',total_kopecks:0};}
    return {total_kopecks:0,archive_status:'preparing'};
  }});
  await controller.start(free());assert.equal(states.at(-1).status,'error');
  await controller.start(free());await controller.start(free());
  const posts=calls.filter(c=>c.body);assert.equal(posts.length,2);assert.deepEqual(posts[0].body,posts[1].body);
  assert.deepEqual(Object.keys(posts[0].body).sort(),['client_request_id','photo_ids','result_id']);
  assert.equal(ids,1);assert.equal(calls.filter(c=>!c.body).length,2);assert.equal(states.at(-1).status,'preparing');
});
test('changed selection resets attempt and drops late status from old order; paid quote does not create', async () => {
  let release,ids=0;const states=[],posts=[];
  const controller=createPhotoDownload({makeId:()=>String(++ids),onChange:s=>states.push(s),request:async(url,body)=>{
    if(body){posts.push(body);return {id:body.client_request_id,total_kopecks:0};}
    if(url.endsWith('/1'))return new Promise(resolve=>{release=resolve;});
    return {archive_status:'ready',total_kopecks:0,download_url:'/api/public/archives/2?token=synthetic'};
  }});
  const old=controller.start(free());await new Promise(resolve=>setImmediate(resolve));
  controller.select(free(['common']));await controller.start(free(['common']));
  release({archive_status:'failed',total_kopecks:0});await old;
  assert.equal(states.at(-1).status,'ready');assert.notEqual(posts[0].client_request_id,posts[1].client_request_id);
  await controller.start({...free(['paid']),quote:{paid_count:1,total_kopecks:100}});assert.equal(posts.length,2);
});
test('concurrent click is one creation; archive failure is distinct from transport failure', async () => {
  let release;const states=[];let posts=0;
  const controller=createPhotoDownload({makeId:()=> 'one',onChange:s=>states.push(s),request:async(url,body)=>{
    if(body){posts++;return new Promise(resolve=>{release=resolve;});}
    return {total_kopecks:0,archive_status:'failed',error:'unsafe private key'};
  }});
  const first=controller.start(free());await controller.start(free());assert.equal(posts,1);
  release({id:'order',total_kopecks:0});await first;assert.deepEqual(states.at(-1),{status:'failed',total_kopecks:0});
});

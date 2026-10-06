import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createPhotoDownload} from '../../client/public-photo-download.js';

const paid = () => ({result_id:'result',photo_ids:['paid','free'],quote:{total_kopecks:101,paid_count:1}});

test('paid attempt freezes email, method and id across ambiguous POST and stays preparing before provider', async () => {
  const calls=[], states=[]; let lose=true;
  const controller=createPhotoDownload({makeId:()=> 'same-id',onChange:s=>states.push(s),request:async(url,body)=>{
    calls.push({url,body});
    if(url==='/api/public/orders') {if(lose){lose=false;throw Error('lost response');}return {id:'order',total_kopecks:101};}
    return {archive_status:'preparing',total_kopecks:101,payment_status:'pending'};
  }});
  await controller.start(paid());
  assert.equal(states.at(-1).status,'email');
  await controller.start(paid(),{email:'frozen@example.test',payment_method:'sbp'});
  assert.equal(states.at(-1).status,'error');
  await controller.start(paid());
  assert.equal(states.at(-1).status,'preparing');
  assert.deepEqual(calls[0].body,calls[1].body);
  assert.equal(calls[0].body.client_request_id,'same-id');
  assert.equal(calls[0].body.email,'frozen@example.test');
  assert.equal(calls[0].body.payment_method,'sbp');
  assert.equal(calls.some(call=>call.url.endsWith('/payment')),false);
});

test('paid return requires server status and confirmed download_url', async () => {
  let status='pending'; const states=[], calls=[];
  const controller=createPhotoDownload({onChange:s=>states.push(s),request:async url=>{
    calls.push(url);
    return {archive_status:'ready',total_kopecks:101,payment_status:status,
      ...(status==='succeeded'?{download_url:'/api/public/archives/order?token=server'}:{})};
  }});
  await controller.resume({key:'selection',id:'order',client_request_id:'same-id'});
  assert.equal(states.at(-1).status,'pending');
  assert.equal(states.at(-1).download_url,undefined);
  status='canceled';await controller.refresh();assert.equal(states.at(-1).status,'canceled');
  status='succeeded';await controller.refresh();assert.equal(states.at(-1).status,'ready');
  assert.match(states.at(-1).download_url,/token=server/);
  assert.deepEqual(calls,['/api/public/orders/order','/api/public/orders/order','/api/public/orders/order']);
});

test('retry after saved paid return keeps the same order through pending or preparing status', async () => {
  for (const archive_status of ['ready','preparing']) {
    const calls=[], states=[];
    const controller=createPhotoDownload({onChange:s=>states.push(s),request:async (url,body) => {
      calls.push({url,body});
      return {archive_status,total_kopecks:101,payment_status:'pending'};
    }});
    await controller.resume({key:JSON.stringify(['result',['free','paid']]),id:'saved-order',client_request_id:'same-id'});
    assert.equal(states.at(-1).status,archive_status==='ready'?'pending':'preparing');
    await controller.start(paid());
    assert.equal(states.at(-1).status,archive_status==='ready'?'pending':'preparing');
    assert.deepEqual(calls.map(call=>call.url),['/api/public/orders/saved-order','/api/public/orders/saved-order']);
  }
});

test('created order amount and free mode replace the quoted values', async () => {
  for (const total of [999, 0]) {
    const states=[], calls=[];
    const controller=createPhotoDownload({makeId:()=> 'same-id',onChange:s=>states.push(s),
      request:async (url, body) => {
        calls.push({url,body});
        if(url==='/api/public/orders') return {id:'order',archive_status:'ready',total_kopecks:total};
        return {archive_status:total ? 'preparing' : 'ready',total_kopecks:total,
          payment_status:total ? 'pending' : 'not_required',
          ...(total ? {} : {download_url:'/api/public/archives/order?token=free'})};
      }});
    await controller.start(paid());
    await controller.start(paid(),{email:'frozen@example.test',payment_method:'bank_card'});
    assert.equal(states.at(-1).total_kopecks,total);
    assert.equal(states.at(-1).status,total ? 'preparing' : 'ready');
    assert.equal(calls.some(call=>call.url.endsWith('/payment')),false);
    if (!total) assert.equal(states.at(-1).download_url,'/api/public/archives/order?token=free');
  }
});

import assert from 'node:assert/strict';
import { test } from 'node:test';
globalThis.document={querySelectorAll:()=>[],cookie:'fm_staff_csrf=fixture'};
const {mountSpaFreeMode}=await import('../../client/spa-free-settings.js');
function fixture(saved=false){
 const input={checked:saved},button={},status={},listeners={};
 const form={dataset:{spaId:'venue',isFree:String(saved)},elements:{namedItem:()=>input},
  querySelector:key=>key==='[role="status"]'?status:button,addEventListener:(name,fn)=>listeners[name]=fn};
 mountSpaFreeMode(form);return {form,input,button,status,submit:()=>listeners.submit({preventDefault(){}})};
}
test('false→true requires confirmation and cancel/close never sends PUT',async()=>{
 const f=fixture();f.input.checked=true;globalThis.window={confirm:()=>false};
 globalThis.fetch=()=>assert.fail('cancel must not mutate');await f.submit();
 assert.equal(f.button.disabled,undefined);assert.equal(f.form.dataset.isFree,'false');
 window.confirm=()=>true;globalThis.fetch=async(url,options)=>{
  assert.equal(url,'/api/serving/spas/venue/is-free');assert.equal(options.method,'PUT');
  assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store');
  assert.equal(options.headers['X-CSRF-Token'],'fixture');assert.deepEqual(JSON.parse(options.body),{is_free:true});
  return {ok:true,json:async()=>({spa_id:'venue',is_free:true})};};
 await f.submit();assert.equal(f.form.dataset.isFree,'true');assert.match(f.status.textContent,/сохранён/);
});
test('true→false has no enabling popup; rejected save keeps canonical state',async()=>{
 const f=fixture(true);f.input.checked=false;globalThis.window={confirm:()=>assert.fail('disabling does not confirm')};
 globalThis.fetch=async()=>({ok:false,status:403});await f.submit();
 assert.equal(f.form.dataset.isFree,'true');assert.match(f.status.textContent,/Нет прав/);assert.equal(f.button.disabled,false);
 globalThis.fetch=async()=>({ok:true,json:async()=>({is_free:false})});await f.submit();
 assert.equal(f.form.dataset.isFree,'false');assert.equal(f.input.checked,false);
});

import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

const evidence = '.tasks/TASK-136-T2-FT-015-W12';
let fixture, baseURL, exited;
test.use({ ignoreHTTPSErrors: true, trace: 'on', viewport: { width: 1280, height: 900 } });
test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true });
  fixture = spawn('uv', ['run', '--locked', '--env-file', '.env.local', 'python', '-m', 'tests.client.public_photo_download_browser_fixture'], { stdio: ['pipe', 'pipe', 'inherit'] });
  exited = new Promise(resolve => fixture.on('exit', resolve));
  const lines = createInterface({ input: fixture.stdout });
  baseURL = await new Promise((resolve, reject) => {
    lines.on('line', line => { if (line.startsWith('{')) resolve(JSON.parse(line).url); else console.log(line); });
    fixture.on('exit', code => reject(new Error(`fixture exit ${code}`)));
  });
});
test.afterAll(async () => { fixture?.stdin.end('\n'); if (exited) expect(await exited).toBe(0); });
async function setup(page) {
  await page.route('**/camera-fixture.png', route => readFile('tests/client/fixtures/selfie-portrait-small.png').then(body => route.fulfill({ contentType: 'image/png', body })));
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }) } });
    Object.defineProperty(HTMLMediaElement.prototype, 'srcObject', { configurable: true, set(v) { this.__stream = v; }, get() { return this.__stream; } });
    Object.defineProperty(HTMLMediaElement.prototype, 'readyState', { configurable: true, get: () => 4 });
    Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', { configurable: true, get: () => 310 });
    Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', { configurable: true, get: () => 360 });
    HTMLMediaElement.prototype.play = async () => { const image = new Image(); image.src = '/camera-fixture.png'; await image.decode(); window.__cameraImage = image; };
    const drawImage = CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage = function(source, ...args) { return drawImage.call(this, source instanceof HTMLVideoElement ? window.__cameraImage : source, ...args); };
  });
  await page.goto(baseURL);
}
async function capture(page, retake = false) {
  await page.locator(retake ? '#selfie-retake' : '#selfie-viewport').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state','ready');
  await page.locator('#selfie-viewport').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state','captured');
}
async function config(page, values) { expect((await page.request.post(`${baseURL}/__fixture`, { data: values })).ok()).toBeTruthy(); }
async function submit(page, button = '#selfie-send') {
  const response = page.waitForResponse(r => r.url().endsWith('/api/public/search'));
  await page.locator(button).click(); return response;
}

test('FT-015-AC-002 free served browser order preparation failure and ready', async ({page}) => {
  const assertions=[],network=[],errors=[],posts=[];
  function proved(name, observed) { assertions.push({name,result:'PASS',observed}); console.log(`AC-002 PASS ${name}: ${JSON.stringify(observed)}`); }
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',r=>{
    if(r.url().includes('/api/public/orders'))network.push({method:r.method(),path:new URL(r.url()).pathname,body:r.postDataJSON()});
    if(r.url().endsWith('/api/public/orders') && r.method()==='POST')posts.push(r.postDataJSON());
  });
  const state=async(values={})=>(await page.request.post(`${baseURL}/__fixture`,{data:values})).json();
  try {
    await setup(page); await capture(page);
    const options=page.locator('#search-venues input'); await options.nth(0).check(); await options.nth(1).check();
    const result=await (await submit(page)).json(); await expect(page.locator('#search-gallery')).toBeVisible();
    const sections=page.locator('#search-gallery > section');
    const free=sections.nth(1).locator('.fm-photo-select-free input').first();
    const common=sections.nth(0).locator('.fm-photo-select-free input').first();
    await free.check(); await expect(page.locator('#photo-selection-total')).toHaveText('0,00 ₽');
    // Lose an actual committed POST response, preserving real server semantics.
    let lose=true;
    await page.route('**/api/public/orders',async route=>{
      if(lose && route.request().method()==='POST'){lose=false;expect((await route.fetch()).status()).toBe(200);await route.abort('failed');}
      else await route.continue();
    });
    await page.locator('#photo-selection-download').click();
    await expect.poll(()=>posts.length,{timeout:1500,message:'AC-002 Скачать must POST one free order to actual backend'}).toBe(1);
    await expect(page.locator('#photo-download-status')).toContainText('Не удалось проверить');
    let snapshot=await state();expect(snapshot.orders).toHaveLength(1);
    proved('free click creates one actual order; ambiguous response shows manual retry',snapshot.orders[0]);
    await page.screenshot({path:`${evidence}/transport-retry.png`,fullPage:true});
    await page.locator('#photo-download-retry').click();
    await expect(page.locator('#photo-download-status')).toContainText('30 секунд');
    expect(posts).toHaveLength(2);expect(posts[1]).toEqual(posts[0]);
    expect(Object.keys(posts[0]).sort()).toEqual(['client_request_id','photo_ids','result_id']);
    expect(posts[0].result_id).toBe(result.result_id);
    snapshot=await state();expect(snapshot.orders).toHaveLength(1);expect(snapshot.orders[0].status).toBe('preparing');
    expect(snapshot.orders[0].total).toBe(0);expect(snapshot.orders[0].email).toBeNull();expect(snapshot.orders[0].method).toBeNull();expect(snapshot.orders[0].provider).toBeNull();
    proved('stable request id replays same free order without email/payment or price authority',posts);
    const gets=network.filter(r=>r.method==='GET').length;
    await page.locator('#photo-download-retry').click();await expect(page.locator('#photo-download-status')).toContainText('30 секунд');
    await expect.poll(()=>network.filter(r=>r.method==='GET').length).toBe(gets+1);expect(posts).toHaveLength(2);
    await page.locator('#photo-selection-download').click();await expect(page.locator('#photo-download-status')).toContainText('30 секунд');expect(posts).toHaveLength(2);
    proved('preparing says repeat in 30 seconds; manual refresh and click reuse owner GET',network.filter(r=>r.method==='GET'));
    await page.screenshot({path:`${evidence}/preparing.png`,fullPage:true});
    await state({release:true});
    await expect.poll(async()=> (await state()).orders[0].status).toBe('ready');
    await page.locator('#photo-download-retry').click();await expect(page.locator('#photo-download-link')).toBeVisible();
    await expect(page.locator('#photo-download-status')).toContainText('Архив готов');
    expect(await page.locator('#photo-download-link').getAttribute('href')).toMatch(/^\/api\/public\/archives\/.+\?token=/);
    const downloadPromise=page.waitForEvent('download');await page.locator('#photo-download-link').click();const download=await downloadPromise;
    expect(download.suggestedFilename()).toBe('face-moment-photos.zip');expect(await download.failure()).toBeNull();
    const archive=await readFile(await download.path());expect(archive.subarray(0,2).toString()).toBe('PK');
    proved('real executor and signer deliver ready archive in browser',{filename:download.suggestedFilename(),bytes:archive.length});
    await page.screenshot({path:`${evidence}/ready.png`,fullPage:true});
    // Change selection: common photo at the paid venue is still server-quoted free.
    await state({block:true,archive_fail:true});await common.check();await expect(page.locator('#photo-selection-total')).toHaveText('0,00 ₽');
    await expect(page.locator('#photo-download-panel')).toBeHidden();
    await page.locator('#photo-selection-download').click();await expect(page.locator('#photo-download-status')).toContainText('30 секунд');
    expect(posts).toHaveLength(3);expect(posts[2].client_request_id).not.toBe(posts[0].client_request_id);
    snapshot=await state();expect(snapshot.orders).toHaveLength(2);expect(snapshot.orders[1].photo_ids).toEqual(expect.arrayContaining([result.venues[1].personal[0].id,result.venues[0].common[0].id]));
    proved('changed free selection starts new attempt including common at paid venue',snapshot.orders[1]);
    await state({release:true});await expect.poll(async()=>(await state()).orders[1].status).toBe('failed');
    await page.locator('#photo-download-retry').click();await expect(page.locator('#photo-download-status')).toHaveText('Не удалось подготовить архив. Обратитесь в поддержку.');
    await expect(page.locator('#photo-download-link')).toBeHidden();
    await page.locator('#photo-download-retry').click();await expect(page.locator('#photo-download-status')).toContainText('поддержку');
    expect(posts).toHaveLength(3);snapshot=await state();expect(snapshot.orders).toHaveLength(2);expect(snapshot.mail_count).toBe(1);
    proved('real generation failure stays safe with manual support and status-only retry',snapshot.orders[1]);
    await page.screenshot({path:`${evidence}/failed.png`,fullPage:true});
    // A ready URL can become unavailable; display safe support feedback in the same page.
    await common.uncheck();await state({archive_fail:false});await page.locator('#photo-selection-download').click();
    await expect.poll(async()=>(await state()).orders[2]?.status).toBe('ready');
    if(!(await page.locator('#photo-download-link').isVisible())) await page.locator('#photo-download-retry').click();
    await expect(page.locator('#photo-download-link')).toBeVisible();
    await page.route('**/api/public/archives/**',route=>route.fulfill({status:404,body:'unsafe storage detail'}));
    await page.locator('#photo-download-link').click();await expect(page.locator('#photo-download-status')).toHaveText('Не удалось подготовить архив. Обратитесь в поддержку.');
    expect(await page.locator('#photo-download-status').textContent()).not.toContain('unsafe');
    proved('unavailable ready delivery renders safe manual support',await page.locator('#photo-download-status').textContent());
    expect(network.some(r=>r.path.endsWith('/payment'))).toBe(false);expect(page.url()).toBe(`${baseURL}/`);
    await expect(page.locator('input[type=email],select[name=payment_method]')).toHaveCount(0);
    expect(errors).toEqual([]);snapshot=await state();expect(snapshot.orders.every(o=>o.total===0 && o.email===null && o.method===null && o.provider===null)).toBe(true);
    proved('no payment navigation/email form/private errors; all orders free',snapshot.orders.length);
    for(const width of [1280,390]) {
      await page.setViewportSize({width,height:900});await page.locator('#photo-download-panel').scrollIntoViewIfNeeded();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await expect(page.locator('#photo-download-status')).toBeVisible();
      await page.screenshot({path:`${evidence}/download-${width}.png`,fullPage:true});
    }
    proved('existing UI readable desktop/mobile without horizontal overflow',[1280,390]);
  } finally { await writeFile(`${evidence}/browser-assertions.json`,JSON.stringify({claim:'.memory-bank/features/FT-015.md#FT-015-AC-002',assertions,network,errors},null,2)); }
});

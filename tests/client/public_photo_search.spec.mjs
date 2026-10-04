import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { mkdir, readFile } from 'node:fs/promises';

const evidence = '.tasks/TASK-125-T2-FT-013-W7';
let fixture, baseURL, exited;
test.use({ ignoreHTTPSErrors: true, trace: 'on', viewport: { width: 1280, height: 900 } });
test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true });
  fixture = spawn('uv', ['run', '--locked', '--env-file', '.env.local', 'python', '-m', 'tests.client.public_photo_search_browser_fixture'], { stdio: ['pipe', 'pipe', 'inherit'] });
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

test('AC-003 explicit current JPEG, 1–3 venues, engaged progress and real API summary', async ({ page }) => {
  const searches=[];
  page.on('request', r => { if(r.url().endsWith('/api/public/search')) searches.push(r); });
  await setup(page); await config(page,{delay:.7}); await capture(page);
  await expect(page.locator('#selfie-send')).toBeDisabled();
  await expect(page.locator('#search-venues input')).toHaveCount(4);
  const options=page.locator('#search-venues input');
  await options.nth(0).check(); await options.nth(1).check(); await options.nth(2).check();
  await expect(options.nth(3)).toBeDisabled();
  await options.nth(2).uncheck(); await expect(options.nth(3)).toBeEnabled();
  expect(searches).toHaveLength(0);
  await page.evaluate(() => { window.__submittedCapture = null; const original=fetch; window.fetch=(url,init) => { if(String(url).endsWith('/api/public/search')) window.__submittedCapture=init.body.get('selfie'); return original(url,init); }; });
  const response=page.waitForResponse(r=>r.url().endsWith('/api/public/search'));
  await page.locator('#selfie-send').click();
  await expect(page.locator('#search-progress')).toBeVisible();
  await expect(page.locator('#search-progress')).not.toContainText('%');
  await expect(page.locator('#selfie-retake')).toBeDisabled();
  await page.screenshot({path:`${evidence}/progress-1280.png`,fullPage:true});
  expect((await response).status()).toBe(200);
  await expect(page.locator('#search-summary')).toContainText('4');
  await expect(page.locator('#search-summary')).toContainText('synthetic venue 0');
  await expect(page.locator('#search-summary')).toContainText('synthetic venue 1');
  await expect(page.locator('#search-summary')).toContainText('2001-01-01');
  expect(searches).toHaveLength(1);
  expect(await page.evaluate(async()=>{const b=(await import('/client/site-selfie.js')).getCurrentSelfie();return b.type==='image/jpeg' && b.size===window.__submittedCapture.size && JSON.stringify([...new Uint8Array(await b.arrayBuffer())])===JSON.stringify([...new Uint8Array(await window.__submittedCapture.arrayBuffer())]);})).toBe(true);
  expect(searches[0].postDataBuffer().toString()).not.toContain('confirm_reset');
  for(const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:`${evidence}/summary-${width}.png`,fullPage:true});
  }
  console.log('AC-003 real HTTPS/API/PG: no POST before Submit, 1–3 venues, current JPEG only, engaged progress no %, personal count/venue/date, 1280/390');
});

test('AC-003 server A/B warning, same-capture confirmation, retake, later denial and clear failures', async ({page})=>{
  await setup(page); await capture(page); await page.locator('#search-venues input').first().check();
  await config(page,{vector:0}); expect((await submit(page)).status()).toBe(200);
  await config(page,{vector:1}); await submit(page);
  await expect(page.locator('#search-status')).toContainText('не найдены');
  await expect(page.locator('#search-summary')).toBeHidden();
  await config(page,{vector:2}); await submit(page);
  await expect(page.locator('#search-confirmation')).toBeVisible();
  await expect(page.locator('#search-confirmation')).toContainText('другое');
  await capture(page,true);
  await expect(page.locator('#search-confirmation')).toBeHidden();
  await submit(page);
  await expect(page.locator('#search-confirmation')).toBeVisible();
  await page.evaluate(async()=>{window.__beforeConfirm=(await import('/client/site-selfie.js')).getCurrentSelfie();});
  await page.screenshot({path:`${evidence}/warning-1280.png`,fullPage:true});
  const confirmed=await submit(page,'#search-confirm');
  expect(confirmed.request().postDataBuffer().toString()).toContain('true');
  expect(await page.evaluate(async()=>(await import('/client/site-selfie.js')).getCurrentSelfie()===window.__beforeConfirm)).toBe(true);
  await expect(page.locator('#search-confirmation')).toBeHidden();
  await config(page,{vector:3}); await submit(page);
  await config(page,{vector:4}); await submit(page);
  await expect(page.locator('#search-status')).toContainText('отличается');
  await expect(page.locator('#search-confirmation')).toBeHidden();
  await capture(page,true);
  for(const [values, message] of [[{busy:true},'занят'],[{delay:.03,deadline_ms:1},'Время'],[{faces:0},'Переснимите'],[{fail:true},'Не удалось']]) {
    await config(page,values); await submit(page);
    await expect(page.locator('#search-status')).toContainText(message);
    await expect(page.locator('#search-summary')).toBeHidden();
    await expect(page.locator('#search-confirmation')).toBeHidden();
  }
  await config(page,{});
  await page.route('**/api/public/search', route=>route.fulfill({status:429,body:'{}'}));
  await submit(page);
  await expect(page.locator('#search-status')).toContainText('Слишком много');
  await expect(page.locator('#search-summary')).toBeHidden();
  await page.unroute('**/api/public/search');
  await page.route('**/api/public/search', route=>route.abort()); await page.locator('#selfie-send').click();
  await expect(page.locator('#search-status')).toContainText('Не удалось');
  await expect(page.locator('#search-summary')).toBeHidden();
  await page.setViewportSize({width:390,height:900});
  await page.screenshot({path:`${evidence}/failure-390.png`,fullPage:true});
  console.log('AC-003 native API A/B/no_matches/busy/deadline/retake/500 and browser network failure explained; confirmation same Blob, later denial no reset, retake available');
});

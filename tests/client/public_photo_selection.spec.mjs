import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { mkdir, readFile } from 'node:fs/promises';

const evidence = '.tasks/TASK-129-T2-FT-014-W9';
let fixture, baseURL, exited;
test.use({ ignoreHTTPSErrors: true, trace: 'on', viewport: { width: 1280, height: 900 } });
test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true });
  fixture = spawn('uv', ['run', '--locked', '--env-file', '.env.local', 'python', '-m', 'tests.client.public_photo_selection_browser_fixture'], { stdio: ['pipe', 'pipe', 'inherit'] });
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

test('FT-014-AC-001 combined selection and server quote', async ({page}) => {
  await setup(page); await capture(page);
  const options=page.locator('#search-venues input');
  await options.nth(0).check(); await options.nth(1).check();
  const result=await (await submit(page)).json();
  await expect(page.locator('#search-gallery')).toBeVisible();
  await expect(page.locator('#photo-selection-summary')).toBeVisible();
  const summary=page.locator('#photo-selection-summary'), count=page.locator('#photo-selection-count'), total=page.locator('#photo-selection-total'), download=page.locator('#photo-selection-download');
  await expect(count).toHaveText('Выбрано: 0'); await expect(download).toBeDisabled();
  const sections=page.locator('#search-gallery > section');
  const paid=sections.nth(0).locator('.fm-photo-select-paid input'), free=sections.nth(1).locator('.fm-photo-select-free input');
  await expect(paid).toHaveCount(2); await expect(free).toHaveCount(4);
  expect(await paid.first().evaluate(n=>getComputedStyle(n).accentColor)).toBe('rgb(85, 155, 255)');
  expect(await free.first().evaluate(n=>getComputedStyle(n).accentColor)).toBe('rgb(85, 217, 149)');
  const totals=[];
  page.on('response',async response=>{if(response.url().endsWith('/api/public/quote') && response.status()===200)totals.push(await response.json());});
  async function select(locator, checked) {
    const response=page.waitForResponse(r=>r.url().endsWith('/api/public/quote'));
    await locator.setChecked(checked); const r=await response; expect(r.status()).toBe(200); const quote=await r.json();
    await expect(count).toHaveText(`Выбрано: ${quote.selected_count}`);
    await expect(total).toHaveText(`${new Intl.NumberFormat('ru-RU',{minimumFractionDigits:2,maximumFractionDigits:2}).format(quote.total_kopecks/100)} ₽`);
    await expect(download).toBeEnabled();
    const ids=await page.locator('#search-gallery .fm-photo-select input:checked').evaluateAll(nodes=>nodes.map(n=>n.closest('figure').dataset.photoId));
    expect(new Set(r.request().postDataJSON().photo_ids)).toEqual(new Set(ids)); expect(r.request().postDataJSON().result_id).toBe(result.result_id);
    return quote;
  }
  expect((await select(paid.first(),true)).total_kopecks).toBe(101);
  await select(free.first(),true); await expect(paid.first()).toBeChecked();
  await select(sections.nth(1).locator('.fm-photo-select-all input'),true);await expect(count).toHaveText('Выбрано: 5');
  await select(sections.nth(1).locator('.fm-photo-select-all input'),false);await expect(paid.first()).toBeChecked();
  // A reduced preview failure must be excluded from this venue's all-selection.
  const unavailable=sections.nth(0).locator('figure').last();
  await page.route(`**${result.venues[0].common.at(-1).preview_url}*`,route=>route.fulfill({status:404,body:''}));
  await unavailable.locator('img').evaluate(img=>{img.src=img.src+'?retry-test';});
  await expect(unavailable.locator('.fm-photo-select input')).toBeDisabled();
  await expect(download).toBeEnabled(); await expect(total).toHaveText('1,01 ₽');
  await select(sections.nth(0).locator('.fm-photo-select-all input'),true);
  await expect(count).toHaveText('Выбрано: 3');
  expect((await total.textContent())).toBe('1,52 ₽');
  // Delay only the first real quote response; newer request must win.
  let release, oldArrived; const oldReady=new Promise(r=>oldArrived=r); let intercept=true;
  await page.route('**/api/public/quote',async route=>{
    if(intercept){intercept=false;const response=await route.fetch();oldArrived();await new Promise(r=>release=r);await route.fulfill({response});}
    else await route.continue();
  });
  await free.first().check(); await oldReady;
  await expect(total).toHaveText('Рассчитываем стоимость…');await expect(download).toBeDisabled();
  const newer=page.waitForResponse(r=>r.url().endsWith('/api/public/quote'));
  await paid.last().uncheck();const newestQuote=await (await newer).json();
  await expect(total).toHaveText('1,01 ₽');release();await page.waitForTimeout(250);
  await expect(total).toHaveText('1,01 ₽');await expect(count).toHaveText(`Выбрано: ${newestQuote.selected_count}`);
  await page.unroute('**/api/public/quote');
  await page.route('**/api/public/quote',route=>route.fulfill({status:503,body:'{}'}));
  await free.last().check();await expect(total).toContainText('Не удалось');await expect(download).toBeDisabled();
  await page.unroute('**/api/public/quote');
  const retry=page.waitForResponse(r=>r.url().endsWith('/api/public/quote'));await page.locator('#photo-selection-retry').click();expect((await retry).status()).toBe(200);await expect(download).toBeEnabled();
  await page.evaluate(()=>document.addEventListener('photo-selection-download',e=>window.__selection=e.detail,{once:true}));
  await download.click();
  const detail=await page.evaluate(()=>window.__selection);expect(detail.result_id).toBe(result.result_id);
  expect(new Set(detail.photo_ids)).toEqual(new Set(await page.locator('#search-gallery .fm-photo-select input:checked').evaluateAll(nodes=>nodes.map(n=>n.closest('figure').dataset.photoId))));
  for(const width of [1280,390]) {
    await page.setViewportSize({width,height:900});await sections.last().scrollIntoViewIfNeeded();
    const box=await summary.boundingBox();expect(box.y).toBeGreaterThanOrEqual(0);expect(box.y+box.height).toBeLessThan(900);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await expect(download).toBeVisible();await page.screenshot({path:`${evidence}/selection-${width}.png`,fullPage:true});
  }
  await options.first().uncheck();await expect(summary).toBeHidden();
  console.log('FT-014-AC-001 GREEN: preserved paid/free/common selection, venue-local available all, colors, exact IDs/server total, late/pending/error response safety, retry/current IDs handoff, desktop1280/mobile390 sticky');
});

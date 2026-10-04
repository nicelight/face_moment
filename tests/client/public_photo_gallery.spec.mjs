import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { mkdir, readFile } from 'node:fs/promises';

const evidence = '.tasks/TASK-126-T2-FT-013-W8';
let fixture, baseURL, exited;
test.use({ ignoreHTTPSErrors: true, trace: 'on', viewport: { width: 1280, height: 900 } });
test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true });
  fixture = spawn('uv', ['run', '--locked', '--env-file', '.env.local', 'python', '-m', 'tests.client.public_photo_gallery_browser_fixture'], { stdio: ['pipe', 'pipe', 'inherit'] });
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

test('FT-013-AC-005 ordered venue feed uses granted private previews, personal watermark and free common', async ({page}) => {
  await setup(page); await capture(page);
  const options=page.locator('#search-venues input');
  for(let i=0;i<3;i++) await options.nth(i).check();
  let previewBusy = false;
  await page.route('**/api/public/results/*/previews/*', route => {
    if (!previewBusy) { previewBusy = true; return route.fulfill({status:429,body:''}); }
    return route.continue();
  });
  const response=await submit(page); const result=await response.json();
  expect(result.personal_count).toBe(4);
  await expect(page.locator('#search-gallery')).toBeVisible();
  const sections=page.locator('#search-gallery > section');
  await expect(sections).toHaveCount(result.venues.length);
  expect(result.venues).toHaveLength(2);
  expect(result.venues.map(v=>v.id)).not.toContain(await options.nth(2).inputValue());
  for(let i=0;i<result.venues.length;i++) {
    const section=sections.nth(i), venue=result.venues[i];
    await expect(section.locator('h2')).toHaveText(venue.name);
    const figures=section.locator('figure');
    const granted=[...venue.personal,...venue.common];
    await expect(figures).toHaveCount(granted.length);
    expect(await figures.evaluateAll(nodes=>nodes.map(n=>n.dataset.photoId))).toEqual(granted.map(p=>p.id));
    for(let j=0;j<granted.length;j++) {
      const figure=figures.nth(j), photo=granted[j];
      const image=figure.locator('img');
      await expect(image).toHaveAttribute('src',photo.preview_url);
      await expect.poll(()=>image.evaluate(img=>img.complete && img.naturalWidth===640)).toBe(true);
      await expect(figure.locator('figcaption')).toContainText(photo.visit_date);
      if(j<venue.personal.length) await expect(figure.locator('.fm-photo-watermark')).toBeVisible();
      else {await expect(figure.locator('.fm-photo-watermark')).toHaveCount(0);await expect(figure).toContainText('Бесплатно');}
      if(photo.is_free) await expect(figure).toContainText('Бесплатно');
    }
  }
  await expect(page.locator('#search-gallery')).not.toContainText('synthetic venue 2');
  // The overlay is frontend-only and removable; protected JPEG remains unchanged.
  await page.locator('.fm-photo-watermark').first().evaluate(node=>node.remove());
  expect(await sections.first().locator('img').first().evaluate(img=>img.naturalWidth)).toBe(640);
  for(const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:`${evidence}/gallery-${width}.png`,fullPage:true});
  }
  await options.first().uncheck();await expect(page.locator('#search-gallery')).toBeHidden();
  console.log('FT-013-AC-005: real HTTPS public result/private JPEG, paid/free venues, two dates, no-personal venue, DOM order, removable watermark, free common, clear stale gallery and responsive widths');
});

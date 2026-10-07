import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

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
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: async () => { if (window.__cameraGate) await window.__cameraGate; return { getTracks: () => [{ stop() {} }] }; } } });
    Object.defineProperty(HTMLMediaElement.prototype, 'srcObject', { configurable: true, set(v) { this.__stream = v; }, get() { return this.__stream; } });
    Object.defineProperty(HTMLMediaElement.prototype, 'readyState', { configurable: true, get: () => 4 });
    Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', { configurable: true, get: () => 310 });
    Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', { configurable: true, get: () => 360 });
    HTMLMediaElement.prototype.play = async () => { const image = new Image(); image.src = '/camera-fixture.png'; await image.decode(); window.__cameraImage = image; };
    const drawImage = CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage = function(source, ...args) { return drawImage.call(this, source instanceof HTMLVideoElement ? window.__cameraImage : source, ...args); };
  });
  await page.goto(baseURL);
  await config(page, {});
}
async function capture(page, retake = false) {
  await page.locator(retake ? '#selfie-retake' : '#selfie-viewport').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state','ready');
  await page.locator('#selfie-viewport').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state','captured');
}
async function retryAfterNoMatches(page) {
  await expect(page.locator('#search-empty')).toBeVisible();
  await page.locator('#search-empty-retry').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state','ready');
  await page.locator('#selfie-viewport').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state','captured');
}
async function config(page, values) { expect((await page.request.post(`${baseURL}/__fixture`, { data: values })).ok()).toBeTruthy(); }
async function submit(page, button = '#selfie-send') {
  const response = page.waitForResponse(r => r.url().endsWith('/api/public/search'));
  await page.locator(button).click(); return response;
}

test('AC-014 five completed empty searches pause only new search POST', async ({ page }, testInfo) => {
  const pauseCopy = 'на данный момент не удалось найти подходящих фоток, но Вы можете поискать себя  через пол часа';
  const posts = [];
  page.on('request', request => { if (request.url().endsWith('/api/public/search')) posts.push(request); });
  await page.clock.install({ time: new Date('2026-10-07T08:00:00Z') });
  await setup(page); await capture(page);
  await page.locator('#search-venues input').first().check();
  await config(page, { vector: 0 });
  const initialResult = await (await submit(page)).json();
  expect(initialResult.outcome).toBe('result');
  await config(page, { vector: 1 });
  let fifthStarted;
  for (let count = 1; count <= 5; count++) {
    if (count === 5) fifthStarted = await page.evaluate(() => Date.now());
    expect((await (await submit(page)).json()).outcome).toBe('no_matches');
    await expect(page.locator('#search-empty')).toBeVisible();
    const retryCookie = (await page.context().cookies(baseURL)).find(cookie => cookie.name === 'fm_search_retry');
    expect(retryCookie).toBeTruthy();
    expect(retryCookie.httpOnly).toBe(false);
    expect(JSON.parse(decodeURIComponent(retryCookie.value)).count).toBe(count);
    if (count < 5) {
      await expect(page.locator('#search-empty-retry')).toBeVisible();
      await retryAfterNoMatches(page);
      if (count === 2) {
        await page.reload();
        await capture(page);
        await page.locator('#search-venues input').nth(1).check();
      }
    }
  }
  expect(await page.locator('#search-empty-copy').textContent()).toBe(pauseCopy);
  await expect(page.locator('#search-empty-retry')).toBeHidden();
  const cookies = await page.context().cookies(baseURL);
  expect(cookies.filter(cookie => cookie.name === 'fm_search_retry')).toHaveLength(1);
  expect(cookies.find(cookie => cookie.name === 'fm_search_retry').httpOnly).toBe(false);
  expect(await page.evaluate(() => document.cookie.includes('fm_search_retry='))).toBe(true);
  expect(await page.evaluate(() => document.cookie.includes('fm_browser_profile='))).toBe(false);
  const fifthTime = await page.evaluate(() => Date.now());
  const deadline = JSON.parse(decodeURIComponent(cookies.find(cookie => cookie.name === 'fm_search_retry').value)).until;
  expect(deadline).toBeGreaterThanOrEqual(fifthStarted + 30 * 60 * 1000);
  expect(deadline).toBeLessThanOrEqual(fifthTime + 30 * 60 * 1000);
  expect(posts).toHaveLength(6);
  await page.screenshot({ path: testInfo.outputPath('ac-014-fifth-pause.png'), fullPage: true });
  await page.reload();
  await expect(page.locator('#search-empty-copy')).toHaveText(pauseCopy);
  await expect(page.locator('#search-empty-retry')).toBeHidden();
  expect(await page.evaluate(async id => (await fetch(`/api/public/results/${id}`, { credentials: 'same-origin' })).status, initialResult.result_id)).toBe(200);
  const orderCalls = [];
  await page.route('**/api/public/orders**', route => {
    const request = route.request();
    orderCalls.push(`${request.method()} ${new URL(request.url()).pathname}`);
    if (request.url().endsWith('/payment')) return route.fulfill({ status: 503, body: '{}' });
    if (request.method() === 'POST') return route.fulfill({ json: { id: 'new-order', total_kopecks: 100 } });
    return route.fulfill({ json: { total_kopecks: 100, archive_status: request.url().endsWith('/new-order') ? 'ready' : 'preparing', payment_status: 'pending' } });
  });
  await page.evaluate(() => sessionStorage.setItem('fm_paid_photo_order', JSON.stringify({ key: 'old', id: 'old-order', client_request_id: 'old-request' })));
  await page.reload();
  await expect(page.locator('#search-empty-copy')).toHaveText(pauseCopy);
  await expect(page.locator('#photo-download-retry')).toBeVisible();
  await page.locator('#photo-download-retry').click();
  await expect.poll(() => orderCalls.filter(call => call === 'GET /api/public/orders/old-order').length).toBe(2);
  await expect(page.locator('#photo-download-status')).toContainText('Архив готовится');
  const payment = { result_id: 'stub-result', photo_ids: ['stub-photo'], quote: { total_kopecks: 100, paid_count: 1 }, status: 'ready' };
  await page.evaluate(value => {
    const summary = document.querySelector('#photo-selection-summary');
    summary.dispatchEvent(new CustomEvent('photo-selection-change', { detail: value }));
    summary.dispatchEvent(new CustomEvent('photo-selection-download', { detail: value }));
  }, payment);
  await expect(page.locator('#photo-payment-form')).toBeVisible();
  await page.locator('#photo-payment-email').fill('visitor@example.test');
  const paymentRequest = page.waitForRequest(request => request.url().endsWith('/api/public/orders/new-order/payment'));
  await page.locator('#photo-payment-form button').click();
  expect((await paymentRequest).method()).toBe('POST');
  expect(orderCalls).toContain('POST /api/public/orders');
  expect(posts).toHaveLength(6);
  await page.evaluate(() => { const send = document.querySelector('#selfie-send'); send.disabled = false; send.click(); });
  expect(posts).toHaveLength(6);
  await page.clock.fastForward(deadline - await page.evaluate(() => Date.now()) - 1);
  await page.evaluate(() => { const send = document.querySelector('#selfie-send'); send.disabled = false; send.click(); });
  expect(posts).toHaveLength(6);
  await page.clock.fastForward(1);
  await expect(page.locator('#search-empty')).toBeHidden();
  expect((await page.context().cookies(baseURL)).some(cookie => cookie.name === 'fm_search_retry')).toBe(false);
  await capture(page);
  await page.locator('#search-venues input').first().check();
  expect((await (await submit(page)).json()).outcome).toBe('no_matches');
  expect(JSON.parse(decodeURIComponent((await page.context().cookies(baseURL)).find(cookie => cookie.name === 'fm_search_retry').value)).count).toBe(1);
});

test('AC-014 other outcomes do not spend retries and a result resets them', async ({ page }) => {
  await setup(page); await capture(page);
  await page.locator('#search-venues input').first().check();
  await config(page, { vector: 0 });
  expect((await (await submit(page)).json()).outcome).toBe('result');
  await config(page, { vector: 1 });
  expect((await (await submit(page)).json()).outcome).toBe('no_matches');
  const count = async () => {
    const cookie = (await page.context().cookies(baseURL)).find(item => item.name === 'fm_search_retry');
    return cookie ? JSON.parse(decodeURIComponent(cookie.value)).count : 0;
  };
  expect(await count()).toBe(1);
  await page.evaluate(() => { window.__cameraGate = { then: (_, reject) => reject(new DOMException('denied', 'NotAllowedError')) }; });
  await page.locator('#search-empty-retry').click();
  await expect(page.locator('#selfie-status')).toContainText('Доступ к камере не разрешён');
  expect(await count()).toBe(1);
  await page.evaluate(() => { window.__cameraGate = null; });
  await capture(page);
  for (const outcome of ['busy', 'deadline', 'retake_required', 'confirmation_required', 'face_denied']) {
    await page.route('**/api/public/search', route => route.fulfill({ json: { schema_version: 1, outcome } }));
    expect((await (await submit(page)).json()).outcome).toBe(outcome);
    expect(await count()).toBe(1);
    await page.unroute('**/api/public/search');
  }
  await page.route('**/api/public/search', route => route.fulfill({ status: 500, body: '{}' }));
  expect((await submit(page)).status()).toBe(500);
  expect(await count()).toBe(1);
  await page.unroute('**/api/public/search');
  await page.route('**/api/public/search', route => route.abort());
  await page.locator('#selfie-send').click();
  await expect(page.locator('#search-status')).toContainText('Не удалось');
  expect(await count()).toBe(1);
  await page.unroute('**/api/public/search');
  await page.route('**/api/public/search', route => route.fulfill({ json: { schema_version: 1, outcome: 'result', result_id: 'stub', personal_count: 1, venues: [] } }));
  expect((await (await submit(page)).json()).outcome).toBe('result');
  expect(await count()).toBe(0);
  await page.unroute('**/api/public/search');
  expect((await (await submit(page)).json()).outcome).toBe('no_matches');
  expect(await count()).toBe(1);
});

test('AC-014 late sixth no_matches in another tab preserves the fifth pause', async ({ page, context }) => {
  await setup(page); await capture(page);
  await page.locator('#search-venues input').first().check();
  const other = await context.newPage();
  await setup(other); await capture(other);
  await other.locator('#search-venues input').first().check();
  await context.addCookies([{ name: 'fm_search_retry', value: encodeURIComponent(JSON.stringify({ count: 4, until: 0 })), url: baseURL }]);
  const cookieState = async () => {
    const cookie = (await context.cookies(baseURL)).find(item => item.name === 'fm_search_retry');
    return cookie ? JSON.parse(decodeURIComponent(cookie.value)) : null;
  };
  const pending = [];
  await context.route('**/api/public/search', route => { pending.push(route); });
  await page.locator('#selfie-send').click();
  await other.locator('#selfie-send').click();
  await expect.poll(() => pending.length).toBe(2);
  expect(await cookieState()).toEqual({ count: 4, until: 0 });

  await pending[0].fulfill({ json: { schema_version: 1, outcome: 'no_matches' } });
  await expect.poll(async () => (await cookieState())?.count).toBe(5);
  const fifth = await cookieState();
  expect(fifth.until).toBeGreaterThan(Date.now());
  await pending[1].fulfill({ json: { schema_version: 1, outcome: 'no_matches' } });
  await expect(other.locator('#search-empty-copy')).toHaveText('на данный момент не удалось найти подходящих фоток, но Вы можете поискать себя  через пол часа');
  expect(await cookieState()).toEqual(fifth);
  await other.evaluate(() => { const send = document.querySelector('#selfie-send'); send.disabled = false; send.click(); });
  expect(pending).toHaveLength(2);
});

test('AC-012 completed no_matches shows exact dedicated screen and retry', async ({ page }, testInfo) => {
  const copy = 'К сожалению, нам не удалось найти  Вас на прошедших мероприятиях. Возможно, Вы посещали нас слишком давно? Если фото с Вами были сделаны не позднее 3х месяцев назад, попробуйте сделать селфи еще раз, выберите светлое место, так нам будет легче рассмотреть ваше лицо';
  const searches = [];
  page.on('request', request => { if (request.url().endsWith('/api/public/search')) searches.push(request); });
  await setup(page); await capture(page);
  await page.locator('#search-venues input').first().check();
  await config(page, { vector: 0 });
  expect((await (await submit(page)).json()).outcome).toBe('result');
  await config(page, { vector: 1 });
  expect((await (await submit(page)).json()).outcome).toBe('no_matches');
  const screen = page.locator('#search-empty');
  await expect(screen).toBeVisible();
  await expect(page.locator('.fm-selfie-panel')).toBeHidden();
  expect(await page.locator('#search-empty-copy').textContent()).toBe(copy);
  await expect(screen.getByRole('button', { name: 'Попробовать еще' })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('ac-012-empty.png'), fullPage: true });
  const beforeRetry = searches.length;
  await screen.getByRole('button', { name: 'Попробовать еще' }).click();
  await expect(screen).toBeHidden();
  await expect(page.locator('.fm-selfie-panel')).toBeVisible();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'ready');
  await expect(page.locator('fieldset.fm-search-selection')).toBeHidden();
  expect(searches).toHaveLength(beforeRetry);
  await page.locator('#selfie-viewport').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'captured');
  await expect(page.locator('fieldset.fm-search-selection')).toBeVisible();
  await page.locator('#search-venues input').nth(1).check();
  await config(page, { fail: true });
  expect((await submit(page)).status()).toBe(500);
  await expect(page.locator('#search-status')).toContainText('Не удалось');
  await expect(screen).toBeHidden();
  expect(searches).toHaveLength(beforeRetry + 1);
  expect(searches[1].postData()).not.toContain('date');
});

test('AC-011 venues require current captured selfie and POST waits for Find', async ({ page }, testInfo) => {
  const searches = [];
  page.on('request', request => { if (request.url().endsWith('/api/public/search')) searches.push(request); });
  await setup(page);
  await expect(page.locator('#search-venues input')).toHaveCount(4);
  const fieldset = page.locator('fieldset.fm-search-selection');
  const states = [];
  async function record(label) {
    states.push({ label, ...await page.evaluate(async () => ({
      state: document.querySelector('#selfie-viewport').dataset.state || 'idle',
      hidden: document.querySelector('fieldset.fm-search-selection').hidden,
      disabled: document.querySelector('fieldset.fm-search-selection').disabled,
      checkedInputs: document.querySelectorAll('#search-venues input:checked').length,
      enabledInputs: [...document.querySelectorAll('#search-venues input')].filter(input => !input.disabled).length,
      currentJpeg: (await import('/client/site-selfie.js')).getCurrentSelfie()?.type === 'image/jpeg',
    })), posts: searches.length });
  }
  await record('idle');
  await expect(fieldset).toBeHidden();
  await expect(fieldset).toHaveJSProperty('disabled', true);
  await page.evaluate(() => { window.__cameraGate = new Promise(resolve => { window.__releaseCamera = resolve; }); });
  await page.locator('#selfie-viewport').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'opening');
  await record('opening');
  await expect(fieldset).toBeHidden();
  await page.evaluate(() => window.__releaseCamera());
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'ready');
  await record('ready');
  await expect(fieldset).toBeHidden();
  await page.clock.pauseAt(new Date('2026-10-07T08:00:00Z'));
  await page.evaluate(() => document.querySelector('#selfie-viewport').click());
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'capturing');
  await record('capturing');
  await expect(fieldset).toBeHidden();
  await page.clock.runFor(75);
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'captured');
  await record('captured');
  await expect(fieldset).toBeVisible();
  await expect(fieldset).toHaveJSProperty('disabled', false);
  await expect(page.locator('#selfie-send')).toBeDisabled();
  const inputs = page.locator('#search-venues input');
  await inputs.nth(0).check();
  await expect(page.locator('#selfie-send')).toBeEnabled();
  await record('one-selected');
  await inputs.nth(1).check(); await inputs.nth(2).check();
  await expect(page.locator('#selfie-send')).toBeEnabled();
  await expect(inputs.nth(3)).toBeDisabled();
  await record('three-selected');
  await inputs.nth(2).uncheck();
  await expect(inputs.nth(3)).toBeEnabled();
  await record('two-selected');
  expect(searches).toHaveLength(0);
  await page.evaluate(() => { window.__cameraGate = new Promise(resolve => { window.__releaseCamera = resolve; }); });
  await page.locator('#selfie-retake').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'opening');
  await record('retake-opening');
  await expect(fieldset).toBeHidden();
  await expect(fieldset).toHaveJSProperty('disabled', true);
  await expect(page.locator('#selfie-send')).toBeDisabled();
  await page.evaluate(() => window.__releaseCamera());
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'ready');
  await record('retake-ready');
  await expect(fieldset).toBeHidden();
  await page.evaluate(() => document.querySelector('#selfie-viewport').click());
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'capturing');
  await record('retake-capturing');
  await expect(fieldset).toBeHidden();
  await page.clock.runFor(75);
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'captured');
  await record('recaptured');
  await expect(fieldset).toBeVisible();
  expect(searches).toHaveLength(0);
  await page.evaluate(() => { const original = fetch; window.fetch = (url, init) => { if (String(url).endsWith('/api/public/search')) window.__sentSelfie = init.body.get('selfie'); return original(url, init); }; });
  const response = await submit(page);
  expect(response.status()).toBe(200);
  await record('after-Find');
  expect(searches).toHaveLength(1);
  expect(await page.evaluate(async () => {
    const current = (await import('/client/site-selfie.js')).getCurrentSelfie();
    const sent = window.__sentSelfie;
    if (current?.type !== 'image/jpeg' || sent?.type !== 'image/jpeg' || current.size !== sent.size) return false;
    const [a, b] = await Promise.all([current.arrayBuffer(), sent.arrayBuffer()]);
    const sentBytes = new Uint8Array(b);
    return [...new Uint8Array(a)].every((byte, index) => byte === sentBytes[index]);
  })).toBe(true);
  await writeFile(testInfo.outputPath('ac-011-state-network.json'), JSON.stringify({ states, selectedAtSubmit: await page.locator('#search-venues input:checked').count(), postMethod: searches[0].method(), postStatus: response.status() }, null, 2));
});

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
  await expect(page.locator('#search-summary')).toBeHidden();
  await retryAfterNoMatches(page);
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
  await retryAfterNoMatches(page);
  await config(page,{vector:3}); await submit(page);
  await retryAfterNoMatches(page);
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

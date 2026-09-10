import { readFile } from 'node:fs/promises';
import { test, expect } from '@playwright/test';

const origin = 'https://promo-replay.test';

test('local duration persists; latest Promo replays without search or ACK and recovers from missing media', async ({ page }) => {
  let media;
  let mediaUnavailable = false;
  const requests = [];
  await page.route(`${origin}/**`, async route => {
    const pathname = new URL(route.request().url()).pathname;
    requests.push({ pathname, method: route.request().method() });
    if (pathname === '/client/blazeface.js') return route.fulfill({ contentType: 'text/javascript', body: 'export async function createBlazeFaceDetector(){return {detect:async()=>[],close(){}}} export async function detectReferenceSeries(){return []}' });
    if (pathname === '/api/promo/display/config') return route.fulfill({ json: { schema_version: 1, result_display_ms: 60_000, success_cooldown_ms: 1000 } });
    if (pathname.startsWith('/api/promo/media/')) return mediaUnavailable
      ? route.fulfill({ status: 503 })
      : route.fulfill({ contentType: 'image/jpeg', body: media });
    if (pathname === '/api/promo/sessions/synthetic-replay/display' || pathname.endsWith('/client-timing')) return route.fulfill({ json: {} });
    if (pathname.startsWith('/api/')) return route.fulfill({ status: 503 });
    const file = pathname === '/' ? '/client/index.html' : pathname;
    try {
      await route.fulfill({ contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html', body: await readFile(new URL(`../..${file}`, import.meta.url)) });
    } catch { await route.fulfill({ status: 404 }); }
  });
  await page.addInitScript(() => {
    localStorage.setItem('face-moment.display-client-token', 'synthetic-replay-token');
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
      enumerateDevices: async () => [], getUserMedia: async () => { throw new Error('No physical camera in QA'); }, addEventListener() {},
    } });
  });
  await page.goto(`${origin}/#advertising`);
  const replay = page.getByRole('button', { name: 'Фотки вновь', exact: true });
  await expect(replay).toBeDisabled();
  await page.goto(`${origin}/#configuration`);
  await page.locator('#promo-display-seconds').fill('1');
  await page.getByRole('button', { name: 'Сохранить время показа', exact: true }).click();
  await expect(page.locator('.promo-duration-panel [role="status"]')).toContainText('Сохранено: 1 сек.');
  await page.reload();
  await expect(page.locator('#promo-display-seconds')).toHaveValue('1');
  media = Buffer.from(await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 40;
    canvas.getContext('2d').fillRect(0, 0, 40, 40);
    return canvas.toDataURL('image/jpeg').split(',')[1];
  }), 'base64');
  await page.evaluate(() => {
    const parts = ['photo-1', 'photo-2', 'photo-3', 'photo-4', 'text', 'qr'];
    localStorage.setItem('face-moment.promo-layout.v1', JSON.stringify({ version: 1, textScale: 1,
      parts: Object.fromEntries(parts.map((part, index) => [part, { x: 20 + index % 3 * 30, y: index < 3 ? 30 : 70, w: 15, h: 20, angle: index }])) }));
  });
  await page.goto(`${origin}/#advertising`);
  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent('face-moment:attempt-request-start', { detail: { attemptId: 'synthetic-replay', captureId: 'synthetic-capture' } }));
    window.dispatchEvent(new CustomEvent('face-moment:attempt-response', { detail: {
      attemptId: 'synthetic-replay', captureId: 'synthetic-capture', timing: { referenceSeriesReadyMonotonicMs: performance.now() },
      response: { status: 200, json: async () => ({ schema_version: 1, attempt_id: 'synthetic-replay', outcome: 'result', result: {
        session_id: 'synthetic-replay', n: 4, qr_url: `${location.origin}/q?ticket=synthetic-replay`, qr_first_open_expires_at: '2020-01-01T00:00:00Z',
        teasers: [1, 2, 3, 4].map(i => ({ photo_id: `synthetic-photo-${i}`, media_url: `${location.origin}/api/promo/media/${i}` })),
      } }) },
    } }));
  });
  const card = page.locator('.promo-card');
  await expect(card).toBeVisible();
  await expect(card.locator('.promo-teaser')).toHaveCount(4);
  await expect(card.locator('.promo-replay-notice')).toHaveCount(0);
  const snapshot = () => card.evaluate(el => ({ qr: el.querySelector('[data-qr-content]').getAttribute('data-qr-content'), parts: [...el.querySelectorAll('[data-layout-part]')].map(part => ({ id: part.dataset.layoutPart, style: part.getAttribute('style') })) }));
  const original = await snapshot();
  await expect.poll(() => requests.filter(r => r.pathname.endsWith('/display') && r.method === 'PUT').length).toBe(1);
  await expect(card).toHaveCount(0, { timeout: 3000 });
  await expect(replay).toBeEnabled();
  const beforeReplay = requests.length;
  for (let repeat = 0; repeat < 2; repeat++) {
    const beforeThisReplay = requests.length;
    await replay.click();
    await expect(card).toBeVisible();
    const visibleAt = Date.now();
    await expect(card.locator('.promo-teaser')).toHaveCount(4);
    expect(await snapshot()).toEqual(original);
    expect(requests.slice(beforeThisReplay).filter(r => r.pathname.startsWith('/api/promo/media/')).map(r => r.pathname).sort())
      .toEqual([1, 2, 3, 4].map(i => `/api/promo/media/${i}`));
    await expect(card.locator('.promo-replay-notice')).toContainText('Срок действия QR истёк');
    await expect(card).toHaveCount(0, { timeout: 3000 });
    expect(Date.now() - visibleAt).toBeGreaterThan(600);
    expect(Date.now() - visibleAt).toBeLessThan(2200);
    await expect(replay).toBeEnabled();
  }
  expect(requests.slice(beforeReplay).filter(r => r.pathname.endsWith('/attempts') || r.pathname.endsWith('/display'))).toEqual([]);
  mediaUnavailable = true;
  await replay.click();
  await expect(page.locator('.advertising-card [role="status"]')).toContainText('Не удалось повторно загрузить');
  await expect(card).toHaveCount(0);
  await expect(replay).toBeEnabled();
  mediaUnavailable = false;
  await replay.click();
  await expect(card).toBeVisible();
  await expect(card.locator('.promo-teaser')).toHaveCount(4);
  await expect(card).toHaveCount(0, { timeout: 3000 });
  await expect(replay).toBeEnabled();
  expect(requests.filter(r => r.pathname.endsWith('/display') && r.method === 'PUT')).toHaveLength(1);
  expect(requests.filter(r => r.pathname.endsWith('/attempts'))).toHaveLength(0);
});

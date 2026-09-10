import { readFile } from 'node:fs/promises';
import { test, expect } from '@playwright/test';

const origin = 'https://promo-editor.test';
const storageKey = 'face-moment.promo-layout.v1';

test('configuration editor saves, restores and applies local layout to a real result', async ({ page }) => {
  await page.setViewportSize({ width: 1450, height: 833 });
  await page.route(`${origin}/**`, async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/client/blazeface.js') {
      return route.fulfill({ contentType: 'text/javascript', body: 'export async function createBlazeFaceDetector(){return {detect:async()=>[],close(){}}} export async function detectReferenceSeries(){return []}' });
    }
    if (pathname.startsWith('/api/')) return route.fulfill({ status: 503 });
    const file = pathname === '/' ? '/client/index.html' : pathname;
    try {
      await route.fulfill({ contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html', body: await readFile(new URL(`../..${file}`, import.meta.url)) });
    } catch { await route.fulfill({ status: 404 }); }
  });
  await page.addInitScript(() => Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { enumerateDevices: async () => [], getUserMedia: async () => { throw new Error('No physical camera in QA'); }, addEventListener() {} },
  }));
  await page.goto(`${origin}/#configuration`);
  const open = () => page.getByRole('button', { name: 'Поправить расположение фоток' }).click();
  await open();
  await expect(page.locator('.promo-editable')).toHaveCount(6);
  await page.getByText('Размер и поворот выбранного объекта', { exact: true }).click();
  await page.getByLabel('Поворот объекта', { exact: true }).fill('15');
  await page.getByLabel('Объект', { exact: true }).selectOption('3');
  const photo = page.locator('.promo-editable').nth(3);
  const position = await photo.evaluate(el => [el.style.left, el.style.top]);
  await page.getByLabel('Ширина объекта', { exact: true }).fill('35');
  await page.getByLabel('Высота объекта', { exact: true }).fill('40');
  expect(await photo.evaluate(el => [el.style.left, el.style.top])).toEqual(position);
  await page.getByLabel('Объект', { exact: true }).selectOption('5');
  for (const name of ['Ширина объекта', 'Высота объекта']) {
    await page.getByLabel(name, { exact: true }).fill('25');
    const size = await page.locator('.promo-qr-panel').evaluate(el => [el.offsetWidth, el.offsetHeight]);
    expect(size[0]).toEqual(size[1]);
  }
  await page.getByLabel('Размер текста', { exact: true }).selectOption('1.4');
  await page.getByRole('button', { name: 'Сохранить дизайн', exact: true }).click();
  await expect(page.locator('.promo-editor')).toHaveCount(0);
  await expect(page).toHaveURL(/#configuration$/);
  const saved = await page.evaluate(key => localStorage.getItem(key), storageKey);
  expect(JSON.parse(saved).parts['photo-1'].angle).toBe(15);
  await page.reload();
  await open();
  await expect(page.getByLabel('Размер текста', { exact: true })).toHaveValue('1.4');
  expect(await page.evaluate(key => localStorage.getItem(key), storageKey)).toBe(saved);
  await page.getByLabel('Размер текста', { exact: true }).selectOption('0.75');
  await page.getByRole('button', { name: 'Отмена', exact: true }).click();
  expect(await page.evaluate(key => localStorage.getItem(key), storageKey)).toBe(saved);

  const applied = await page.evaluate(async () => {
    const { PromoDisplayController } = await import('/client/promo-display.js');
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 20;
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
    const container = document.createElement('div'); document.body.append(container);
    const controller = new PromoDisplayController({ container, fetchImpl: async () => new Response(blob, { headers: { 'Content-Type': 'image/jpeg' } }) });
    const result = await controller.showResult({ attemptId: 'synthetic-layout', result: { session_id: 'synthetic-layout', n: 4,
      teasers: [0, 1, 2, 3].map(i => ({ photo_id: `synthetic-${i}`, media_url: `${location.origin}/api/promo/media/${i}` })),
      qr_url: `${location.origin}/q?ticket=synthetic-layout`, qr_first_open_expires_at: '2099-01-01T00:00:00Z' } });
    const elements = [...container.querySelectorAll('[data-layout-part]')].map(el => ({ part: el.dataset.layoutPart, left: el.style.left, top: el.style.top, transform: el.style.transform }));
    container.remove();
    return { state: result.state, elements };
  });
  expect(applied.state).toBe('result');
  expect(applied.elements).toHaveLength(6);
  for (const element of applied.elements) {
    const part = JSON.parse(saved).parts[element.part];
    expect(parseFloat(element.left)).toBeCloseTo(part.x, 3);
    expect(parseFloat(element.top)).toBeCloseTo(part.y, 3);
    expect(element.transform).toContain(`rotate(${part.angle}deg)`);
  }

  await open();
  await page.evaluate(() => { Storage.prototype.setItem = () => { throw new DOMException('QA storage denied', 'SecurityError'); }; });
  await page.getByRole('button', { name: 'Сохранить дизайн', exact: true }).click();
  await expect(page.locator('.promo-editor')).toHaveCount(1);
  await expect(page.locator('.promo-editor-actions [role="status"]')).toContainText('Не удалось сохранить');
  await page.getByRole('button', { name: 'Отмена', exact: true }).click();
});

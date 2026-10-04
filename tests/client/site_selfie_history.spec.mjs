import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { expect, test } from '@playwright/test';

const ROOT = path.resolve(import.meta.dirname, '../..');
const ORIGIN = 'https://selfie-history.test';
const DB = 'face-moment-selfies';
const STORE = 'captures';
const ARTIFACTS = process.env.SELFIE_PAIR_OUTPUT;

async function setup(page, { size = 'large', denied = false } = {}) {
  await page.route(`${ORIGIN}/**`, async route => {
    const pathname = new URL(route.request().url()).pathname;
    const relative = pathname === '/' ? 'client/site.html' : pathname.slice(1);
    if (!relative.startsWith('client/') && !relative.startsWith('tests/client/fixtures/')) {
      await route.fulfill({ status: 404, body: 'not found' }); return;
    }
    const type = relative.endsWith('.html') ? 'text/html' : relative.endsWith('.js') ? 'text/javascript' : relative.endsWith('.css') ? 'text/css' : 'image/png';
    await route.fulfill({ contentType: type, body: await readFile(path.join(ROOT, relative)) });
  });
  await page.addInitScript(({ size, denied }) => {
    globalThis.__cameraSize = size === 'large' ? [1240, 1440] : [310, 360];
    globalThis.__encodings = [];
    globalThis.__uploads = [];
    const nativeFetch = globalThis.fetch;
    globalThis.fetch = (...args) => { globalThis.__uploads.push(String(args[0])); return nativeFetch(...args); };
    const nativeToBlob = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {
      globalThis.__encodings.push({ width: this.width, height: this.height, type, quality });
      return nativeToBlob.call(this, callback, type, quality);
    };
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }) } });
    Object.defineProperty(HTMLMediaElement.prototype, 'srcObject', { configurable: true, get() { return this.__stream; }, set(value) { this.__stream = value; } });
    Object.defineProperty(HTMLMediaElement.prototype, 'readyState', { configurable: true, get: () => HTMLMediaElement.HAVE_ENOUGH_DATA });
    Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', { configurable: true, get: () => globalThis.__cameraSize[0] });
    Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', { configurable: true, get: () => globalThis.__cameraSize[1] });
    HTMLMediaElement.prototype.play = async () => {
      const image = new Image(); image.src = `/tests/client/fixtures/selfie-portrait-${size}.png`;
      await image.decode(); globalThis.__cameraImage = image;
    };
    const drawImage = CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage = function(source, ...args) {
      return drawImage.call(this, source instanceof HTMLVideoElement ? globalThis.__cameraImage : source, ...args);
    };
    if (denied) indexedDB.open = () => { throw new DOMException('fixture unavailable', 'SecurityError'); };
  }, { size, denied });
  await page.goto(`${ORIGIN}/`);
}

async function capture(page) {
  await page.locator('#selfie-viewport').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'ready');
  await page.locator('#selfie-viewport').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'captured');
}

async function history(page) {
  return page.evaluate(async ({ DB, STORE }) => {
    const dbs = await indexedDB.databases();
    if (!dbs.some(db => db.name === DB)) return [];
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB);
      request.onsuccess = () => {
        const db = request.result;
        const transaction = db.transaction(STORE, 'readonly');
        const records = transaction.objectStore(STORE).getAll();
        records.onsuccess = async () => {
          const result = await Promise.all(records.result.map(async row => {
            const bitmap = await createImageBitmap(row.blob);
            const info = { id: row.id, capturedAt: row.capturedAt, width: bitmap.width, height: bitmap.height, type: row.blob.type, bytes: row.blob.size };
            bitmap.close(); return info;
          }));
          db.close(); resolve(result);
        };
        records.onerror = () => reject(records.error);
      };
      request.onerror = () => reject(request.error);
    });
  }, { DB, STORE });
}

test('camera JPEG downscales/no-upscale q0.85 and retains every capture across reload', async ({ page }) => {
  await setup(page);
  await capture(page);
  expect(await page.evaluate(() => globalThis.__encodings[0])).toEqual({ width: 827, height: 960, type: 'image/jpeg', quality: .85 });
  const first = await history(page);
  expect(first).toHaveLength(1);
  expect(first[0]).toMatchObject({ width: 827, height: 960, type: 'image/jpeg' });
  if (ARTIFACTS) {
    await mkdir(ARTIFACTS, { recursive: true });
    const bytes = await page.evaluate(async () => [...new Uint8Array(await (await fetch(document.querySelector('#selfie-preview').src)).arrayBuffer())]);
    await writeFile(path.join(ARTIFACTS, 'selfie-browser-960-q085.jpg'), Buffer.from(bytes));
    await writeFile(path.join(ARTIFACTS, 'selfie-original-large.png'), await readFile(path.join(ROOT, 'tests/client/fixtures/selfie-portrait-large.png')));
  }
  await page.locator('#selfie-retake').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'ready');
  await page.evaluate(() => { globalThis.__cameraSize = [310, 360]; });
  await page.locator('#selfie-viewport').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'captured');
  expect(await page.evaluate(() => globalThis.__encodings[1])).toEqual({ width: 310, height: 360, type: 'image/jpeg', quality: .85 });
  expect(await history(page)).toHaveLength(2);
  expect(await page.evaluate(() => globalThis.__uploads.filter(url => url.includes('/api/public/search')))).toEqual([]);
  expect(await page.locator('input[type=file]').count()).toBe(0);
  // TASK-125 owns search UI. Here a consumer sends only the current Blob;
  // denied/failed/success responses have no access to history writes/deletes.
  for (const [code, outcome] of [[403, 'face_denied'], [500, 'request_failure'], [200, 'success']]) {
    await page.route(`${ORIGIN}/api/public/search`, route => route.fulfill({
      status: code, contentType: 'application/json', body: JSON.stringify({ outcome }),
    }));
    const consumed = await page.evaluate(async () => {
      const { getCurrentSelfie } = await import('/client/site-selfie.js');
      const current = getCurrentSelfie();
      const form = new FormData(); form.append('selfie', current, 'selfie.jpg');
      const response = await fetch('/api/public/search', { method: 'POST', body: form });
      return { outcome: (await response.json()).outcome, currentPreserved: getCurrentSelfie() === current };
    });
    expect(consumed).toEqual({ outcome, currentPreserved: true });
    expect(await history(page)).toHaveLength(2);
  }
  await page.reload();
  const reloaded = await history(page);
  expect(reloaded).toHaveLength(2);
  expect(reloaded.map(row => row.id)).toEqual([1, 2]);
  expect(reloaded[1]).toMatchObject({ width: 310, height: 360, type: 'image/jpeg' });
  const current = await page.evaluate(async () => (await import('/client/site-selfie.js')).getCurrentSelfie());
  expect(current).toBeNull(); // History never becomes search input automatically.
});

test('unavailable history warns while current camera JPEG remains usable', async ({ page }) => {
  await setup(page, { denied: true, size: 'small' });
  await capture(page);
  await expect(page.locator('#selfie-storage-warning')).toBeVisible();
  await expect(page.locator('#selfie-storage-warning')).toContainText('не сохранён');
  const current = await page.evaluate(async () => {
    const blob = (await import('/client/site-selfie.js')).getCurrentSelfie();
    const image = await createImageBitmap(blob);
    return { type: blob.type, width: image.width, height: image.height };
  });
  expect(current).toEqual({ type: 'image/jpeg', width: 310, height: 360 });
});

test('quota abort preserves older JPEGs and does not cancel current capture', async ({ page }) => {
  await setup(page);
  await capture(page);
  const previous = await history(page);
  expect(previous).toHaveLength(1);
  await page.evaluate(() => {
    const nativeAdd = IDBObjectStore.prototype.add;
    IDBObjectStore.prototype.add = function(...args) {
      if (this.name === 'captures') {
        throw new DOMException('fixture quota exceeded', 'QuotaExceededError');
      }
      return nativeAdd.apply(this, args);
    };
  });
  await page.locator('#selfie-retake').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'ready');
  await page.locator('#selfie-viewport').click();
  await expect(page.locator('#selfie-viewport')).toHaveAttribute('data-state', 'captured');
  await expect(page.locator('#selfie-storage-warning')).toBeVisible();
  expect(await history(page)).toEqual(previous);
  expect(await page.evaluate(async () => (await import('/client/site-selfie.js')).getCurrentSelfie() instanceof Blob)).toBe(true);
});

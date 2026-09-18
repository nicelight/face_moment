import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';

const spaId = '00000000-0000-0000-0000-000000000001';
const photoId = '00000000-0000-0000-0000-000000000002';
const uploadPage = execFileSync('.venv/bin/python', ['-c', `
from face_moment.inventory.http import _photo_upload_page_html
from face_moment.platform.staff_presentation import staff_document
print(staff_document(_photo_upload_page_html(), 'photo-upload'))
`], { encoding: 'utf8' });

test.beforeEach(async ({ page }) => {
  await page.route('https://staff.test/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/staff/photo-upload') {
      return route.fulfill({ contentType: 'text/html', body: uploadPage });
    }
    if (url.pathname.startsWith('/client/')) {
      const contentType = url.pathname.endsWith('.css') ? 'text/css' : 'text/javascript';
      return route.fulfill({ contentType, body: await readFile(`.${url.pathname}`) });
    }
    if (url.pathname === '/api/staff/session') {
      return route.fulfill({ json: { username: 'Fixture', role: 'photographer' } });
    }
    if (url.pathname === '/api/inventory/ingest-targets') {
      return route.fulfill({ json: {
        schema_version: 1,
        spas: [{ spa_id: spaId, name: 'Площадка 1', timezone: 'Asia/Dushanbe' }],
      } });
    }
    return route.fulfill({ status: 503, body: '' });
  });
});

async function prepareUpload(page, files) {
  await page.goto('https://staff.test/staff/photo-upload');
  await page.locator('#spa-id').selectOption(spaId);
  await page.locator('#photos').setInputFiles(files);
  await page.getByRole('button', { name: /Загрузить фотографии/ }).click();
}

test('locks file selection and submit while transfer progress moves from one of two to complete', async ({ page }) => {
  let releaseSecondUpload;
  const secondUploadGate = new Promise(resolve => { releaseSecondUpload = resolve; });
  let requestCount = 0;
  await page.route('https://staff.test/api/inventory/photos', async route => {
    requestCount += 1;
    if (route.request().postData()?.includes('filename="two.jpg"')) {
      await secondUploadGate;
      return route.fulfill({ status: 422, json: { detail: { message: 'Некорректный JPEG' } } });
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      schema_version: 1, outcome: 'duplicate', warnings: [],
    }) });
  });

  await prepareUpload(page, [
    { name: 'one.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('one') },
    { name: 'two.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('two') },
  ]);

  await expect.poll(() => requestCount).toBe(2);
  await expect(page.locator('#photos')).toBeDisabled();
  await expect(page.locator('#upload-submit')).toBeDisabled();
  await expect(page.locator('#spa-id')).toBeEnabled();
  await expect(page.locator('#visit-date')).toBeEnabled();
  await expect(page.locator('#upload-progress-label')).toHaveText('Завершено 1 из 2');
  await expect(page.locator('#upload-progress')).toHaveAttribute('aria-valuetext', 'Завершено 1 из 2');
  await expect(page.locator('#upload-progress')).toHaveJSProperty('value', 1);
  await expect(page.locator('#upload-results .fm-upload-indicator.is-uploading')).toHaveCount(1);

  releaseSecondUpload();
  await expect(page.locator('#upload-progress-label')).toHaveText('Завершено 2 из 2');
  await expect(page.locator('#upload-results .fm-upload-indicator:not([hidden])')).toHaveCount(0);
  await expect(page.locator('#photos')).toBeEnabled();
  await expect(page.locator('#upload-submit')).toBeEnabled();
});

test('keeps an accepted row pulsing through processing, then settles it at a terminal result', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  let releaseProcessing;
  const processingGate = new Promise(resolve => { releaseProcessing = resolve; });
  let processingRequests = 0;
  await page.route('https://staff.test/api/inventory/photos', async route => {
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({
      schema_version: 1,
      outcome: 'accepted',
      photo: { photo_id: photoId },
      warnings: [],
    }) });
  });
  await page.route(`https://staff.test/api/inventory/photos/${photoId}/processing`, async route => {
    processingRequests += 1;
    await processingGate;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      schema_version: 1,
      photo_id: photoId,
      processing_status: 'ready',
      searchable: true,
    }) });
  });

  await prepareUpload(page, [
    { name: 'accepted.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('accepted') },
  ]);

  await expect.poll(() => processingRequests).toBe(1);
  await expect(page.locator('#upload-progress-label')).toHaveText('Завершено 1 из 1');
  await expect(page.locator('#photos')).toBeEnabled();
  await expect(page.locator('#upload-submit')).toBeEnabled();
  await expect(page.locator('#upload-results .fm-upload-indicator.is-processing')).toHaveCount(1);
  await expect.poll(() => page.locator('#upload-results .fm-upload-indicator').evaluate(element => getComputedStyle(element).animationName)).toBe('none');

  releaseProcessing();
  await expect(page.locator('#upload-results strong')).toHaveText('searchable');
  await expect(page.locator('#upload-results .fm-upload-indicator:not([hidden])')).toHaveCount(0);
});

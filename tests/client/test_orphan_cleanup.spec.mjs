import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';

const venue = '00000000-0000-4000-8000-000000000001';
const html = execFileSync('uv', ['run', '--locked', 'python', '-c', `
import uuid
from face_moment.inventory.staff_media_http import staff_media_page_html
from face_moment.platform.staff_presentation import staff_document
print(staff_document(staff_media_page_html(uuid.UUID('${venue}'), 'Тестовая площадка', can_diagnose=True), 'venue-media'))
`], { encoding: 'utf8' });

test('operator confirms orphan cleanup; cancel does not send a request', async ({ page }) => {
  let cleanupRequests = 0;
  let finishCleanup;
  let failCleanup = false;
  const cleanupGate = new Promise(resolve => { finishCleanup = resolve; });
  await page.route('https://staff.test/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/staff/venue-media') return route.fulfill({ contentType: 'text/html', body: html });
    if (path.startsWith('/client/')) return route.fulfill({
      contentType: path.endsWith('.js') ? 'text/javascript' : 'text/css', body: await readFile('.' + path),
    });
    if (path === '/api/staff/session') return route.fulfill({ json: { username: 'Оператор', role: 'operator' } });
    if (path === '/api/inventory/venue-media') return route.fulfill({ json: { photos: [] } });
    if (path === '/api/diagnostics/people') return route.fulfill({ json: { people: [] } });
    if (path === '/api/diagnostics/captures') return route.fulfill({ json: { attempts: [] } });
    if (path === '/api/inventory/orphan-originals/cleanup') {
      cleanupRequests += 1;
      expect(route.request().method()).toBe('POST');
      await cleanupGate;
      if (failCleanup) return route.fulfill({ status: 503 });
      return route.fulfill({ json: { schema_version: 1, scanned: 12, deleted: 3 } });
    }
    return route.fulfill({ status: 404 });
  });

  await page.goto(`https://staff.test/staff/venue-media?spa_id=${venue}`);
  const open = page.getByRole('button', { name: 'Запустить очистку битых файлов' });
  await open.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Это может занять до 30 минут, сервер в это время будет практически неработоспособен');
  await dialog.getByRole('button', { name: 'Отмена' }).click();
  await expect(dialog).not.toBeVisible();
  expect(cleanupRequests).toBe(0);

  await open.click();
  await dialog.getByRole('button', { name: 'ДА!' }).click();
  await expect(dialog.getByRole('status')).toHaveText('Очистка выполняется. Дождитесь результата.');
  await expect(open).toBeDisabled();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'ОК' })).toBeHidden();
  finishCleanup();
  await expect(dialog.getByRole('status')).toHaveText('Очистка завершена: проверено 12, удалено 3 файлов.');
  await page.keyboard.press('Escape');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'ОК' }).click();
  await expect(dialog).not.toBeVisible();
  await expect(open).toBeEnabled();
  expect(cleanupRequests).toBe(1);

  failCleanup = true;
  await open.click();
  await dialog.getByRole('button', { name: 'ДА!' }).click();
  await expect(dialog.getByRole('status')).toHaveText('Очистка не завершилась. Повторите позже.');
  await dialog.getByRole('button', { name: 'ОК' }).click();
  await expect(dialog).not.toBeVisible();
  expect(cleanupRequests).toBe(2);
});

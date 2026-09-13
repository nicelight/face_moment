import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';

const spaA = '00000000-0000-0000-0000-000000000001';
const spaB = '00000000-0000-0000-0000-000000000002';
const html = execFileSync('.venv/bin/python', ['-c', `
import uuid
from datetime import date
from face_moment.platform.staff_presentation import staff_document
from face_moment.serving_control.http import _spa_admin_page_html
from face_moment.serving_control.active_search_date import ActiveSearchDateSpa
print(staff_document(_spa_admin_page_html([
    ActiveSearchDateSpa(uuid.UUID('${spaA}'), 'Первая площадка'),
    ActiveSearchDateSpa(uuid.UUID('${spaB}'), 'Вторая площадка', search_today=False,
                       date_from=date(2026,9,8), date_to=date(2026,9,10)),
]), 'spas'))
`], { encoding: 'utf8' });

test.use({ timezoneId: 'America/Los_Angeles' });

test('independent площадка switches, calendar range, validation and save failures', async ({ page }) => {
  const writes = [];
  let failSave = false;
  await page.context().addCookies([{ name: 'fm_staff_csrf', value: 'test-csrf', domain: 'staff.test', path: '/', secure: true }]);
  await page.route('https://staff.test/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/staff/spas') return route.fulfill({ contentType: 'text/html', body: html });
    if (path.startsWith('/client/')) return route.fulfill({
      contentType: path.endsWith('.js') ? 'text/javascript' : 'text/css', body: await readFile('.' + path),
    });
    if (path === '/api/staff/session') return route.fulfill({ json: { username: 'Fixture', role: 'developer' } });
    if (path.endsWith('/search-dates')) {
      writes.push({ path, payload: route.request().postDataJSON(), csrf: route.request().headers()['x-csrf-token'] });
      if (failSave) return route.fulfill({ status: 503 });
      return route.fulfill({ json: { ...writes.at(-1).payload, date_from: '2026-09-09', date_to: '2026-09-11', today: '2026-09-12' } });
    }
    return route.fulfill({ status: 404 });
  });
  await page.goto('https://staff.test/staff/spas');
  const first = page.locator(`[data-spa-search][data-spa-id="${spaA}"]`);
  const second = page.locator(`[data-spa-search][data-spa-id="${spaB}"]`);
  await expect(first.getByRole('switch')).toBeChecked();
  await expect(first.locator('[name="date_from"]')).toBeDisabled();
  await expect(second.getByRole('switch')).not.toBeChecked();
  await expect(second.locator('[name="date_from"]')).toBeEnabled();
  await expect(second.locator('[name="date_from"]')).toHaveValue('08.09.2026');
  await expect(page.getByRole('link', { name: 'Настройки поиска', exact: true })).toHaveCount(0);
  await first.getByRole('switch').uncheck();
  await first.locator('[name="date_from"]').fill('11.09.2026');
  await first.locator('[name="date_to"]').fill('09.09.2026');
  await first.getByRole('button', { name: 'Сохранить поиск' }).click();
  await expect(first.getByRole('status')).toContainText('не должна быть позже');
  expect(writes).toHaveLength(0);
  await first.locator('[data-calendar]').first().fill('2026-09-09');
  await first.locator('[data-calendar]').last().fill('2026-09-11');
  await first.getByRole('button', { name: 'Сохранить поиск' }).click();
  await expect(first.getByRole('status')).toHaveText('Настройки поиска сохранены.');
  expect(writes[0]).toEqual({ path: `/api/serving/spas/${spaA}/search-dates`, csrf: 'test-csrf',
    payload: { search_today: false, date_from: '2026-09-09', date_to: '2026-09-11' } });
  await expect(second.locator('[name="date_from"]')).toHaveValue('08.09.2026');
  await first.getByRole('switch').check();
  await first.getByRole('button', { name: 'Сохранить поиск' }).click();
  await expect(first.getByRole('status')).toHaveText('Настройки поиска сохранены.');
  expect(writes[1].payload).toEqual({ search_today: true });
  await first.getByRole('switch').uncheck();
  await expect(first.locator('[name="date_from"]')).toHaveValue('09.09.2026');
  await expect(first.locator('[name="date_to"]')).toHaveValue('11.09.2026');
  failSave = true;
  await first.getByRole('button', { name: 'Сохранить поиск' }).click();
  await expect(first.getByRole('status')).toContainText('Не удалось сохранить');
  await expect(first.getByRole('button', { name: 'Сохранить поиск' })).toBeEnabled();
  await expect(first.locator('[name="date_from"]')).toBeEnabled();
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    const bounds = await first.locator('[name="date_to"]').boundingBox();
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    await page.screenshot({ path: `.tasks/search-dates/spas-${width}.png`, fullPage: true });
  }
});

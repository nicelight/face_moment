import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

const html = execFileSync('uv', ['run', '--locked', 'python', '-c', `
import uuid
from datetime import date
from face_moment.serving_control.active_search_date import ActiveSearchDateSpa
from face_moment.serving_control.http import _spa_admin_page_html
from face_moment.platform.staff_presentation import staff_document
spas=[ActiveSearchDateSpa(spa_id=uuid.UUID(int=i), name='Площадка '+str(i), search_today=True,
date_from=date(2026,9,8), date_to=date(2026,9,20)) for i in (1,2)]
print(staff_document(_spa_admin_page_html(spas), 'spas'))
`], { encoding: 'utf8' });

for (const width of [1100, 390]) {
  test(`venue threshold controls and auto-today at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    const saved = [];
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/staff/spas') return route.fulfill({ contentType: 'text/html', body: html });
      if (url.pathname.startsWith('/api/serving/spas/')) {
        const payload = route.request().postDataJSON(); saved.push({ path: url.pathname, payload });
        const body = url.pathname.endsWith('/search-dates')
          ? { ...payload, date_from: '2026-09-08', date_to: '2026-09-20', today: '2026-09-14' }
          : payload;
        return route.fulfill({ json: body });
      }
      if (url.pathname.startsWith('/client/')) {
        try {
          const body = await readFile(path.join(process.cwd(), url.pathname.slice(1)));
          return route.fulfill({ body, contentType: url.pathname.endsWith('.js') ? 'text/javascript' : 'text/css' });
        } catch { return route.abort(); }
      }
      return route.abort();
    });
    await page.goto('http://127.0.0.1:18891/staff/spas');
    await page.locator('.fm-spa-settings > summary').first().click();
    await page.locator('.fm-spa-settings > summary').nth(1).click();
    const dates = page.locator('[data-spa-search]').first();
    await expect(dates.locator('[data-manual-search]')).toBeHidden();
    await dates.getByRole('switch').uncheck();
    await expect(dates.getByRole('status')).toHaveText('Настройки поиска сохранены.');
    await expect(dates.locator('[data-manual-search]')).toBeVisible();
    await expect(dates.getByRole('button', { name: 'Сохранить поиск' })).toBeVisible();
    expect(saved[0].payload).toEqual({ search_today: false, date_from: '2026-09-08', date_to: '2026-09-20' });
    await dates.getByRole('switch').check();
    await expect(dates.getByRole('status')).toHaveText('Настройки поиска сохранены.');
    await expect(dates.locator('[data-manual-search]')).toBeHidden();

    const form = page.locator('[data-detector="photo_yunet"]').first();
    const input = form.getByRole('spinbutton');
    await expect(input).toBeDisabled();
    await form.getByRole('switch').check();
    await input.fill('0.72');
    await form.getByRole('switch').uncheck();
    await expect(input).toHaveValue('0.9');
    await expect(input).toBeDisabled();
    await form.getByRole('switch').check();
    await input.fill('0.72');
    await form.getByRole('button', { name: 'Сохранить порог' }).click();
    await expect(form.getByRole('status')).toHaveText('Порог сохранён.');
    await expect(input).toBeDisabled();
    await expect(input).toHaveValue('0.72');
    await expect(form.getByRole('switch')).not.toBeChecked();
    await expect(page.locator('[data-detector="photo_yunet"]').nth(1).getByRole('spinbutton')).toHaveValue('0.9');
    const capture = page.locator('[data-detector="capture_blazeface"]').first();
    await capture.getByRole('switch').check();
    await capture.getByRole('spinbutton').fill('0.6');
    await capture.getByRole('button').click();
    await expect(capture.getByRole('spinbutton')).toBeDisabled();
    await expect(capture.getByRole('spinbutton')).toHaveValue('0.6');
    expect(saved.at(-1).path).toContain('/detector-thresholds/capture_blazeface');
    await capture.getByRole('switch').hover();
    await expect(capture.locator('.fm-search-toggle')).toHaveAttribute('title', /Ниже порог/);
    await expect(capture.locator('[role="tooltip"]')).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath('venue-detectors.png'), fullPage: true });
  });
}

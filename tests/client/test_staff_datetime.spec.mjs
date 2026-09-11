import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';

const pages = JSON.parse(execFileSync('.venv/bin/python', ['-c', `
import json, uuid
from datetime import datetime, timezone
from face_moment.platform.staff_datetime import datetime_range_fields
from face_moment.platform.staff_presentation import staff_document
from face_moment.diagnostics.http import _render_server_event_page, _render_attempt_list
from face_moment.inventory.http import _processing_health_page_html, _photo_upload_page_html
from face_moment.serving_control.http import _active_search_date_page_html, _spa_admin_page_html
from face_moment.serving_control.active_search_date import ActiveSearchDateSpa
spa = uuid.UUID('00000000-0000-0000-0000-000000000001')
fixed = datetime_range_fields(now=datetime(2026,9,11,20,15,30,tzinfo=timezone.utc), max_days=7)
events = _render_server_event_page([], [])
start=events.index('<div class="fm-datetime-range"')
end=events.index('<label>Severity', start)
events=events[:start]+fixed+'\\n'+events[end:]
print(json.dumps({
  '/staff/server-events': staff_document(events, 'server-events'),
  '/staff/attempts': staff_document(_render_attempt_list([], []), 'attempts'),
  '/staff/processing-health': staff_document(_processing_health_page_html([(spa, 'Площадка 1')]), 'processing-health'),
  '/staff/photo-upload': staff_document(_photo_upload_page_html(), 'photo-upload'),
  '/staff/spas': staff_document(_spa_admin_page_html([ActiveSearchDateSpa(spa, 'Площадка 1')]), 'spas'),
  '/staff/search-settings': staff_document(_active_search_date_page_html([ActiveSearchDateSpa(spa, 'Площадка 1')]), 'search-settings'),
}))
`], { encoding: 'utf8' }));

test.use({ timezoneId: 'America/Los_Angeles' });

test.beforeEach(async ({ page }) => {
  await page.route('https://staff.test/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (pages[path]) return route.fulfill({ contentType: 'text/html', body: pages[path] });
    if (/^\/client\/[a-z-]+\.(js|css)$/.test(path)) {
      return route.fulfill({ contentType: path.endsWith('.js') ? 'text/javascript' : 'text/css', body: await readFile('.' + path) });
    }
    if (path === '/api/staff/session') return route.fulfill({ json: { username: 'Fixture', role: 'developer' } });
    if (path === '/api/inventory/ingest-targets') return route.fulfill({ json: { schema_version: 1, spas: [] } });
    if (path.endsWith('/active-visit-date')) return route.fulfill({ json: { active_visit_date: null, settings_revision: 1 } });
    return route.fulfill({ status: 503, body: '' });
  });
});

test('default date/time uses UTC+7 across midnight, with the clock to the right', async ({ page }) => {
  await page.goto('https://staff.test/staff/server-events');
  await expect(page.locator('#from-date')).toHaveValue('12.09.2026');
  await expect(page.locator('#to-date')).toHaveValue('12.09.2026');
  await expect(page.locator('#from-time')).toHaveValue('03:15:30');
  await expect(page.locator('#to-time')).toHaveValue('03:15:30');
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 950 });
    const date = await page.locator('#from-date').boundingBox();
    const time = await page.locator('[data-time-picker]').first().boundingBox();
    expect(time.x).toBeGreaterThan(date.x);
    expect(Math.abs(time.y - date.y)).toBeLessThan(2);
    expect(time.x + time.width).toBeLessThanOrEqual(width);
  }
});

test('all omits filters; severity and component selections submit their exact codes', async ({ page }) => {
  await page.goto('https://staff.test/staff/server-events');
  await page.getByRole('button', { name: 'Filter', exact: true }).click();
  await expect(page).toHaveURL('https://staff.test/staff/server-events?');
  await page.locator('[name="severity"]').selectOption('error');
  await page.locator('[name="component"]').selectOption('realtime');
  await page.getByRole('button', { name: 'Filter', exact: true }).click();
  await expect(page).toHaveURL(/severity=error&component=realtime$/);
});

test('date and time submit UTC correctly and reject equal and oversized ranges', async ({ page }) => {
  await page.goto('https://staff.test/staff/server-events');
  await page.locator('[data-range-enabled]').check();
  await page.getByRole('button', { name: 'Filter', exact: true }).click();
  await expect(page.locator('[data-range-error]')).toContainText('позже начала');
  await page.locator('#from-date').fill('01.09.2026');
  await page.getByRole('button', { name: 'Filter', exact: true }).click();
  await expect(page.locator('[data-range-error]')).toContainText('7 дней');
  await page.locator('#from-date').fill('12.09.2026');
  await page.locator('#from-time').fill('00:00:00');
  const navigation = page.waitForRequest(request => request.isNavigationRequest() && new URL(request.url()).searchParams.has('from'));
  await page.getByRole('button', { name: 'Filter', exact: true }).click();
  const url = new URL((await navigation).url());
  expect(url.searchParams.get('from')).toBe('2026-09-11T17:00:00.000Z');
  expect(url.searchParams.get('to')).toBe('2026-09-11T20:15:30.000Z');
  expect([...url.searchParams.keys()]).toEqual(['from', 'to']);
});

test('history and processing share the controls and processing restores a bookmarked UTC interval', async ({ page }) => {
  await page.goto('https://staff.test/staff/attempts');
  await expect(page.locator('input[type="date"]')).toHaveCount(2);
  await expect(page.locator('[data-time-picker]')).toHaveCount(2);
  const requests = [];
  page.on('request', request => { if (request.url().includes('/api/inventory/processing-health?')) requests.push(new URL(request.url())); });
  await page.goto('https://staff.test/staff/processing-health?accepted_from=2026-09-11T17:00:00Z&accepted_before=2026-09-11T18:30:00Z');
  await expect(page.locator('#accepted_from-date')).toHaveValue('12.09.2026');
  await expect(page.locator('#accepted_from-time')).toHaveValue('00:00:00');
  await expect(page.locator('#accepted_before-time')).toHaveValue('01:30:00');
  await expect.poll(() => requests.length).toBeGreaterThan(0);
  expect(requests.at(-1).searchParams.get('accepted_from')).toBe('2026-09-11T17:00:00.000Z');
  await page.locator('[data-range-enabled]').uncheck();
  await page.getByRole('button', { name: 'Обновить состояние' }).click();
  await expect.poll(() => requests.at(-1).searchParams.has('accepted_from')).toBe(false);
});

test('date-only forms use calendars and default to today in UTC+7', async ({ page }) => {
  const today = new Date(Date.now() + 7 * 3600000).toISOString().slice(0, 10);
  for (const path of ['/staff/photo-upload', '/staff/search-settings']) {
    await page.goto('https://staff.test' + path);
    await expect(page.locator('#visit-date')).toHaveAttribute('type', 'text');
    await expect(page.locator('#visit-date')).toHaveValue(today.split('-').reverse().join('.'));
  }
});


test('calendar selection and typed dd.mm.yyyy stay synchronized and reject impossible dates', async ({ page }) => {
  await page.goto('https://staff.test/staff/server-events');
  const calendar = page.locator('[data-date-picker]').first().locator('[data-calendar]');
  await calendar.fill('2026-09-10');
  await expect(page.locator('#from-date')).toHaveValue('10.09.2026');
  await page.locator('#from-date').fill('31.02.2026');
  expect(await page.locator('#from-date').evaluate(e => e.checkValidity())).toBe(false);
  await page.locator('#from-date').fill('29.02.2028');
  await expect(calendar).toHaveValue('2028-02-29');
  expect(await page.locator('#from-date').evaluate(e => e.checkValidity())).toBe(true);
});


test('single time field uses 24-hour input and sends an afternoon selection correctly', async ({ page }) => {
  await page.goto('https://staff.test/staff/server-events');
  await expect(page.locator('input[type="time"]')).toHaveCount(0);
  await expect(page.locator('[data-time-picker] select')).toHaveCount(0);
  await expect(page.locator('[data-time-picker] input')).toHaveCount(2);
  await page.locator('#from-date').fill('11.09.2026');
  await page.locator('#from-time').fill('18:45:00');
  await expect(page.locator('#from-time')).toHaveValue('18:45:00');
  const navigation = page.waitForRequest(request => request.isNavigationRequest() && new URL(request.url()).searchParams.has('from'));
  await page.getByRole('button', { name: 'Filter', exact: true }).click();
  expect(new URL((await navigation).url()).searchParams.get('from')).toBe('2026-09-11T11:45:00.000Z');
});


test('processing timestamps show seconds only in UTC+7 without Z', async ({ page }) => {
  const stamp = '2026-09-11T20:05:17.501214Z';
  await page.route('**/api/inventory/processing-health?*', route => route.fulfill({ json: {
    queue: { pending: 0, processing: 0, ready: 0, no_faces: 0, failed: 0,
      oldest_pending_accepted_at: null, current_operation: null, operation_started_at: null,
      worker_started_at: stamp, last_recovery_at: stamp, last_recovered_count: 0 },
    ingest_to_searchable: null,
    storage: { postgresql: { status: 'ok', available_bytes: 1, low_threshold_bytes: 0, observed_at: stamp, error: null },
      minio: { status: 'ok', available_bytes: 1, low_threshold_bytes: 0, observed_at: stamp, error: null } },
  } }));
  await page.goto('https://staff.test/staff/processing-health');
  await expect(page.locator('#queue-worker-started-at')).toHaveText('12.09.2026 03:05:17');
  await expect(page.locator('#queue-last-recovery-at')).toHaveText('12.09.2026 03:05:17');
  await expect(page.locator('#postgresql-observed-at')).toHaveText('12.09.2026 03:05:17');
  await expect(page.locator('#queue-operation-started-at')).toHaveText('нет данных');
});


for (const role of ['operator', 'developer']) {
  test(`${role} sees both navigation entries and renames a площадка on its own page`, async ({ page }) => {
    await page.route('**/api/staff/session', route => route.fulfill({ json: { username: 'Fixture', role } }));
    const writes = [];
    await page.route('**/api/serving/spas/*/name', route => {
      writes.push(route.request().postDataJSON());
      return route.fulfill({ json: { name: writes.at(-1).name } });
    });
    await page.goto('https://staff.test/staff/spas');
    await expect(page.getByRole('link', { name: 'Площадки', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Настройки поиска', exact: true })).toBeVisible();
    await page.locator('[data-spa-rename] input').fill('Термы');
    await page.getByRole('button', { name: 'Сохранить название', exact: true }).click();
    await expect(page.locator('[data-spa-title]')).toHaveText('Термы');
    await expect(page.locator('[data-spa-rename] [role="status"]')).toHaveText('Название площадки сохранено.');
    expect(writes).toEqual([{ name: 'Термы' }]);
  });
}


test('time supports minute shorthand and keyboard adjustment while rejecting invalid input', async ({ page }) => {
  await page.goto('https://staff.test/staff/server-events');
  const time = page.locator('#from-time');
  await time.fill('18:45');
  await time.blur();
  await expect(time).toHaveValue('18:45:00');
  await time.focus();
  await time.evaluate(input => input.setSelectionRange(3, 5));
  await time.press('ArrowUp');
  await expect(time).toHaveValue('18:46:00');
  await time.fill('24:00:00');
  expect(await time.evaluate(input => input.checkValidity())).toBe(false);
  await time.fill('23:59:59');
  expect(await time.evaluate(input => input.checkValidity())).toBe(true);
});

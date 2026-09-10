import { readFile } from 'node:fs/promises';
import { test, expect } from '@playwright/test';

const origin = 'https://kiosk-identity.test';
const id = '12345678-1234-4321-8765-123456789abc';

async function assets(route) {
  const pathname = new URL(route.request().url()).pathname;
  if (pathname === '/client/blazeface.js') return route.fulfill({ contentType: 'text/javascript', body: 'export async function createBlazeFaceDetector(){return {detect:async()=>[],close(){}}} export async function detectReferenceSeries(){return []}' });
  const file = pathname === '/' ? '/client/index.html' : pathname;
  try {
    await route.fulfill({ contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html', body: await readFile(new URL(`../..${file}`, import.meta.url)) });
  } catch { await route.fulfill({ status: 404 }); }
}

for (const [width, height] of [[1450, 833], [390, 844]]) {
  test(`kiosk menu and authenticated Cyrillic identity at ${width}x${height}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    const authorizations = [];
    await page.route(`${origin}/**`, async route => {
      if (new URL(route.request().url()).pathname === '/api/promo/display/config') {
        const auth = route.request().headers().authorization;
        authorizations.push(auth);
        return route.fulfill({ headers: { 'X-Face-Moment-Display-Client-Id': id, 'X-Face-Moment-Display-Name': encodeURIComponent(auth === 'Bearer synthetic-second' ? 'Экран у бассейна' : 'Экран у входа') }, json: { schema_version: 1, result_display_ms: 60_000, success_cooldown_ms: 1000 } });
      }
      return assets(route);
    });
    await page.addInitScript(() => {
      localStorage.setItem('face-moment.display-client-token', 'synthetic-first');
      localStorage.setItem('face-moment.promo-display-seconds', '7');
      Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
        enumerateDevices: async () => [], getUserMedia: async () => { throw new Error('No physical camera in QA'); }, addEventListener() {},
      } });
    });
    await page.goto(`${origin}/#advertising`);
    await expect(page.locator('.site-header')).toHaveText('Ловим моменты');
    await expect(page.locator('.advertising-card h2')).toHaveCount(0);
    await expect(page.locator('.kiosk-menu')).not.toHaveAttribute('open');
    const menu = page.getByLabel('Меню', { exact: true });
    await expect(menu).toBeInViewport();
    await expect(page.getByRole('link', { name: 'Конфигурация', exact: true })).not.toBeVisible();
    await menu.click();
    await expect(page.getByRole('link', { name: 'Конфигурация', exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('.kiosk-menu')).not.toHaveAttribute('open');
    await expect(menu).toBeFocused();
    await menu.click();
    await page.locator('.site-header h1').click();
    await expect(page.locator('.kiosk-menu')).not.toHaveAttribute('open');
    await menu.click();
    await page.getByRole('link', { name: 'Конфигурация', exact: true }).click();
    await expect(page.locator('.kiosk-menu')).not.toHaveAttribute('open');
    await expect(page.locator('#display-client-identity')).toHaveText('Экран у входа · ID: …89abc');
    await expect(page.locator('#promo-display-seconds')).toHaveValue('7');
    expect(authorizations).toContain('Bearer synthetic-first');
    await page.getByText('доп настройки', { exact: true }).click();
    await page.locator('#display-client-token').fill('synthetic-second');
    await page.locator('#display-client-save').click();
    await expect(page.locator('#display-client-identity')).toHaveText('Экран у бассейна · ID: …89abc');
    expect(authorizations).toContain('Bearer synthetic-second');
  });
}

test('staff screen rename updates card and table; failure preserves last saved name', async ({ page, context }) => {
  let failRename = false;
  const writes = [];
  await context.addCookies([{ name: 'fm_staff_csrf', value: 'synthetic-csrf', url: origin }]);
  // Faithful bounded markup fixture for _display_client_page_html; no real staff session.
  const markup = `<meta charset="utf-8"><body data-staff-page="display-clients"><span id="staff-account-name"></span><span id="staff-identity"></span><main>
    <article class="fm-device-card"><h2>Экран у входа</h2><form class="fm-device-rename" data-client-id="${id}"><label>Название экрана<input name="name" value="Экран у входа" required maxlength="255"></label><button type="submit">Сохранить название</button><p role="status"></p></form></article>
    <details class="fm-device-table"><summary>Таблица настроенных экранов</summary><table><tbody><tr><td data-field="display-client-id">${id}</td><td data-field="name">Экран у входа</td></tr></tbody></table></details>
    </main><script type="module" src="/client/staff-ui.js"></script></body>`;
  await page.route(`${origin}/**`, async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/staff/display-clients') return route.fulfill({ contentType: 'text/html', body: markup });
    if (pathname === '/api/staff/session') return route.fulfill({ json: { username: 'QA', role: 'operator' } });
    if (pathname === `/api/serving/display-clients/${id}/name`) {
      writes.push({ method: route.request().method(), csrf: route.request().headers()['x-csrf-token'], body: route.request().postDataJSON() });
      return failRename ? route.fulfill({ status: 503 }) : route.fulfill({ json: { name: 'Экран у бассейна' } });
    }
    return assets(route);
  });
  await page.goto(`${origin}/staff/display-clients`);
  await page.getByLabel('Название экрана').fill(' Экран у бассейна ');
  await page.getByRole('button', { name: 'Сохранить название', exact: true }).click();
  await expect(page.locator('.fm-device-card h2')).toHaveText('Экран у бассейна');
  await expect(page.locator('[data-field="name"]')).toHaveText('Экран у бассейна');
  expect(writes).toEqual([{ method: 'PUT', csrf: 'synthetic-csrf', body: { name: 'Экран у бассейна' } }]);
  failRename = true;
  await page.getByLabel('Название экрана').fill('Несохранённое имя');
  await page.getByRole('button', { name: 'Сохранить название', exact: true }).click();
  await expect(page.locator('.fm-device-rename [role="status"]')).toContainText('Не удалось сохранить название');
  await expect(page.locator('.fm-device-card h2')).toHaveText('Экран у бассейна');
  await expect(page.locator('[data-field="name"]')).toHaveText('Экран у бассейна');
  await expect(page.getByRole('button', { name: 'Сохранить название', exact: true })).toBeEnabled();
});

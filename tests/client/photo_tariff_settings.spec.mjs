import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { mkdir } from 'node:fs/promises';

const evidence = '.tasks/TASK-130-T2-FT-014-W4';
let fixture, baseURL, exited;
test.use({ viewport: { width: 1280, height: 900 } });
test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true });
  fixture = spawn('uv', ['run', '--locked', '--env-file', '.env.local', 'python', '-m', 'tests.client.photo_tariff_browser_fixture'], { stdio: ['pipe', 'pipe', 'inherit'] });
  exited = new Promise(resolve => fixture.on('exit', resolve));
  const lines = createInterface({ input: fixture.stdout });
  baseURL = await new Promise((resolve, reject) => {
    lines.on('line', line => { if (line.startsWith('{')) resolve(JSON.parse(line).url); else if (line === 'DISPOSABLE_DB_CLEANED') console.log(line); });
    fixture.on('exit', code => reject(new Error(`fixture exit ${code}`)));
  });
});
test.afterAll(async () => {
  fixture?.stdin.end('\n');
  if (exited) expect(await exited).toBe(0);
});

for (const role of ['operator', 'developer']) {
  test(`${role}: native staff tariff read/save/reload/rejections`, async ({ page }) => {
    const login = await page.request.post(`${baseURL}/api/staff/sessions`, {
      data: { username: `tariff-${role}`, password: 'browser-fixture-password' },
    });
    expect(login.ok()).toBeTruthy();
    // Native auth issues secure cookies; fixture browser runs on disposable loopback HTTP.
    const cookies = login.headersArray().filter(h => h.name.toLowerCase() === 'set-cookie').map(h => {
      const [name, ...value] = h.value.split(';')[0].split('=');
      return { name, value: value.join('='), url: baseURL };
    });
    await page.context().addCookies(cookies);
    await page.goto(`${baseURL}/staff/spas`);
    const form = page.locator('[data-photo-tariff]');
    await expect(form, 'AC-005 staff global tariff editor exists').toBeVisible();
    const field = name => form.locator(`[name="${name}"]`);
    if (role === 'operator') {
      await expect(form.getByRole('status')).toContainText('ещё не задан');
      for (const name of ['base_kopecks', 'd1', 'd2', 'd3']) await expect(field(name)).toHaveValue('');
    }
    await field('base_kopecks').fill('12345');
    await field('d1').fill('0.8'); await field('d2').fill('0.6'); await field('d3').fill('0.4');
    const savedResponse = page.waitForResponse(r => r.url().endsWith('/api/serving/photo-tariff') && r.request().method() === 'PUT');
    await form.getByRole('button', { name: 'Сохранить тариф' }).click();
    const saved = await savedResponse;
    expect(saved.status()).toBe(200);
    expect(await saved.json()).toEqual({ base_kopecks: 12345, d1: '0.8', d2: '0.6', d3: '0.4' });
    await expect(form.getByRole('status')).toContainText('Тариф сохранён');
    await page.reload();
    await expect(field('base_kopecks')).toHaveValue('12345');
    await expect(field('d3')).toHaveValue('0.4');
    // Invalid client draft is explained and never sent.
    let writes = 0;
    page.on('request', r => { if (r.url().endsWith('/api/serving/photo-tariff') && r.method() === 'PUT') writes++; });
    await field('d2').fill('0.9');
    await form.getByRole('button', { name: 'Сохранить тариф' }).click();
    await expect(form.getByRole('status')).toContainText('1 ≥ d1 ≥ d2 ≥ d3 > 0');
    expect(writes).toBe(0);
    await field('d2').fill('0.6');
    // Rounded paid units are server-owned: a syntactically valid draft can be rejected.
    await field('base_kopecks').fill('1'); await field('d3').fill('0.1');
    const invalidResponse = page.waitForResponse(r => r.url().endsWith('/api/serving/photo-tariff') && r.request().method() === 'PUT');
    await form.getByRole('button', { name: 'Сохранить тариф' }).click();
    expect((await invalidResponse).status()).toBe(422);
    await expect(form.getByRole('status')).toContainText('отклонён сервером');
    await page.reload();
    await expect(field('base_kopecks')).toHaveValue('12345');
    await expect(field('d3')).toHaveValue('0.4');
    // Real API rejects a valid draft when its existing CSRF header is absent.
    await page.route('**/api/serving/photo-tariff', async route => {
      if (route.request().method() !== 'PUT') return route.continue();
      const headers = { ...route.request().headers() }; delete headers['x-csrf-token'];
      return route.continue({ headers });
    });
    await field('base_kopecks').fill('99999');
    const deniedResponse = page.waitForResponse(r => r.url().endsWith('/api/serving/photo-tariff') && r.request().method() === 'PUT');
    await form.getByRole('button', { name: 'Сохранить тариф' }).click();
    expect((await deniedResponse).status()).toBe(403);
    await expect(form.getByRole('status')).toContainText('Нет прав');
    await page.unroute('**/api/serving/photo-tariff');
    await page.reload();
    await expect(field('base_kopecks')).toHaveValue('12345');
    await expect(field('d2')).toHaveValue('0.6');
    for (const width of [1280, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(form).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      await page.screenshot({ path: `${evidence}/${role}-${width}.png`, fullPage: true });
    }
    console.log(`${role}: native shell/API save200, reload canonical, invalid draft no write, API422/403 explained, saved state retained; Chromium 1280/390`);
  });
}

// Browser rendering/ephemeral-state proof with fixture HTTP responses.
// Real model + API + PostgreSQL + MinIO integration lives in test_capture_identity.py.
import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';

const venue = '00000000-0000-0000-0000-000000000001';
const person = '00000000-0000-0000-0000-000000000002';
const html = execFileSync('uv', ['run', '--locked', 'python', '-c', `
import uuid
from face_moment.inventory.staff_media_http import staff_media_page_html
from face_moment.platform.staff_presentation import staff_document
print(staff_document(staff_media_page_html(uuid.UUID('${venue}'), 'Тестовая площадка', can_diagnose=True), 'venue-media'))
`], { encoding: 'utf8' });

test('capture server order and temporary evaluations survive toggling but reset on reload', async ({ page }) => {
  const writes = [];
  const ranks = new Map([[4,1],[1,2],[7,3],[2,4],[6,5]]);
  await page.route('https://staff.test/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/staff/venue-media') return route.fulfill({ contentType: 'text/html', body: html });
    if (path.startsWith('/client/')) return route.fulfill({
      contentType: path.endsWith('.js') ? 'text/javascript' : 'text/css', body: await readFile('.' + path),
    });
    if (route.request().method() !== 'GET') writes.push(path);
    if (path === '/api/staff/session') return route.fulfill({ json: { username: 'Fixture', role: 'operator' } });
    if (path === '/api/inventory/venue-media') return route.fulfill({ json: { photos: [] } });
    if (path === '/api/diagnostics/people') return route.fulfill({ json: { people: [{ id: person, name: 'Алекс' }] } });
    if (path === '/api/diagnostics/captures') return route.fulfill({ json: { attempts: [
      { id: 'attempt-new', created_at: '2026-09-15T10:00:00Z', proposal_count: 8 },
      { id: 'attempt-old', created_at: '2026-09-14T10:00:00Z', proposal_count: 2 },
    ] } });
    if (path.endsWith('/attempt-old')) return route.fulfill({ json: { captures: null } });
    if (path.endsWith('/attempt-new')) return route.fulfill({ json: { captures: {
      threshold: .4, pipeline_revision_id: 'test-revision', selection_available: true, images_expired: false,
      items: Array.from({ length: 8 }, (_, index) => ({ occurrence_index: index, rank: ranks.get(index) ?? null,
        person_id: person, identity_name: `Гость ${index}`, reason: 'recognized', score: .8, image_url: null })),
    } } });
    return route.fulfill({ status: 404 });
  });
  await page.goto(`https://staff.test/staff/venue-media?spa_id=${venue}`);
  const attempt = page.locator('.fm-capture-attempt').first();
  await attempt.locator('summary').click();
  await expect(attempt.locator('.fm-capture-grid').first().locator('strong')).toHaveText(['Гость 4','Гость 1','Гость 7','Гость 2','Гость 6'].map(name => `${name} · 000002`));
  await expect(attempt.locator('.fm-capture-grid').nth(1).locator('strong')).toHaveText(['Гость 0','Гость 3','Гость 5'].map(name => `${name} · 000002`));
  await expect(attempt.getByRole('group', { name: 'Кого не нашли' }).getByRole('combobox')).toHaveCount(3);
  const grade = attempt.locator('.fm-capture-card select').first();
  await grade.selectOption('correct');
  await attempt.locator('fieldset select').first().selectOption(person);
  await attempt.locator('summary').click(); await attempt.locator('summary').click();
  await expect(grade).toHaveValue('correct');
  await attempt.getByRole('button', { name: 'Очистить оценки захвата' }).click();
  await expect(grade).toHaveValue('');
  await grade.selectOption('false');
  await page.reload();
  await page.locator('.fm-capture-attempt').first().locator('summary').click();
  await expect(page.locator('.fm-capture-card select').first()).toHaveValue('');
  expect(writes).toHaveLength(0);
  await page.locator('.fm-capture-attempt').nth(1).locator('summary').click();
  await expect(page.getByText('Изображения этого захвата не сохранены:', { exact: false })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

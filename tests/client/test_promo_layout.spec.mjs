import { readFile } from 'node:fs/promises';
import { test, expect } from '@playwright/test';

const origin = 'https://promo-layout.test';
for (const [width, height] of [[1920,1080], [1280,1024], [1080,1080], [1080,1920], [2560,1080], [390,844]]) {
  test(`Promo fits ${width}x${height} with complete photos and stationary QR`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.route(`${origin}/**`, async route => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname === '/') return route.fulfill({ contentType: 'text/html', body: '<link rel="stylesheet" href="/client/styles.css"><main id="result"></main>' });
      return route.fulfill({ contentType: pathname.endsWith('.css') ? 'text/css' : 'text/javascript', body: await readFile(new URL(`../..${pathname}`, import.meta.url)) });
    });
    await page.goto(origin);
    await page.evaluate(async () => {
      const { PromoDisplayController } = await import('/client/promo-display.js');
      // Distinct landscape/portrait fixtures exercise full-frame containment.
      const blobs = await Promise.all([[600,400],[400,600],[600,400],[400,600]].map(async ([w,h], i) => {
        const canvas = document.createElement('canvas'); canvas.width=w; canvas.height=h;
        const ctx=canvas.getContext('2d'); ctx.fillStyle=['#b18a68','#667e78','#9298ac','#c6a071'][i]; ctx.fillRect(0,0,w,h);
        ctx.strokeStyle='white'; ctx.lineWidth=20; ctx.strokeRect(10,10,w-20,h-20);
        ctx.fillStyle='white'; ctx.font='80px sans-serif'; ctx.fillText(String(i+1),w/2-20,h/2);
        return new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg'));
      }));
      const controller = new PromoDisplayController({ container: document.querySelector('#result'), fetchImpl: async url => new Response(blobs[Number(url.at(-1))], {headers:{'Content-Type':'image/jpeg'}}) });
      const result = await controller.showResult({attemptId:'layout', result:{session_id:'layout', teasers:blobs.map((_,i)=>({photo_id:`photo-${i}`,media_url:`${location.origin}/api/promo/media/${i}`})), n:4, qr_url:`${location.origin}/q?ticket=layout`, qr_first_open_expires_at:'2026-09-07T12:00:00Z'}});
      if (result.state !== 'result') throw new Error(JSON.stringify(result));
    });
    await expect(page.locator('.promo-photo-card')).toHaveCount(4);
    await expect(page.locator('h2')).toHaveText('Ваши фото можно скачать по QR коду или на сайте face-momet.ru');
    await page.waitForTimeout(1200);
    const qrBefore = await page.locator('.promo-qr').boundingBox();
    for (const selector of ['.promo-photo-card', '.promo-qr-panel', '.promo-copy h2']) {
      for (const element of await page.locator(selector).all()) {
        const bounds = await element.boundingBox();
        expect(bounds.x).toBeGreaterThanOrEqual(0); expect(bounds.y).toBeGreaterThanOrEqual(0);
        expect(bounds.x+bounds.width).toBeLessThanOrEqual(width);
        expect(bounds.y+bounds.height).toBeLessThanOrEqual(height);
      }
    }
    for (const img of await page.locator('.promo-teaser').all()) {
      expect(await img.evaluate(el => el.complete && el.naturalWidth > 0 && getComputedStyle(el).objectFit === 'contain')).toBe(true);
    }
    await page.waitForTimeout(500);
    expect(await page.locator('.promo-qr').boundingBox()).toEqual(qrBefore);
    await page.screenshot({ path: `/tmp/face-moment-promo-${width}x${height}.png` });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    expect(await page.locator('.promo-photo-card').first().evaluate(el=>getComputedStyle(el).animationName)).toBe('none');
  });
}

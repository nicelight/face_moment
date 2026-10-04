import { readFile } from 'node:fs/promises';

export const origin = 'https://second-slide.test';
export async function setupSecondSlide(page) {
  const requests = [];
  let media;
  await page.route(`${origin}/**`, async route => {
    const path = new URL(route.request().url()).pathname;
    requests.push({ path, method: route.request().method() });
    if (path === '/client/blazeface.js') return route.fulfill({ contentType: 'text/javascript', body: 'export async function createBlazeFaceDetector(){return {detect:async()=>[],close(){}}} export async function detectReferenceSeries(){return []}' });
    if (path === '/api/promo/display/config') return route.fulfill({ json: { schema_version: 1, result_display_ms: 1000, success_cooldown_ms: 1000 } });
    if (path === '/api/promo/advertising/playlist') return route.fulfill({ json: { schema_version: 1, revision: 1, spa_id: 'fixture', crossfade_seconds: 0, image_seconds: 1, random_start: false, items: [] } });
    if (path.includes('/gallery/media/p4')) await new Promise(resolve => setTimeout(resolve, 3500));
    if (path.includes('/gallery/media/p5')) return route.fulfill({ status: 404 });
    if (path.includes('/media/')) return route.fulfill({ contentType: 'image/jpeg', body: media });
    if (path.endsWith('/display') || path.endsWith('/client-timing')) return route.fulfill({ json: {} });
    if (path.startsWith('/api/')) return route.fulfill({ status: 503 });
    const file = path === '/' ? '/client/index.html' : path;
    try { return route.fulfill({ contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html', body: await readFile(new URL(`../..${file}`, import.meta.url)) }); }
    catch { return route.fulfill({ status: 404 }); }
  });
  await page.addInitScript(() => {
    localStorage.setItem('face-moment.display-client-token', 'disposable-browser-token');
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { enumerateDevices: async () => [], getUserMedia: async () => { throw new Error('No fixture camera'); }, addEventListener() {} } });
  });
  await page.goto(`${origin}/#configuration`);
  media = Buffer.from(await page.evaluate(() => {
    const c = document.createElement('canvas'); c.width = 640; c.height = 400;
    const ctx = c.getContext('2d'); const g = ctx.createLinearGradient(0,0,640,400);
    g.addColorStop(0,'#cca77b');g.addColorStop(.5,'#416366');g.addColorStop(1,'#172e42');
    ctx.fillStyle=g;ctx.fillRect(0,0,640,400);ctx.fillStyle='#eee3cc';ctx.beginPath();ctx.arc(320,170,75,0,Math.PI*2);ctx.fill();
    return c.toDataURL('image/jpeg').split(',')[1];
  }), 'base64');
  return requests;
}
export async function issueSecondSlide(page, { gallery = true } = {}) {
  await page.goto(`${origin}/#advertising`);
  await page.evaluate(gallery => {
    const photos = Array.from({ length: 7 }, (_, i) => ({ photo_id: `p${i}`, kind: i === 6 ? 'common' : 'matched', media_url: `${location.origin}/api/promo/sessions/s1/gallery/media/p${i}` }));
    window.dispatchEvent(new CustomEvent('face-moment:attempt-request-start', { detail: { attemptId: 'a1', captureId: 'c1' } }));
    window.dispatchEvent(new CustomEvent('face-moment:attempt-response', { detail: { attemptId: 'a1', captureId: 'c1', timing: { referenceSeriesReadyMonotonicMs: performance.now() }, response: { status: 200, json: async () => ({ schema_version: 1, attempt_id: 'a1', outcome: 'result', result: {
      session_id: 's1', n: 6, qr_url: `${location.origin}/q?ticket=fixture`, qr_first_open_expires_at: '2099-01-01T00:00:00Z',
      teasers: photos.slice(0,4).map(p => ({ photo_id: p.photo_id, media_url: p.media_url.replace('/gallery','') })),
      ...(gallery ? { gallery_photos: photos } : {}),
    } }) } } }));
  }, gallery);
}

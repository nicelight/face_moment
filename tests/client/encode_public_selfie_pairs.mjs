import { chromium } from 'playwright';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
const directory = process.argv[2] ?? '.tasks/TASK-122-T2-FT-013-W3';
await mkdir(directory, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
 const page = await browser.newPage();
 const module = `data:text/javascript;base64,${(await readFile('client/site-selfie-history.js')).toString('base64')}`;
 for (const size of ['large', 'small']) {
  const source = await readFile(`tests/client/fixtures/selfie-portrait-${size}.png`);
  const result = await page.evaluate(async ({ module, source }) => {
   const { encodeSelfie } = await import(module);
   const image = new Image(); image.src = source; await image.decode();
   Object.defineProperties(image, {videoWidth: {value: image.naturalWidth}, videoHeight: {value: image.naturalHeight}});
   const blob = await encodeSelfie(image);
   return [...new Uint8Array(await blob.arrayBuffer())];
  }, {module, source: `data:image/png;base64,${source.toString('base64')}`});
  await writeFile(`${directory}/selfie-browser-${size}.jpg`, Buffer.from(result));
  console.log(`${size}: actual encodeSelfie Chromium JPEG q=.85, bytes=${result.length}`);
 }
} finally { await browser.close(); }

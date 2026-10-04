import assert from 'node:assert/strict';
import { encodeSelfie, selfieDimensions, saveSelfie } from '../../client/site-selfie-history.js';

for (const [input, expected] of [
  [[1240, 1440], { width: 827, height: 960 }],
  [[1920, 1080], { width: 960, height: 540 }],
  [[310, 360], { width: 310, height: 360 }],
  [[960, 960], { width: 960, height: 960 }],
]) assert.deepEqual(selfieDimensions(...input), expected);

const video = { videoWidth: 1920, videoHeight: 1080 };
const calls = [];
const jpeg = new Blob(['encoded JPEG'], { type: 'image/jpeg' });
const canvas = {
  getContext: () => ({ drawImage: (...args) => calls.push(args) }),
  toBlob(callback, type, quality) { calls.push({ type, quality }); callback(jpeg); },
};
assert.equal(await encodeSelfie(video, canvas), jpeg);
assert.deepEqual(calls, [[video, 0, 0, 960, 540], { type: 'image/jpeg', quality: .85 }]);
assert.equal(canvas.width, 960); assert.equal(canvas.height, 540);
canvas.toBlob = callback => callback(null);
await assert.rejects(encodeSelfie(video, canvas), /capture_failed/);
// Storage failures propagate for the camera UI to warn, without discarding JPEG.
const previous = globalThis.indexedDB;
try {
  globalThis.indexedDB = { open() { throw new DOMException('quota', 'QuotaExceededError'); } };
  await assert.rejects(saveSelfie(jpeg), { name: 'QuotaExceededError' });
  globalThis.indexedDB = undefined;
  await assert.rejects(saveSelfie(jpeg));
} finally { globalThis.indexedDB = previous; }
console.log('public camera JPEG: landscape/portrait no-upscale, q0.85, decode-failure and unavailable history supported');

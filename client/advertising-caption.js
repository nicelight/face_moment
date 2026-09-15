/** Local kiosk caption; independent of the venue playlist. */
const KEY = 'face-moment.advertising-caption';
export const MIN_CAPTION_SIZE = 8;
export const MAX_CAPTION_SIZE = 200;

export function readAdvertisingCaption() {
  try {
    const value = JSON.parse(localStorage.getItem(KEY));
    if (typeof value?.text === 'string') {
      // Preserve the appearance of legacy presets on this kiosk's viewport.
      const vmin = Math.min(window.innerWidth, window.innerHeight) / 100;
      const legacy = {
        small: Math.round(Math.max(16, Math.min(2 * vmin, 32))),
        medium: Math.round(Math.max(20, Math.min(3 * vmin, 48))),
        large: Math.round(Math.max(28, Math.min(4.5 * vmin, 72))),
      };
      const size = typeof value.size === 'string' && Object.hasOwn(legacy, value.size)
        ? legacy[value.size] : Number(value.size);
      return { text: value.text, size: Number.isInteger(size) && size >= MIN_CAPTION_SIZE && size <= MAX_CAPTION_SIZE ? size : 32 };
    }
  } catch { /* An empty caption is the default when local storage is unavailable. */ }
  return { text: '', size: 32 };
}

export function saveAdvertisingCaption(text, size) {
  const pixels = Number(size);
  if (!Number.isInteger(pixels) || pixels < MIN_CAPTION_SIZE || pixels > MAX_CAPTION_SIZE) throw new TypeError('invalid_caption_size');
  localStorage.setItem(KEY, JSON.stringify({ text: text.trim(), size: pixels }));
}

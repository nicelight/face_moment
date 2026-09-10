/** Local display duration; server session and QR lifetimes are independent. */
export const PROMO_DURATION_KEY = "face-moment.promo-display-seconds";
export const MAX_PROMO_SECONDS = Math.floor(2147483647 / 1000);

export function parsePromoSeconds(value) {
  if (!/^\d+$/.test(String(value))) return null;
  const seconds = Number(value);
  return Number.isSafeInteger(seconds) && seconds >= 1 && seconds <= MAX_PROMO_SECONDS ? seconds : null;
}

export function readPromoSeconds() {
  try { return parsePromoSeconds(globalThis.localStorage.getItem(PROMO_DURATION_KEY)); }
  catch { return null; }
}

export function promoDurationMs(serverDurationMs) {
  const seconds = readPromoSeconds();
  return seconds === null ? serverDurationMs : seconds * 1000;
}

export function savePromoSeconds(value) {
  const seconds = parsePromoSeconds(value);
  if (seconds === null) throw new TypeError("invalid_promo_seconds");
  globalThis.localStorage.setItem(PROMO_DURATION_KEY, String(seconds));
  return seconds;
}

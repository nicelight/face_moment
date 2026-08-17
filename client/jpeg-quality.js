export const JPEG_QUALITY_VALUES = Object.freeze([
  0.7,
  0.75,
  0.8,
  0.85,
  0.9,
  0.95,
]);
export const DEFAULT_JPEG_QUALITY = 0.85;
export const JPEG_QUALITY_STORAGE_KEY = "face-moment.jpeg-quality";

function storageOrNull(storage) {
  if (storage !== undefined) return storage;
  try {
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

function qualityFromValue(value) {
  if (typeof value === "number") {
    return JPEG_QUALITY_VALUES.includes(value) ? value : null;
  }
  if (typeof value === "string") {
    return (
      JPEG_QUALITY_VALUES.find((quality) => String(quality) === value) ?? null
    );
  }
  return null;
}

export function isAllowedJpegQuality(value) {
  return qualityFromValue(value) !== null;
}

export function normalizeJpegQuality(value) {
  const quality = qualityFromValue(value);
  if (quality === null) throw new RangeError("jpeg_quality_not_allowed");
  return quality;
}

function readStoredQuality(storage) {
  try {
    const stored = storage?.getItem(JPEG_QUALITY_STORAGE_KEY);
    if (stored === null || stored === undefined) return DEFAULT_JPEG_QUALITY;
    const quality = qualityFromValue(stored);
    if (quality !== null) return quality;
    storage.removeItem?.(JPEG_QUALITY_STORAGE_KEY);
  } catch {
    return DEFAULT_JPEG_QUALITY;
  }
  return DEFAULT_JPEG_QUALITY;
}

function freezeAttemptSnapshot(attemptId, jpegQuality) {
  return Object.freeze({ attemptId, jpegQuality });
}

export class JpegQualityController {
  constructor({ storage, onChange = () => {}, onAttemptStart = () => {} } = {}) {
    this.storage = storageOrNull(storage);
    this.onChange = onChange;
    this.onAttemptStart = onAttemptStart;
    this.configuredQuality = readStoredQuality(this.storage);
    this.activeAttempt = null;
    this.nextAttemptNumber = 1;
  }

  getQuality() {
    return this.configuredQuality;
  }

  setQuality(value) {
    const quality = normalizeJpegQuality(value);
    try {
      this.storage?.setItem(JPEG_QUALITY_STORAGE_KEY, String(quality));
    } catch (error) {
      throw new Error("jpeg_quality_persistence_failed", { cause: error });
    }
    this.configuredQuality = quality;
    this.onChange({ jpegQuality: quality, appliesFrom: "next-attempt" });
    return quality;
  }

  startAttempt(attemptId = `attempt-${this.nextAttemptNumber++}`) {
    if (this.activeAttempt) return this.activeAttempt;
    this.activeAttempt = freezeAttemptSnapshot(
      attemptId,
      this.configuredQuality,
    );
    this.onAttemptStart(this.activeAttempt);
    return this.activeAttempt;
  }

  getActiveAttemptSnapshot() {
    return this.activeAttempt;
  }

  finishAttempt(attemptId) {
    if (!this.activeAttempt) return null;
    if (attemptId !== undefined && attemptId !== this.activeAttempt.attemptId) {
      return this.activeAttempt;
    }
    const completed = this.activeAttempt;
    this.activeAttempt = null;
    return completed;
  }
}

export function createJpegQualityController(config) {
  return new JpegQualityController(config);
}

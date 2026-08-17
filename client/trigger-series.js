export const DEFAULT_CAPTURE_CONFIG = Object.freeze({
  preTriggerMs: 400,
  postTriggerMs: 2_000,
  frameIntervalMs: 300,
});

const TRIGGER_SOURCES = new Set(["physical", "test"]);
const BUSY_STATES = new Set(["capturing", "searching", "result", "cooldown"]);

function nowMs() {
  return globalThis.performance?.now?.() ?? Date.now();
}

function positiveNumber(value, fallback, name) {
  const number = value === undefined ? fallback : Number(value);
  if (!Number.isFinite(number) || number <= 0) {
    throw new TypeError(`${name}_must_be_positive`);
  }
  return number;
}

export function normalizeCaptureConfig(config = {}) {
  const normalized = {
    preTriggerMs: positiveNumber(
      config.preTriggerMs,
      DEFAULT_CAPTURE_CONFIG.preTriggerMs,
      "pre_trigger_ms",
    ),
    postTriggerMs: positiveNumber(
      config.postTriggerMs,
      DEFAULT_CAPTURE_CONFIG.postTriggerMs,
      "post_trigger_ms",
    ),
    frameIntervalMs: positiveNumber(
      config.frameIntervalMs,
      DEFAULT_CAPTURE_CONFIG.frameIntervalMs,
      "frame_interval_ms",
    ),
  };
  if (normalized.frameIntervalMs > normalized.postTriggerMs) {
    throw new TypeError("frame_interval_exceeds_post_trigger");
  }
  return Object.freeze(normalized);
}

export function normalizeTriggerSource(source) {
  const normalized = String(source ?? "").trim();
  if (!TRIGGER_SOURCES.has(normalized)) {
    throw new TypeError("trigger_source_invalid");
  }
  return normalized;
}

export class FrameRingBuffer {
  constructor({ maxAgeMs, clock = nowMs } = {}) {
    this.maxAgeMs = positiveNumber(maxAgeMs, 1_000, "ring_max_age_ms");
    this.clock = clock;
    this.frames = [];
  }

  prune(referenceTimestamp = this.clock()) {
    const oldest = referenceTimestamp - this.maxAgeMs;
    this.frames = this.frames.filter((entry) => entry.timestampMs >= oldest);
  }

  add(frame, timestampMs = this.clock()) {
    if (!frame || !Number.isFinite(timestampMs)) {
      throw new TypeError("ring_frame_invalid");
    }
    this.prune(timestampMs);
    const entry = { frame, timestampMs };
    this.frames.push(entry);
    return entry;
  }

  snapshot(referenceTimestamp = this.clock()) {
    this.prune(referenceTimestamp);
    return this.frames.map((entry) => ({ ...entry }));
  }

  clear() {
    this.frames = [];
  }

  get size() {
    return this.frames.length;
  }
}

function chronological(entries) {
  return entries
    .slice()
    .sort((left, right) => left.timestampMs - right.timestampMs)
    .map((entry) => entry.frame);
}

export class ReferenceCaptureController {
  constructor({
    captureFrame,
    cloneFrame = (frame) => frame,
    config,
    clock = nowMs,
    setIntervalImpl = globalThis.setInterval,
    clearIntervalImpl = globalThis.clearInterval,
    setTimeoutImpl = globalThis.setTimeout,
    clearTimeoutImpl = globalThis.clearTimeout,
    onAttemptStart = () => {},
    onReferenceSeriesReady = () => {},
    onStateChange = () => {},
    onIgnoredTrigger = () => {},
    onCaptureError = () => {},
  } = {}) {
    if (typeof captureFrame !== "function") {
      throw new TypeError("capture_frame_required");
    }
    this.config = normalizeCaptureConfig(config);
    this.clock = clock;
    this.captureFrame = captureFrame;
    this.cloneFrame = cloneFrame;
    this.setIntervalImpl = setIntervalImpl.bind?.(globalThis) ?? setIntervalImpl;
    this.clearIntervalImpl = clearIntervalImpl.bind?.(globalThis) ?? clearIntervalImpl;
    this.setTimeoutImpl = setTimeoutImpl.bind?.(globalThis) ?? setTimeoutImpl;
    this.clearTimeoutImpl = clearTimeoutImpl.bind?.(globalThis) ?? clearTimeoutImpl;
    this.onAttemptStart = onAttemptStart;
    this.onReferenceSeriesReady = onReferenceSeriesReady;
    this.onStateChange = onStateChange;
    this.onIgnoredTrigger = onIgnoredTrigger;
    this.onCaptureError = onCaptureError;
    this.ring = new FrameRingBuffer({
      maxAgeMs: this.config.preTriggerMs + this.config.frameIntervalMs,
      clock,
    });
    this.state = "advertising";
    this.started = false;
    this.samplingTimer = null;
    this.postTriggerTimer = null;
    this.cooldownTimer = null;
    this.attemptSequence = 0;
    this.activeAttempt = null;
  }

  setState(state, detail = {}) {
    this.state = state;
    this.onStateChange({ state, ...detail });
  }

  start() {
    if (this.started) return;
    this.started = true;
    this.sample();
    this.samplingTimer = this.setIntervalImpl(
      () => this.sample(),
      this.config.frameIntervalMs,
    );
  }

  stop() {
    if (this.samplingTimer !== null) {
      this.clearIntervalImpl(this.samplingTimer);
      this.samplingTimer = null;
    }
    if (this.postTriggerTimer !== null) {
      this.clearTimeoutImpl(this.postTriggerTimer);
      this.postTriggerTimer = null;
    }
    if (this.cooldownTimer !== null) {
      this.clearTimeoutImpl(this.cooldownTimer);
      this.cooldownTimer = null;
    }
    this.started = false;
  }

  sample() {
    const timestampMs = this.clock();
    try {
      const captured = this.captureFrame();
      if (captured) this.recordFrame(captured, timestampMs);
    } catch (error) {
      this.onCaptureError(error);
    }
  }

  recordFrame(captured, timestampMs = this.clock()) {
    if (!captured || !Number.isFinite(timestampMs)) return null;
    const frame = this.cloneFrame(captured);
    if (!frame) return null;
    const entry = this.ring.add(frame, timestampMs);
    if (
      this.activeAttempt &&
      timestampMs > this.activeAttempt.triggerAtMs &&
      timestampMs <= this.activeAttempt.captureEndsAtMs
    ) {
      this.activeAttempt.postFrames.push(entry);
    }
    return entry;
  }

  acceptTrigger(source, metadata = {}) {
    const triggerSource = normalizeTriggerSource(source);
    if (BUSY_STATES.has(this.state) || this.activeAttempt) {
      const ignored = {
        accepted: false,
        reason: "busy",
        state: this.state,
        trigger_source: triggerSource,
        ignoredAtMs: this.clock(),
      };
      this.onIgnoredTrigger(ignored);
      return ignored;
    }

    const triggerAtMs = this.clock();
    const preFrames = this.ring
      .snapshot(triggerAtMs)
      .filter(
        (entry) =>
          entry.timestampMs <= triggerAtMs &&
          entry.timestampMs >= triggerAtMs - this.config.preTriggerMs,
      );
    if (preFrames.length === 0) {
      const unavailable = {
        accepted: false,
        reason: "camera_unavailable",
        state: this.state,
        trigger_source: triggerSource,
      };
      this.onIgnoredTrigger(unavailable);
      return unavailable;
    }

    const attemptId = `attempt-${++this.attemptSequence}`;
    this.activeAttempt = {
      attemptId,
      trigger_source: triggerSource,
      triggerAtMs,
      captureEndsAtMs: triggerAtMs + this.config.postTriggerMs,
      preFrames,
      postFrames: [],
      metadata: { ...metadata },
    };
    this.setState("capturing", {
      attemptId,
      trigger_source: triggerSource,
    });
    const startDetail = {
      accepted: true,
      attemptId,
      trigger_source: triggerSource,
      trigger_at_ms: triggerAtMs,
      ...metadata,
    };
    this.onAttemptStart(startDetail);
    this.postTriggerTimer = this.setTimeoutImpl(
      () => this.finishCapture(attemptId),
      this.config.postTriggerMs,
    );
    return startDetail;
  }

  finishCapture(attemptId) {
    if (!this.activeAttempt || this.activeAttempt.attemptId !== attemptId) return null;
    const attempt = this.activeAttempt;
    this.postTriggerTimer = null;
    this.activeAttempt = null;
    this.setState("searching", { attemptId, trigger_source: attempt.trigger_source });
    const entries = [...attempt.preFrames, ...attempt.postFrames].filter(
      (entry, index, all) =>
        all.findIndex((candidate) => candidate.timestampMs === entry.timestampMs) === index,
    );
    const readyAtMs = this.clock();
    const detail = {
      attemptId,
      trigger_source: attempt.trigger_source,
      trigger_at_ms: attempt.triggerAtMs,
      reference_series_ready_at_ms: readyAtMs,
      frames: chronological(entries),
      frame_timestamps_ms: entries
        .slice()
        .sort((left, right) => left.timestampMs - right.timestampMs)
        .map((entry) => entry.timestampMs),
      metadata: { ...attempt.metadata },
    };
    this.onReferenceSeriesReady(detail);
    return detail;
  }

  finishAttempt({ success = false, cooldownMs = 0 } = {}) {
    if (this.activeAttempt) return false;
    if (success) {
      const cooldown = Number(cooldownMs);
      if (!Number.isFinite(cooldown) || cooldown < 0) {
        throw new TypeError("cooldown_ms_must_be_non_negative");
      }
      this.setState("cooldown");
      this.cooldownTimer = this.setTimeoutImpl(() => {
        this.cooldownTimer = null;
        this.ring.clear();
        this.setState("advertising");
      }, cooldown);
      return true;
    }
    this.ring.clear();
    this.setState("advertising");
    return true;
  }
}

export function createReferenceCaptureController(config) {
  return new ReferenceCaptureController(config);
}

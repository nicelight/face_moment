function browserMonotonicNow() {
  if (typeof globalThis.performance?.now !== "function") {
    throw new Error("client_monotonic_clock_unavailable");
  }
  return globalThis.performance.now();
}

function browserTimeOrigin() {
  return globalThis.performance?.timeOrigin;
}

function requireMonotonicMs(value, name) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) {
    throw new TypeError(`${name}_must_be_non_negative`);
  }
  return numeric;
}

function integerMs(value) {
  return Math.max(0, Math.round(value));
}

function correlationTimestamp({ readyMonotonicMs, timeOriginMs, wallClockNow }) {
  const origin = Number(timeOriginMs);
  const wallMs = Number.isFinite(origin)
    ? origin + readyMonotonicMs
    : Number(wallClockNow());
  const timestamp = new Date(wallMs);
  if (!Number.isFinite(timestamp.getTime())) {
    throw new TypeError("reference_series_ready_at_unavailable");
  }
  return timestamp.toISOString();
}

export function createAttemptTimingRecorder({
  attemptId,
  captureId,
  referenceSeriesReadyMonotonicMs,
  clock = browserMonotonicNow,
  timeOriginMs = browserTimeOrigin(),
  wallClockNow = Date.now,
} = {}) {
  if (typeof clock !== "function") throw new TypeError("clock_must_be_function");
  if (typeof wallClockNow !== "function") {
    throw new TypeError("wall_clock_must_be_function");
  }

  const readyMonotonicMs = requireMonotonicMs(
    referenceSeriesReadyMonotonicMs,
    "reference_series_ready_monotonic_ms",
  );
  const referenceSeriesReadyAt = correlationTimestamp({
    readyMonotonicMs,
    timeOriginMs,
    wallClockNow,
  });
  const markers = {
    referenceSeriesReadyElapsedMs: 0,
    localDetectionCompletedMs: null,
    requestStartedMs: null,
    responseReceivedMs: null,
  };

  function record(name, previousName) {
    if (markers[name] !== null) return markers[name];
    const currentMonotonicMs = requireMonotonicMs(clock(), name);
    const elapsed = currentMonotonicMs - readyMonotonicMs;
    if (elapsed < 0) {
      throw new Error("client_monotonic_markers_out_of_order");
    }
    const elapsedMs = integerMs(elapsed);
    const previous = markers[previousName];
    if (previous === null) {
      throw new Error(`${previousName}_marker_missing`);
    }
    if (elapsedMs < previous) {
      throw new Error("client_monotonic_markers_out_of_order");
    }
    markers[name] = elapsedMs;
    return elapsedMs;
  }

  function snapshot() {
    return {
      attemptId,
      captureId,
      referenceSeriesReadyAt,
      referenceSeriesReadyMonotonicMs: integerMs(readyMonotonicMs),
      ...markers,
    };
  }

  return {
    recordLocalDetectionCompleted() {
      return record(
        "localDetectionCompletedMs",
        "referenceSeriesReadyElapsedMs",
      );
    },
    recordRequestStarted() {
      return record("requestStartedMs", "localDetectionCompletedMs");
    },
    recordResponseReceived() {
      return record("responseReceivedMs", "requestStartedMs");
    },
    manifestTiming() {
      if (
        markers.localDetectionCompletedMs === null ||
        markers.requestStartedMs === null
      ) {
        throw new Error("request_timing_markers_incomplete");
      }
      return {
        referenceSeriesReadyAt,
        localDetectionCompletedMs: markers.localDetectionCompletedMs,
        requestStartedMs: markers.requestStartedMs,
      };
    },
    snapshot,
  };
}

const VALID_OUTCOMES = new Set([
  "result",
  "no_proposals",
  "busy",
  "deadline",
  "unacceptable_query",
  "insufficient_results",
  "interrupted",
  "in_progress",
]);

export const REALTIME_ATTEMPT_OUTCOMES = Object.freeze([
  ...VALID_OUTCOMES,
]);

function requireIdentity(value, name) {
  const normalized = String(value ?? "").trim();
  if (!normalized || normalized.length > 255) {
    throw new TypeError(`${name}_must_be_non_empty`);
  }
  return normalized;
}

function stateSnapshot(state, detail = {}) {
  return Object.freeze(
    Object.fromEntries(
      Object.entries({ state, ...detail }).filter(([, value]) => value !== undefined),
    ),
  );
}

function staleResult(attemptId, current) {
  return stateSnapshot(current?.state ?? "advertising", {
    handled: false,
    stale: true,
    attemptId,
    currentAttemptId: current?.attemptId,
  });
}

function responseFailure({ attemptId, status, reason }) {
  return {
    handled: true,
    stale: false,
    attemptId,
    state: "advertising",
    retryEligible: true,
    reason,
    ...(status === undefined ? {} : { status }),
  };
}

function typedResponse(payload, attemptId) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new TypeError("realtime_response_shape_invalid");
  }
  if (payload.schema_version !== 1 || payload.attempt_id !== attemptId) {
    throw new TypeError("realtime_response_identity_invalid");
  }
  if (!VALID_OUTCOMES.has(payload.outcome)) {
    throw new TypeError("realtime_outcome_invalid");
  }
  if (
    payload.outcome === "result" &&
    (!payload.result || typeof payload.result !== "object" || Array.isArray(payload.result))
  ) {
    throw new TypeError("realtime_result_shape_invalid");
  }
  return payload;
}

/**
 * Own the browser-local response branch after the request boundary.
 *
 * The controller deliberately has no timer, notice, Promo, QR or retry queue.
 * A caller supplies a new capture/series identity for every attempt; only the
 * current identity may change the state.
 */
export class AttemptOutcomeController {
  constructor({
    onStateChange = () => {},
    onOutcome = () => {},
  } = {}) {
    this.onStateChange = onStateChange;
    this.onOutcome = onOutcome;
    this.state = "advertising";
    this.current = null;
    this.resultAttemptId = null;
    this.startedAttemptIds = new Set();
    this.startedCaptureIds = new Set();
  }

  snapshot() {
    return stateSnapshot(this.state, {
      attemptId: this.current?.attemptId,
      captureId: this.current?.captureId,
    });
  }

  setState(state, detail = {}) {
    this.state = state;
    const snapshot = stateSnapshot(state, detail);
    this.onStateChange(snapshot);
    return snapshot;
  }

  beginAttempt({ attemptId, captureId = attemptId } = {}) {
    const normalizedAttemptId = requireIdentity(attemptId, "attempt_id");
    const normalizedCaptureId = requireIdentity(captureId, "capture_id");
    if (this.current || this.state === "result") {
      throw new Error("attempt_already_active");
    }
    if (
      this.startedAttemptIds.has(normalizedAttemptId) ||
      this.startedCaptureIds.has(normalizedCaptureId)
    ) {
      throw new Error("fresh_capture_required");
    }

    this.startedAttemptIds.add(normalizedAttemptId);
    this.startedCaptureIds.add(normalizedCaptureId);
    this.current = {
      attemptId: normalizedAttemptId,
      captureId: normalizedCaptureId,
    };
    return this.setState("searching", {
      attemptId: normalizedAttemptId,
      captureId: normalizedCaptureId,
    });
  }

  isCurrent(attemptId) {
    return this.current?.attemptId === String(attemptId ?? "");
  }

  finishFailure(attemptId, failure) {
    if (!this.isCurrent(attemptId)) return staleResult(attemptId, this.current);
    this.current = null;
    const result = responseFailure({ attemptId, ...failure });
    this.setState("advertising", {
      attemptId,
      retryEligible: true,
      reason: result.reason,
      ...(result.status === undefined ? {} : { status: result.status }),
    });
    this.onOutcome(result);
    return Object.freeze(result);
  }

  async handleResponse(attemptId, response) {
    if (!this.isCurrent(attemptId)) return staleResult(attemptId, this.current);
    const status = Number(response?.status);
    if (status !== 200) {
      return this.finishFailure(attemptId, {
        status,
        reason: "http_failure",
      });
    }

    let payload;
    try {
      if (typeof response?.json !== "function") {
        throw new TypeError("realtime_response_json_unavailable");
      }
      payload = typedResponse(await response.json(), String(attemptId));
    } catch {
      return this.finishFailure(attemptId, {
        status,
        reason: "typed_response_invalid",
      });
    }

    // The body may have resolved after a newer lifecycle event. Re-check the
    // identity before allowing a late response to mutate state.
    if (!this.isCurrent(attemptId)) return staleResult(attemptId, this.current);
    this.current = null;
    if (payload.outcome === "result") {
      this.resultAttemptId = attemptId;
      const result = Object.freeze({
        handled: true,
        stale: false,
        attemptId,
        state: "result",
        outcome: payload.outcome,
        result: payload.result,
        retryEligible: false,
      });
      this.setState("result", {
        attemptId,
        outcome: payload.outcome,
        resultAvailable: true,
        retryEligible: false,
      });
      this.onOutcome(result);
      return result;
    }

    const result = Object.freeze({
      handled: true,
      stale: false,
      attemptId,
      state: "advertising",
      outcome: payload.outcome,
      retryEligible: true,
    });
    this.setState("advertising", {
      attemptId,
      outcome: payload.outcome,
      retryEligible: true,
    });
    this.onOutcome(result);
    return result;
  }

  handleTransportFailure(attemptId) {
    return this.finishFailure(attemptId, {
      reason: "transport_failure",
    });
  }

  releaseResult(attemptId) {
    if (this.state !== "result") return false;
    if (
      attemptId !== undefined &&
      String(attemptId) !== this.resultAttemptId
    ) {
      return false;
    }
    this.resultAttemptId = null;
    this.setState("advertising", {
      attemptId,
      retryEligible: true,
    });
    return true;
  }
}

export function createAttemptOutcomeController(options) {
  return new AttemptOutcomeController(options);
}

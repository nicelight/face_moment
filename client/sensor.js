const PASSAGE_PATH = "/api/v1/passage-events/next";
const DEFAULT_POLL_TIMEOUT_MS = 10_000;
const DEFAULT_RETRY_DELAY_MS = 1_000;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function normalizeSensorHost(host) {
  const configured = String(host ?? "").trim();
  if (!configured) throw new Error("sensor_host_missing");

  const candidate = configured.includes("://")
    ? configured
    : `http://${configured}`;
  const url = new URL(candidate);
  if (!(["http:", "https:"].includes(url.protocol))) {
    throw new Error("sensor_host_protocol_invalid");
  }
  if (!url.hostname || url.username || url.password || url.search || url.hash) {
    throw new Error("sensor_host_not_fixed");
  }
  if (url.pathname !== "/" && url.pathname !== "") {
    throw new Error("sensor_host_path_invalid");
  }
  return url.origin;
}

function sensorEndpoint(host) {
  return `${normalizeSensorHost(host)}${PASSAGE_PATH}`;
}

function isNonNegativeInteger(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

export function decodePassageEvent(payload, expectedSensorId) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("passage_event_not_object");
  }

  const keys = Object.keys(payload).sort();
  const expectedKeys = ["boot_id", "schema_version", "sensor_id", "sequence", "type"];
  if (keys.length !== expectedKeys.length || keys.some((key, index) => key !== expectedKeys[index])) {
    throw new Error("passage_event_shape_invalid");
  }
  if (payload.schema_version !== 1 || payload.type !== "passage") {
    throw new Error("passage_event_version_or_type_invalid");
  }
  if (
    typeof payload.sensor_id !== "string" ||
    !payload.sensor_id ||
    (expectedSensorId !== undefined && payload.sensor_id !== expectedSensorId)
  ) {
    throw new Error("passage_event_sensor_invalid");
  }
  if (typeof payload.boot_id !== "string" || !UUID_PATTERN.test(payload.boot_id)) {
    throw new Error("passage_event_boot_invalid");
  }
  if (!isNonNegativeInteger(payload.sequence)) {
    throw new Error("passage_event_sequence_invalid");
  }

  return {
    schema_version: payload.schema_version,
    sensor_id: payload.sensor_id,
    boot_id: payload.boot_id,
    sequence: payload.sequence,
    type: payload.type,
  };
}

export class SensorPassageClient {
  constructor({
    host,
    secret,
    sensorId,
    fetchImpl = globalThis.fetch,
    setTimeoutImpl = globalThis.setTimeout,
    clearTimeoutImpl = globalThis.clearTimeout,
    pollTimeoutMs = DEFAULT_POLL_TIMEOUT_MS,
    retryDelayMs = DEFAULT_RETRY_DELAY_MS,
    onEvent = () => {},
    onStatus = () => {},
  }) {
    if (typeof fetchImpl !== "function") throw new Error("fetch_unavailable");
    if (!String(secret ?? "")) throw new Error("sensor_secret_missing");
    if (!String(sensorId ?? "")) throw new Error("sensor_id_missing");

    this.endpoint = sensorEndpoint(host);
    this.authorization = `Bearer ${secret}`;
    this.sensorId = sensorId;
    this.fetchImpl = fetchImpl.bind(globalThis);
    this.setTimeoutImpl = setTimeoutImpl.bind(globalThis);
    this.clearTimeoutImpl = clearTimeoutImpl.bind(globalThis);
    this.pollTimeoutMs = pollTimeoutMs;
    this.retryDelayMs = retryDelayMs;
    this.onEvent = onEvent;
    this.onStatus = onStatus;
    this.seenEvents = new Set();
    this.running = false;
    this.pendingController = null;
    this.retryTimer = null;
  }

  start() {
    if (this.running) return;
    this.running = true;
    void this.poll();
  }

  stop() {
    this.running = false;
    if (this.retryTimer !== null) {
      this.clearTimeoutImpl(this.retryTimer);
      this.retryTimer = null;
    }
    this.pendingController?.abort();
    this.pendingController = null;
  }

  async poll() {
    if (!this.running || this.pendingController) return;

    const controller = new AbortController();
    this.pendingController = controller;
    const timeout = this.setTimeoutImpl(
      () => controller.abort(),
      this.pollTimeoutMs,
    );
    let nextAction = "retry";

    this.onStatus("polling");
    try {
      const response = await this.fetchImpl(this.endpoint, {
        method: "GET",
        mode: "cors",
        credentials: "omit",
        headers: {
          Accept: "application/json",
          Authorization: this.authorization,
        },
        signal: controller.signal,
      });

      if (response.status === 204) {
        nextAction = "immediate";
        this.onStatus("advertising");
      } else if (response.status === 200) {
        nextAction = "immediate";
        try {
          const event = decodePassageEvent(await response.json(), this.sensorId);
          const eventKey = `${event.boot_id}:${event.sequence}`;
          if (!this.seenEvents.has(eventKey)) {
            this.seenEvents.add(eventKey);
            this.onEvent(event);
          }
          this.onStatus("passage");
        } catch {
          this.onStatus("recoverable-error");
        }
      } else if (response.status === 401 || response.status === 403) {
        this.onStatus("recoverable-error");
      } else {
        this.onStatus("recoverable-error");
      }
    } catch (error) {
      if (!controller.signal.aborted || this.running) {
        this.onStatus("recoverable-error");
      }
    } finally {
      this.clearTimeoutImpl(timeout);
      if (this.pendingController === controller) this.pendingController = null;
    }

    if (!this.running) return;
    if (nextAction === "immediate") {
      void this.poll();
      return;
    }
    this.retryTimer = this.setTimeoutImpl(() => {
      this.retryTimer = null;
      void this.poll();
    }, this.retryDelayMs);
  }
}

export function createSensorPassageClient(config) {
  return new SensorPassageClient(config);
}

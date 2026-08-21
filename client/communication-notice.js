export const COMMUNICATION_NOTICE_DURATION_MS = 7_000;

const NOTICE_PREFIX = "Попытка связи с сервером была не успешна в ";

function padTimePart(value) {
  return String(value).padStart(2, "0");
}

export function formatServerCommunicationNotice(timestampMs) {
  const date = new Date(Number(timestampMs));
  if (!Number.isFinite(date.getTime())) {
    throw new TypeError("communication_notice_time_invalid");
  }

  const localTime = [
    date.getHours(),
    date.getMinutes(),
    date.getSeconds(),
  ].map(padTimePart).join(":");
  return `${NOTICE_PREFIX}${localTime}`;
}

export class CommunicationNoticeController {
  constructor({
    element,
    clock = Date.now,
    setTimeoutImpl = (callback, delay) => globalThis.setTimeout(callback, delay),
    clearTimeoutImpl = (timer) => globalThis.clearTimeout(timer),
    durationMs = COMMUNICATION_NOTICE_DURATION_MS,
  } = {}) {
    if (!element) throw new TypeError("communication_notice_element_missing");
    if (typeof clock !== "function") throw new TypeError("clock_must_be_function");
    if (typeof setTimeoutImpl !== "function") {
      throw new TypeError("set_timeout_must_be_function");
    }
    if (typeof clearTimeoutImpl !== "function") {
      throw new TypeError("clear_timeout_must_be_function");
    }
    if (!Number.isFinite(durationMs) || durationMs < 5_000 || durationMs > 10_000) {
      throw new RangeError("communication_notice_duration_out_of_range");
    }

    this.element = element;
    this.clock = clock;
    this.setTimeoutImpl = setTimeoutImpl;
    this.clearTimeoutImpl = clearTimeoutImpl;
    this.durationMs = durationMs;
    this.timer = null;
    this.generation = 0;
    this.hide();
  }

  show() {
    const message = formatServerCommunicationNotice(this.clock());
    this.generation += 1;
    const generation = this.generation;
    if (this.timer !== null) this.clearTimeoutImpl(this.timer);

    this.element.textContent = message;
    this.element.hidden = false;
    this.timer = this.setTimeoutImpl(() => {
      if (generation !== this.generation) return;
      this.timer = null;
      this.hide();
    }, this.durationMs);
    return Object.freeze({ message, durationMs: this.durationMs });
  }

  hide() {
    this.generation += 1;
    if (this.timer !== null) this.clearTimeoutImpl(this.timer);
    this.timer = null;
    this.element.hidden = true;
    this.element.textContent = "";
  }
}

export function createCommunicationNoticeController(options) {
  return new CommunicationNoticeController(options);
}

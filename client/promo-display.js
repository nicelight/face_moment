import { applySavedPromoLayout } from "./promo-layout.js";
import { promoDurationMs } from "./promo-display-preferences.js";
import { getDisplayRequestHeaders } from "./display-client-config.js";

const PROMO_COPY = "Ваши фото можно скачать по QR коду или на сайте face-momet.ru";
const MEDIA_PATH_PREFIX = "/api/promo/media/";
const DISPLAY_CONFIG_PATH = "/api/promo/display/config";
const DISPLAY_PATH_PREFIX = "/api/promo/sessions/";
const DISPLAY_ACK_TIMEOUT_MS = 5_000;
const DISPLAY_LOADING_DEADLINE_MS = 5_000;
const QR_VERSION = Object.freeze({
  4: Object.freeze({ dimension: 33, dataCodewords: 64, blocks: 2, blockData: 32, ecCodewords: 18, alignment: [6, 26] }),
  5: Object.freeze({ dimension: 37, dataCodewords: 86, blocks: 2, blockData: 43, ecCodewords: 24, alignment: [6, 30] }),
});
const FORMAT_GENERATOR = 0x537;
const FORMAT_MASK = 0x5412;

export const PROMO_COPY_TEXT = PROMO_COPY;
export const PROMO_FAILURE_REASONS = Object.freeze([
  "invalid_result",
  "media_failure",
  "media_decode_failure",
  "qr_failure",
  "render_failure",
]);

function defaultOrigin() {
  return typeof globalThis.location?.origin === "string"
    ? globalThis.location.origin
    : "https://face-moment.test";
}

function requireObject(value, name) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(`${name}_invalid`);
  }
  return value;
}

function sameOriginUrl(value, origin, name) {
  if (typeof value !== "string" || !value) throw new TypeError(`${name}_invalid`);
  let parsed;
  try {
    parsed = new URL(value, origin);
  } catch {
    throw new TypeError(`${name}_invalid`);
  }
  if (parsed.origin !== new URL(origin).origin) {
    throw new TypeError(`${name}_origin_invalid`);
  }
  return parsed;
}

export function validatePromoResult(result, { origin = defaultOrigin() } = {}) {
  const payload = requireObject(result, "promo_result");
  if (typeof payload.session_id !== "string" || !payload.session_id.trim()) {
    throw new TypeError("promo_session_id_invalid");
  }
  if (!Number.isSafeInteger(payload.n) || payload.n < 4) {
    throw new TypeError("promo_n_invalid");
  }
  if (!Array.isArray(payload.teasers) || payload.teasers.length !== 4) {
    throw new TypeError("promo_teasers_must_contain_four");
  }

  const photoIds = new Set();
  const teasers = payload.teasers.map((teaser) => {
    const item = requireObject(teaser, "promo_teaser");
    if (typeof item.photo_id !== "string" || !item.photo_id.trim()) {
      throw new TypeError("promo_photo_id_invalid");
    }
    if (photoIds.has(item.photo_id)) throw new TypeError("promo_teasers_not_unique");
    photoIds.add(item.photo_id);
    const mediaUrl = sameOriginUrl(item.media_url, origin, "promo_media_url");
    if (!mediaUrl.pathname.startsWith(MEDIA_PATH_PREFIX)) {
      throw new TypeError("promo_media_url_path_invalid");
    }
    return Object.freeze({
      photo_id: item.photo_id,
      media_url: mediaUrl.href,
    });
  });

  const qrUrl = sameOriginUrl(payload.qr_url, origin, "promo_qr_url");
  const qrTicket = qrUrl.searchParams.get("ticket");
  if (qrUrl.pathname !== "/q" || !qrTicket?.trim()) {
    throw new TypeError("promo_qr_url_path_invalid");
  }
  return Object.freeze({
    session_id: payload.session_id,
    teasers: Object.freeze(teasers),
    n: payload.n,
    qr_url: qrUrl.href,
    qr_first_open_expires_at: payload.qr_first_open_expires_at,
  });
}

export function validateDisplayConfiguration(configuration) {
  if (
    !configuration ||
    typeof configuration !== "object" ||
    Array.isArray(configuration)
  ) {
    throw new TypeError("promo_display_configuration_invalid");
  }
  const fields = Object.keys(configuration).sort().join(",");
  if (fields !== "result_display_ms,schema_version,success_cooldown_ms") {
    throw new TypeError("promo_display_configuration_fields_invalid");
  }
  if (!Number.isSafeInteger(configuration.schema_version) || configuration.schema_version !== 1) {
    throw new TypeError("promo_display_configuration_schema_invalid");
  }
  for (const name of ["result_display_ms", "success_cooldown_ms"]) {
    if (!Number.isSafeInteger(configuration[name]) || configuration[name] <= 0) {
      throw new TypeError(`promo_${name}_invalid`);
    }
  }
  return Object.freeze({
    schema_version: 1,
    result_display_ms: configuration.result_display_ms,
    success_cooldown_ms: configuration.success_cooldown_ms,
  });
}

function gfTables() {
  const exponent = new Uint8Array(512);
  const logarithm = new Int16Array(256);
  let value = 1;
  for (let index = 0; index < 255; index += 1) {
    exponent[index] = value;
    logarithm[value] = index;
    value <<= 1;
    if (value & 0x100) value ^= 0x11d;
  }
  for (let index = 255; index < exponent.length; index += 1) {
    exponent[index] = exponent[index - 255];
  }
  return { exponent, logarithm };
}

const GF = gfTables();

function gfMultiply(left, right) {
  if (left === 0 || right === 0) return 0;
  return GF.exponent[GF.logarithm[left] + GF.logarithm[right]];
}

function rsGenerator(degree) {
  let polynomial = [1];
  for (let index = 0; index < degree; index += 1) {
    const next = Array(polynomial.length + 1).fill(0);
    for (let coefficient = 0; coefficient < polynomial.length; coefficient += 1) {
      next[coefficient] ^= polynomial[coefficient];
      next[coefficient + 1] ^= gfMultiply(
        polynomial[coefficient],
        GF.exponent[index],
      );
    }
    polynomial = next;
  }
  return polynomial;
}

function errorCorrection(data, count) {
  const generator = rsGenerator(count);
  const remainder = Array(count).fill(0);
  for (const byte of data) {
    const factor = byte ^ remainder[0];
    for (let index = 0; index < count - 1; index += 1) {
      remainder[index] =
        remainder[index + 1] ^ gfMultiply(factor, generator[index + 1]);
    }
    remainder[count - 1] = gfMultiply(factor, generator[count]);
  }
  return remainder;
}

function appendBits(target, value, length) {
  for (let bit = length - 1; bit >= 0; bit -= 1) {
    target.push((value >>> bit) & 1);
  }
}

function bytesForText(text) {
  if (typeof TextEncoder !== "function") throw new Error("text_encoder_unavailable");
  return Array.from(new TextEncoder().encode(text));
}

function dataCodewords(text, config) {
  const bytes = bytesForText(text);
  const bits = [];
  appendBits(bits, 0b0100, 4);
  appendBits(bits, bytes.length, 8);
  for (const byte of bytes) appendBits(bits, byte, 8);
  const capacity = config.dataCodewords * 8;
  if (bits.length > capacity) throw new RangeError("qr_payload_too_large");
  appendBits(bits, 0, Math.min(4, capacity - bits.length));
  while (bits.length % 8 !== 0) bits.push(0);

  const bytesOut = [];
  for (let index = 0; index < bits.length; index += 8) {
    let value = 0;
    for (let bit = 0; bit < 8; bit += 1) value = (value << 1) | bits[index + bit];
    bytesOut.push(value);
  }
  const pads = [0xec, 0x11];
  let padIndex = 0;
  while (bytesOut.length < config.dataCodewords) {
    bytesOut.push(pads[padIndex % 2]);
    padIndex += 1;
  }
  return bytesOut;
}

function interleaveCodewords(data, config) {
  const blocks = [];
  for (let block = 0; block < config.blocks; block += 1) {
    const start = block * config.blockData;
    const blockData = data.slice(start, start + config.blockData);
    blocks.push({ data: blockData, ec: errorCorrection(blockData, config.ecCodewords) });
  }
  const result = [];
  for (let index = 0; index < config.blockData; index += 1) {
    for (const block of blocks) result.push(block.data[index]);
  }
  for (let index = 0; index < config.ecCodewords; index += 1) {
    for (const block of blocks) result.push(block.ec[index]);
  }
  return result;
}

function bchDigit(value) {
  let digits = 0;
  while (value !== 0) {
    digits += 1;
    value >>>= 1;
  }
  return digits;
}

function bchTypeInfo(value) {
  let remainder = value << 10;
  while (bchDigit(remainder) >= bchDigit(FORMAT_GENERATOR)) {
    remainder ^= FORMAT_GENERATOR << (bchDigit(remainder) - bchDigit(FORMAT_GENERATOR));
  }
  return ((value << 10) | remainder) ^ FORMAT_MASK;
}

function setFinder(matrix, row, column) {
  for (let r = -1; r <= 7; r += 1) {
    for (let c = -1; c <= 7; c += 1) {
      const targetRow = row + r;
      const targetColumn = column + c;
      if (
        targetRow < 0 ||
        targetRow >= matrix.length ||
        targetColumn < 0 ||
        targetColumn >= matrix.length
      ) continue;
      matrix[targetRow][targetColumn] =
        (r >= 0 && r <= 6 && (c === 0 || c === 6)) ||
        (c >= 0 && c <= 6 && (r === 0 || r === 6)) ||
        (r >= 2 && r <= 4 && c >= 2 && c <= 4);
    }
  }
}

function setAlignment(matrix, row, column) {
  for (let r = -2; r <= 2; r += 1) {
    for (let c = -2; c <= 2; c += 1) {
      if (matrix[row + r][column + c] !== null) return;
    }
  }
  for (let r = -2; r <= 2; r += 1) {
    for (let c = -2; c <= 2; c += 1) {
      matrix[row + r][column + c] =
        Math.max(Math.abs(r), Math.abs(c)) === 2 || (r === 0 && c === 0);
    }
  }
}

function applyFormat(matrix, mask) {
  const bits = bchTypeInfo(mask);
  const size = matrix.length;
  for (let index = 0; index < 15; index += 1) {
    const dark = ((bits >>> index) & 1) === 1;
    if (index < 6) matrix[index][8] = dark;
    else if (index < 8) matrix[index + 1][8] = dark;
    else matrix[size - 15 + index][8] = dark;

    if (index < 8) matrix[8][size - index - 1] = dark;
    else if (index < 9) matrix[8][15 - index] = dark;
    else matrix[8][15 - index - 1] = dark;
  }
  matrix[size - 8][8] = true;
}

function maskBit(mask, row, column) {
  switch (mask) {
    case 0: return (row + column) % 2 === 0;
    case 1: return row % 2 === 0;
    case 2: return column % 3 === 0;
    case 3: return (row + column) % 3 === 0;
    case 4: return (Math.floor(row / 2) + Math.floor(column / 3)) % 2 === 0;
    case 5: return (row * column) % 2 + (row * column) % 3 === 0;
    case 6: return ((row * column) % 2 + (row * column) % 3) % 2 === 0;
    case 7: return ((row * column) % 3 + (row + column) % 2) % 2 === 0;
    default: throw new RangeError("qr_mask_invalid");
  }
}

function buildMatrix(codewords, config, mask = 0) {
  const size = config.dimension;
  const matrix = Array.from({ length: size }, () => Array(size).fill(null));
  setFinder(matrix, 0, 0);
  setFinder(matrix, size - 7, 0);
  setFinder(matrix, 0, size - 7);

  for (let index = 8; index < size - 8; index += 1) {
    if (matrix[index][6] === null) matrix[index][6] = index % 2 === 0;
    if (matrix[6][index] === null) matrix[6][index] = index % 2 === 0;
  }
  for (const row of config.alignment) {
    for (const column of config.alignment) setAlignment(matrix, row, column);
  }

  // Keep the format-information modules out of the data zig-zag. They are
  // written after data placement, but must already be reserved here.
  for (let index = 0; index < 6; index += 1) matrix[index][8] = false;
  matrix[7][8] = false;
  for (let index = size - 7; index < size; index += 1) matrix[index][8] = false;
  for (let index = 0; index < 6; index += 1) matrix[8][index] = false;
  matrix[8][7] = false;
  matrix[8][8] = false;
  for (let index = size - 8; index < size; index += 1) matrix[8][index] = false;

  const bits = [];
  for (const byte of codewords) appendBits(bits, byte, 8);
  let bitIndex = 0;
  let row = size - 1;
  let direction = -1;
  for (let column = size - 1; column > 0; column -= 2) {
    if (column === 6) column -= 1;
    while (true) {
      for (let offset = 0; offset < 2; offset += 1) {
        const targetColumn = column - offset;
        if (matrix[row][targetColumn] !== null) continue;
        let dark = bitIndex < bits.length ? bits[bitIndex] === 1 : false;
        bitIndex += 1;
        if (maskBit(mask, row, targetColumn)) dark = !dark;
        matrix[row][targetColumn] = dark;
      }
      row += direction;
      if (row < 0 || row >= size) {
        row -= direction;
        direction = -direction;
        break;
      }
    }
  }
  applyFormat(matrix, mask);
  return matrix.map((line) => line.map((cell) => cell === true));
}

export function qrMatrixForText(text) {
  if (typeof text !== "string" || !text) throw new TypeError("qr_text_invalid");
  const bytes = bytesForText(text);
  const config = bytes.length <= 62 ? QR_VERSION[4] : QR_VERSION[5];
  const data = dataCodewords(text, config);
  return buildMatrix(interleaveCodewords(data, config), config);
}

function createQrSvg(documentImpl, text) {
  const matrix = qrMatrixForText(text);
  const quiet = 4;
  const size = matrix.length + quiet * 2;
  const svg = documentImpl.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "QR-код для продолжения сессии");
  svg.setAttribute("data-qr-content", text);
  svg.setAttribute("shape-rendering", "crispEdges");

  const background = documentImpl.createElementNS("http://www.w3.org/2000/svg", "rect");
  background.setAttribute("x", "0");
  background.setAttribute("y", "0");
  background.setAttribute("width", String(size));
  background.setAttribute("height", String(size));
  background.setAttribute("fill", "#ffffff");
  svg.append(background);
  const modules = documentImpl.createElementNS("http://www.w3.org/2000/svg", "g");
  modules.setAttribute("fill", "#000000");
  matrix.forEach((line, row) => line.forEach((dark, column) => {
    if (!dark) return;
    const module = documentImpl.createElementNS("http://www.w3.org/2000/svg", "rect");
    module.setAttribute("x", String(column + quiet));
    module.setAttribute("y", String(row + quiet));
    module.setAttribute("width", "1");
    module.setAttribute("height", "1");
    modules.append(module);
  }));
  svg.append(modules);
  return { svg, matrix, text };
}

function operationAbortedError() {
  const error = new Error("promo_operation_cancelled");
  error.name = "AbortError";
  return error;
}

function throwIfOperationAborted(signal) {
  if (signal?.aborted) throw operationAbortedError();
}

async function loadPreview({ teaser, fetchImpl, imageFactory, urlApi, signal, onObjectUrl }) {
  throwIfOperationAborted(signal);
  let response;
  let blob;
  try {
    response = await fetchImpl(teaser.media_url, {
      headers: { ...getDisplayRequestHeaders(), "Cache-Control": "no-cache" },
      credentials: "same-origin",
      cache: "no-store",
      signal,
    });
    if (!response?.ok) throw new Error("promo_media_fetch_failed");
    blob = await response.blob();
    throwIfOperationAborted(signal);
  } catch (error) {
    if (signal?.aborted) throw operationAbortedError();
    if (error?.message === "promo_media_fetch_failed") throw error;
    throw new Error("promo_media_fetch_failed");
  }
  const image = imageFactory();
  image.alt = `Найденная фотография ${teaser.photo_id}`;
  image.className = "promo-teaser";
  const objectUrl = urlApi.createObjectURL(blob);
  // Register immediately so timeout/stale cleanup also covers previews that
  // finish after Promise.all has already rejected.
  onObjectUrl?.(objectUrl);
  image.src = objectUrl;
  try {
    throwIfOperationAborted(signal);
    if (typeof image.decode === "function") await image.decode();
    else await new Promise((resolve, reject) => {
      image.addEventListener("load", resolve, { once: true });
      image.addEventListener("error", () => reject(new Error("promo_media_decode_failed")), { once: true });
    });
    throwIfOperationAborted(signal);
  } catch (error) {
    if (signal?.aborted) throw operationAbortedError();
    if (error?.message === "promo_media_decode_failed") throw error;
    throw new Error("promo_media_decode_failed");
  }
  return image;
}

export class PromoDisplayController {
  constructor({
    container,
    fetchImpl = globalThis.fetch,
    documentImpl = globalThis.document,
    imageFactory = () => new globalThis.Image(),
    urlApi = globalThis.URL,
    onComplete = () => {},
    onLoading = () => {},
    onPrepared = () => {},
    onFailure = () => {},
    onExpired = () => {},
    clock = () => globalThis.performance?.now?.(),
    setTimeoutImpl = (callback, delay) => globalThis.setTimeout(callback, delay),
    clearTimeoutImpl = (timer) => globalThis.clearTimeout(timer),
    setLoadingTimeoutImpl = (callback, delay) => globalThis.setTimeout(callback, delay),
    clearLoadingTimeoutImpl = (timer) => globalThis.clearTimeout(timer),
    loadingDeadlineMs = DISPLAY_LOADING_DEADLINE_MS,
    requireDisplayConfig = false,
    origin = defaultOrigin(),
  } = {}) {
    if (!container || typeof container.replaceChildren !== "function") {
      throw new TypeError("promo_container_missing");
    }
    if (typeof fetchImpl !== "function") throw new TypeError("promo_fetch_missing");
    if (!documentImpl) throw new TypeError("promo_document_missing");
    this.container = container;
    this.fetchImpl = fetchImpl.bind(globalThis);
    this.document = documentImpl;
    this.imageFactory = imageFactory;
    this.urlApi = urlApi;
    this.onComplete = onComplete;
    this.onLoading = onLoading;
    this.onPrepared = onPrepared;
    this.onFailure = onFailure;
    this.onExpired = onExpired;
    this.clock = clock;
    this.setTimeoutImpl = setTimeoutImpl;
    this.clearTimeoutImpl = clearTimeoutImpl;
    this.setLoadingTimeoutImpl = setLoadingTimeoutImpl;
    this.clearLoadingTimeoutImpl = clearLoadingTimeoutImpl;
    this.loadingDeadlineMs = loadingDeadlineMs;
    this.requireDisplayConfig = requireDisplayConfig;
    this.origin = origin;
    this.generation = 0;
    this.isVisible = false;
    this.displayExpiryTimer = null;
    this.pendingControllers = new Set();
    this.displayConfigurationOperations = new Map();
    this.previewResources = new Set();
    this.renderedCard = null;
    this.lastResult = null;
    this.isReplaying = false;
  }

  beginPreviewResource() {
    const resource = { objectUrls: new Set(), released: false };
    this.previewResources.add(resource);
    return resource;
  }

  registerPreviewObjectUrl(resource, objectUrl) {
    if (!resource || typeof objectUrl !== "string" || !objectUrl) return;
    if (resource.released) {
      this.revokePreviewObjectUrl(objectUrl);
      return;
    }
    resource.objectUrls.add(objectUrl);
  }

  revokePreviewObjectUrl(objectUrl) {
    if (typeof this.urlApi?.revokeObjectURL !== "function") return;
    try {
      this.urlApi.revokeObjectURL(objectUrl);
    } catch {
      // Cleanup must not mask the result/failure path.
    }
  }

  releasePreviewResource(resource) {
    if (!resource || resource.released) return;
    resource.released = true;
    for (const objectUrl of resource.objectUrls) {
      this.revokePreviewObjectUrl(objectUrl);
    }
    resource.objectUrls.clear();
    this.previewResources.delete(resource);
  }

  releasePreviewResources() {
    for (const resource of [...this.previewResources]) {
      this.releasePreviewResource(resource);
    }
  }

  removeRenderedCard() {
    const card = this.renderedCard;
    this.renderedCard = null;
    if (!card) return;
    const children = Array.from(
      this.container.childNodes ?? this.container.children ?? [],
    );
    if (!children.includes(card)) return;
    this.container.replaceChildren(...children.filter((child) => child !== card));
  }

  beginPendingOperation() {
    const controller = new AbortController();
    this.pendingControllers.add(controller);
    return controller;
  }

  endPendingOperation(controller) {
    this.pendingControllers.delete(controller);
  }

  cancelPendingWork() {
    const controllers = new Set(this.pendingControllers);
    for (const operation of this.displayConfigurationOperations.values()) {
      controllers.add(operation.controller);
    }
    for (const controller of controllers) controller.abort();
  }

  cancelDisplayConfiguration(attemptId) {
    const operation = this.displayConfigurationOperations.get(String(attemptId ?? ""));
    operation?.controller.abort();
  }

  runWithDeadline(operation, { controller, timeoutMs, timeoutError }) {
    const signal = controller?.signal;
    const work = Promise.resolve(operation);
    let timer = null;
    let abortListener = null;
    return new Promise((resolve, reject) => {
      let settled = false;
      const settle = (callback, value) => {
        if (settled) return;
        settled = true;
        callback(value);
      };
      work.then(
        (value) => settle(resolve, value),
        (error) => settle(reject, error),
      );
      if (signal?.aborted) {
        settle(reject, operationAbortedError());
        return;
      }
      abortListener = () => settle(reject, operationAbortedError());
      signal?.addEventListener("abort", abortListener, { once: true });
      timer = this.setLoadingTimeoutImpl(() => {
        settle(reject, timeoutError);
        controller?.abort();
      }, timeoutMs);
    }).finally(() => {
      if (timer !== null) this.clearLoadingTimeoutImpl(timer);
      signal?.removeEventListener("abort", abortListener);
    });
  }

  async loadDisplayConfiguration({ attemptId, onIdentity } = {}) {
    const controller = this.beginPendingOperation();
    const key = attemptId === undefined ? controller : String(attemptId);
    if (attemptId !== undefined) this.cancelDisplayConfiguration(attemptId);
    const operation = { controller };
    this.displayConfigurationOperations.set(key, operation);
    const work = Promise.resolve().then(async () => {
      const response = await this.fetchImpl(DISPLAY_CONFIG_PATH, {
        headers: getDisplayRequestHeaders(),
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
      });
      throwIfOperationAborted(controller.signal);
      if (response?.status !== 200 || !response?.ok || typeof response.json !== "function") {
        throw new Error("promo_display_configuration_unavailable");
      }
      const payload = await response.json();
      throwIfOperationAborted(controller.signal);
      const configuration = validateDisplayConfiguration(payload);
      onIdentity?.(
        response.headers?.get?.("X-Face-Moment-Display-Client-Id") ?? null,
        response.headers?.get?.("X-Face-Moment-Display-Name") ?? "",
      );
      return configuration;
    });
    const pending = this.runWithDeadline(work, {
      controller,
      timeoutMs: this.loadingDeadlineMs,
      timeoutError: new Error("promo_display_configuration_timeout"),
    });
    const cleanup = () => {
      if (this.displayConfigurationOperations.get(key) === operation) {
        this.displayConfigurationOperations.delete(key);
      }
      this.endPendingOperation(controller);
    };
    pending.then(cleanup, cleanup);
    return pending;
  }

  clearDisplayExpiryTimer() {
    if (this.displayExpiryTimer !== null) {
      this.clearTimeoutImpl(this.displayExpiryTimer);
      this.displayExpiryTimer = null;
    }
  }

  scheduleDisplayExpiry(attemptId, durationMs, replay = false) {
    this.clearDisplayExpiryTimer();
    const generation = this.generation;
    this.displayExpiryTimer = this.setTimeoutImpl(() => {
      this.displayExpiryTimer = null;
      if (generation !== this.generation || !this.isVisible) return;
      this.cancelPendingWork();
      this.generation += 1;
      this.isVisible = false;
      this.isReplaying = false;
      this.removeRenderedCard();
      this.releasePreviewResources();
      this.onExpired(Object.freeze({
        handled: true,
        stale: false,
        attemptId,
        state: "advertising",
        reason: "display_expired",
        resultDisplayMs: durationMs,
        ...(replay ? { replay: true } : {}),
      }));
    }, durationMs);
  }

  async reportDisplay({ sessionId, status, qrFullyVisibleElapsedMs }) {
    const path = `${DISPLAY_PATH_PREFIX}${encodeURIComponent(sessionId)}/display`;
    const body = status === "confirmed"
      ? {
          schema_version: 1,
          status,
          qr_fully_visible_elapsed_ms: qrFullyVisibleElapsedMs,
        }
      : { schema_version: 1, status };
    const controller = this.beginPendingOperation();
    const work = Promise.resolve().then(async () => {
      const response = await this.fetchImpl(path, {
        method: "PUT",
        headers: getDisplayRequestHeaders({ "Content-Type": "application/json" }),
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
        body: JSON.stringify(body),
      });
      if (!response?.ok) {
        const error = new Error("promo_display_acknowledgement_failed");
        error.httpStatus = response?.status;
        throw error;
      }
      return { status: response.status };
    });
    try {
      return await this.runWithDeadline(work, {
        controller,
        timeoutMs: DISPLAY_ACK_TIMEOUT_MS,
        timeoutError: new Error("promo_display_acknowledgement_timeout"),
      });
    } finally {
      this.endPendingOperation(controller);
    }
  }

  qrFullyVisibleElapsedMs(timing) {
    const ready = Number(timing?.referenceSeriesReadyMonotonicMs);
    if (!Number.isFinite(ready) || ready < 0 || typeof this.clock !== "function") {
      return null;
    }
    const current = Number(this.clock());
    const elapsed = Math.round(current - ready);
    if (!Number.isFinite(current) || elapsed < 0) {
      throw new Error("promo_qr_elapsed_invalid");
    }
    return elapsed;
  }

  replayLastResult() {
    if (!this.lastResult || this.isVisible || this.isReplaying) {
      return Promise.resolve({ handled: false });
    }
    return this.showResult({ ...this.lastResult, replay: true });
  }

  async showResult({ attemptId, result, timing, displayConfig, replay = false }) {
    this.cancelPendingWork();
    this.removeRenderedCard();
    this.releasePreviewResources();
    const generation = ++this.generation;
    this.clearDisplayExpiryTimer();
    this.isVisible = false;
    this.isReplaying = replay;
    let normalized;
    let previewResource = null;
    try {
      normalized = validatePromoResult(result, { origin: this.origin });
      const configuration = displayConfig === undefined
        ? null
        : validateDisplayConfiguration(displayConfig);
      if (this.requireDisplayConfig && configuration === null) {
        throw new Error("promo_display_configuration_missing");
      }
      previewResource = this.beginPreviewResource();
      const previewController = this.beginPendingOperation();
      let images;
      if (!replay) this.onLoading({ attemptId });
      try {
        images = await this.runWithDeadline(
          Promise.all(
            normalized.teasers.map((teaser) => loadPreview({
              teaser,
              fetchImpl: this.fetchImpl,
              imageFactory: this.imageFactory,
              urlApi: this.urlApi,
              signal: previewController.signal,
              onObjectUrl: (objectUrl) => this.registerPreviewObjectUrl(previewResource, objectUrl),
            })),
          ),
          {
            controller: previewController,
            timeoutMs: this.loadingDeadlineMs,
            timeoutError: new Error("promo_media_timeout"),
          },
        );
      } catch (error) {
        previewController.abort();
        throw error;
      } finally {
        this.endPendingOperation(previewController);
      }
      if (generation !== this.generation) {
        this.releasePreviewResource(previewResource);
        return { stale: true, attemptId };
      }

      const { card, qr } = createPromoCard(this.document, images, normalized.qr_url);
      applySavedPromoLayout(card);
      if (replay && Date.parse(normalized.qr_first_open_expires_at) <= Date.now()) {
        const notice = this.document.createElement("p");
        notice.className = "promo-replay-notice";
        notice.textContent = "Срок действия QR истёк. Для нового QR запустите поиск.";
        card.append(notice);
      }
      if (!replay) this.onPrepared({ attemptId, card });
      this.container.replaceChildren(card);
      this.renderedCard = card;
      this.isVisible = true;
      const bounds = qr.svg.getBoundingClientRect?.();
      if (bounds && (bounds.width <= 0 || bounds.height <= 0)) {
        throw new Error("promo_qr_not_visible");
      }
      if (configuration !== null) {
        this.scheduleDisplayExpiry(attemptId, promoDurationMs(configuration.result_display_ms), replay);
      }
      const qrFullyVisibleElapsedMs = replay ? null : this.qrFullyVisibleElapsedMs(timing);
      let acknowledgement = { sent: false, reason: "timing_unavailable" };
      if (qrFullyVisibleElapsedMs !== null) {
        try {
          await this.reportDisplay({
            sessionId: normalized.session_id,
            status: "confirmed",
            qrFullyVisibleElapsedMs,
          });
          if (generation !== this.generation) {
            this.releasePreviewResource(previewResource);
            return { stale: true, attemptId };
          }
          acknowledgement = { sent: true, status: 200 };
        } catch (error) {
          if (generation !== this.generation) {
            this.releasePreviewResource(previewResource);
            return { stale: true, attemptId };
          }
          acknowledgement = { sent: false, reason: "acknowledgement_failed" };
          const detail = Object.freeze({
            handled: true,
            stale: false,
            attemptId,
            state: "advertising",
            retryEligible: true,
            reason: "acknowledgement_failure",
            errorCode: "promo_display_acknowledgement_failed",
            httpStatus: Number.isInteger(error?.httpStatus) ? error.httpStatus : undefined,
            teaserCount: images.length,
            qrFullyVisible: true,
            qrFullyVisibleElapsedMs,
            acknowledgement,
          });
          this.isVisible = false;
          this.removeRenderedCard();
          this.releasePreviewResource(previewResource);
          this.onFailure(detail);
          return detail;
        }
      }
      const detail = Object.freeze({
        handled: true,
        stale: false,
        attemptId,
        state: "result",
        teaserCount: images.length,
        qrFullyVisible: true,
        qrFullyVisibleElapsedMs,
        acknowledgement,
        ...(configuration === null
          ? {}
          : {
              resultDisplayMs: promoDurationMs(configuration.result_display_ms),
              successCooldownMs: configuration.success_cooldown_ms,
            }),
        ...(replay ? { replay: true } : {}),
      });
      if (!replay) this.lastResult = { attemptId, result: normalized, displayConfig: configuration ?? undefined };
      this.onComplete(detail);
      return detail;
    } catch (error) {
      if (generation !== this.generation) {
        this.releasePreviewResource(previewResource);
        return { stale: true, attemptId };
      }
      const reason = error?.message === "promo_qr_not_visible"
        ? "render_failure"
        : error?.message === "promo_media_decode_failed"
          ? "media_decode_failure"
            : error?.message === "promo_media_fetch_failed"
              ? "media_failure"
            : error?.message === "promo_media_timeout"
              ? "media_failure"
            : error?.message?.startsWith("promo_display_configuration")
              ? "configuration_failure"
            : "invalid_result";
      let acknowledgement = { sent: false, reason: "not_server_result" };
      if (normalized && !replay) {
        try {
          await this.reportDisplay({
            sessionId: normalized.session_id,
            status: "failed",
          });
          if (generation !== this.generation) {
            this.releasePreviewResource(previewResource);
            return { stale: true, attemptId };
          }
          acknowledgement = { sent: true, status: 200 };
        } catch {
          if (generation !== this.generation) {
            this.releasePreviewResource(previewResource);
            return { stale: true, attemptId };
          }
          acknowledgement = { sent: false, reason: "acknowledgement_failed" };
        }
      }
      const detail = Object.freeze({
        handled: true,
        stale: false,
        attemptId,
        state: "advertising",
        retryEligible: true,
        reason,
        errorCode: typeof error?.message === "string" && /^(promo|qr)_[a-z_]{1,80}$/.test(error.message)
          ? error.message : "unexpected_render_error",
        acknowledgement,
        ...(replay ? { replay: true } : {}),
      });
      this.isVisible = false;
      this.isReplaying = false;
      this.removeRenderedCard();
      this.releasePreviewResource(previewResource);
      this.onFailure(detail);
      return detail;
    }
  }
}

export function createPromoDisplayController(options) {
  return new PromoDisplayController(options);
}

/** Shared presentation for issued results and the local layout editor. */
export function createPromoCard(documentImpl, images, qrUrl) {
  const card = documentImpl.createElement("section");
  card.className = "view-card promo-card";
  card.dataset.view = "result";
  const heading = documentImpl.createElement("h2");
  heading.textContent = PROMO_COPY;
  const copyPanel = documentImpl.createElement("div");
  copyPanel.className = "promo-copy";
  heading.textContent = "";
  for (const [className, text] of [
    ["promo-title", "Ваши фото можно скачать"],
    ["promo-instruction", " по QR коду или на сайте "],
    ["promo-domain", "face-momet.ru"],
  ]) {
    const span = documentImpl.createElement("span");
    span.className = className;
    span.textContent = text;
    heading.append(span);
  }
  copyPanel.append(heading);
  const teaserGrid = documentImpl.createElement("div");
  teaserGrid.className = "promo-teaser-grid";
  images.forEach((image) => {
    const photoCard = documentImpl.createElement("figure");
    photoCard.className = "promo-photo-card";
    photoCard.append(image);
    teaserGrid.append(photoCard);
  });
  card.append(teaserGrid);
  const qrPanel = documentImpl.createElement("div");
  qrPanel.className = "promo-qr-panel";
  const qr = createQrSvg(documentImpl, qrUrl);
  qr.svg.classList.add("promo-qr");
  qrPanel.append(qr.svg);
  const qrSlot = documentImpl.createElement("div");
  qrSlot.className = "promo-qr-slot";
  qrSlot.append(qrPanel);
  copyPanel.append(qrSlot);
  card.append(copyPanel);
  return { card, qr };
}

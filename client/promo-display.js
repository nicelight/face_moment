import { getDisplayRequestHeaders } from "./display-client-config.js";

const PROMO_COPY = "Ваши фотографии найдены — откройте по QR-коду";
const MEDIA_PATH_PREFIX = "/api/promo/media/";
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
  if (qrUrl.pathname !== "/q" || !qrUrl.searchParams.has("ticket")) {
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

async function loadPreview({ teaser, fetchImpl, imageFactory, urlApi }) {
  const response = await fetchImpl(teaser.media_url, {
    headers: { ...getDisplayRequestHeaders(), "Cache-Control": "no-cache" },
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response?.ok) throw new Error("promo_media_fetch_failed");
  const blob = await response.blob();
  const image = imageFactory();
  image.alt = `Найденная фотография ${teaser.photo_id}`;
  image.className = "promo-teaser";
  image.src = urlApi.createObjectURL(blob);
  if (typeof image.decode === "function") await image.decode();
  else await new Promise((resolve, reject) => {
    image.addEventListener("load", resolve, { once: true });
    image.addEventListener("error", () => reject(new Error("promo_media_decode_failed")), { once: true });
  });
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
    onFailure = () => {},
    origin = defaultOrigin(),
  } = {}) {
    if (!container || typeof container.replaceChildren !== "function") {
      throw new TypeError("promo_container_missing");
    }
    if (typeof fetchImpl !== "function") throw new TypeError("promo_fetch_missing");
    if (!documentImpl) throw new TypeError("promo_document_missing");
    this.container = container;
    this.fetchImpl = fetchImpl;
    this.document = documentImpl;
    this.imageFactory = imageFactory;
    this.urlApi = urlApi;
    this.onComplete = onComplete;
    this.onFailure = onFailure;
    this.origin = origin;
    this.generation = 0;
    this.isVisible = false;
  }

  async showResult({ attemptId, result }) {
    const generation = ++this.generation;
    this.isVisible = false;
    let normalized;
    try {
      normalized = validatePromoResult(result, { origin: this.origin });
      const images = await Promise.all(
        normalized.teasers.map((teaser) => loadPreview({
          teaser,
          fetchImpl: this.fetchImpl,
          imageFactory: this.imageFactory,
          urlApi: this.urlApi,
        })),
      );
      if (generation !== this.generation) return { stale: true, attemptId };

      const card = this.document.createElement("section");
      card.className = "view-card promo-card";
      card.dataset.view = "result";
      const heading = this.document.createElement("h2");
      heading.textContent = PROMO_COPY;
      card.append(heading);
      const teaserGrid = this.document.createElement("div");
      teaserGrid.className = "promo-teaser-grid";
      images.forEach((image) => teaserGrid.append(image));
      card.append(teaserGrid);
      const qrPanel = this.document.createElement("div");
      qrPanel.className = "promo-qr-panel";
      const qr = createQrSvg(this.document, normalized.qr_url);
      qr.svg.classList.add("promo-qr");
      qrPanel.append(qr.svg);
      card.append(qrPanel);
      this.container.replaceChildren(card);
      this.isVisible = true;
      const bounds = qr.svg.getBoundingClientRect?.();
      if (bounds && (bounds.width <= 0 || bounds.height <= 0)) {
        throw new Error("promo_qr_not_visible");
      }
      const detail = Object.freeze({
        handled: true,
        stale: false,
        attemptId,
        state: "result",
        teaserCount: images.length,
        qrFullyVisible: true,
      });
      this.onComplete(detail);
      return detail;
    } catch (error) {
      if (generation !== this.generation) return { stale: true, attemptId };
      const reason = error?.message === "promo_qr_not_visible"
        ? "render_failure"
        : error?.message === "promo_media_decode_failed"
          ? "media_decode_failure"
          : error?.message === "promo_media_fetch_failed"
            ? "media_failure"
            : "invalid_result";
      const detail = Object.freeze({
        handled: true,
        stale: false,
        attemptId,
        state: "advertising",
        retryEligible: true,
        reason,
      });
      this.isVisible = false;
      this.onFailure(detail);
      return detail;
    }
  }
}

export function createPromoDisplayController(options) {
  return new PromoDisplayController(options);
}

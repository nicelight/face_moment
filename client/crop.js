const OCCURRENCE_CROP_SCALE = 1.2;
const MAX_OCCURRENCE_CROP_SIDE = 512;

export { MAX_OCCURRENCE_CROP_SIDE, OCCURRENCE_CROP_SCALE };

function requireFinitePositive(value, name) {
  if (!Number.isFinite(value) || value <= 0) {
    throw new TypeError(`${name} must be a finite positive number`);
  }
  return value;
}

function requireFinite(value, name) {
  if (!Number.isFinite(value)) {
    throw new TypeError(`${name} must be a finite number`);
  }
  return value;
}

function sourceDimension(source, names, name) {
  for (const candidate of names) {
    if (Number.isFinite(source?.[candidate]) && source[candidate] > 0) {
      return source[candidate];
    }
  }
  throw new TypeError(`${name} must expose a finite positive image dimension`);
}

export function getSourceDimensions(source) {
  return {
    width: sourceDimension(
      source,
      ["naturalWidth", "videoWidth", "displayWidth", "width"],
      "source width",
    ),
    height: sourceDimension(
      source,
      ["naturalHeight", "videoHeight", "displayHeight", "height"],
      "source height",
    ),
  };
}

/**
 * Resolve the source-frame window for one detector occurrence.
 *
 * The requested window stays centered on the detector bbox. At an image edge
 * only the source rectangle is clipped; it is not shifted, padded, aligned or
 * enlarged. Destination dimensions are reduced proportionally only when the
 * clipped source window itself is larger than the accepted 512px bound.
 */
export function computeOccurrenceCropGeometry({
  sourceWidth,
  sourceHeight,
  boundingBox,
}) {
  requireFinitePositive(sourceWidth, "sourceWidth");
  requireFinitePositive(sourceHeight, "sourceHeight");

  const originX = requireFinite(boundingBox?.originX, "boundingBox.originX");
  const originY = requireFinite(boundingBox?.originY, "boundingBox.originY");
  const bboxWidth = requireFinitePositive(
    boundingBox?.width,
    "boundingBox.width",
  );
  const bboxHeight = requireFinitePositive(
    boundingBox?.height,
    "boundingBox.height",
  );

  const requestedSide = OCCURRENCE_CROP_SCALE * Math.max(bboxWidth, bboxHeight);
  const centerX = originX + bboxWidth / 2;
  const centerY = originY + bboxHeight / 2;
  const requestedLeft = centerX - requestedSide / 2;
  const requestedTop = centerY - requestedSide / 2;
  const requestedRight = requestedLeft + requestedSide;
  const requestedBottom = requestedTop + requestedSide;

  const sourceLeft = Math.max(0, requestedLeft);
  const sourceTop = Math.max(0, requestedTop);
  const sourceRight = Math.min(sourceWidth, requestedRight);
  const sourceBottom = Math.min(sourceHeight, requestedBottom);
  const clippedWidth = sourceRight - sourceLeft;
  const clippedHeight = sourceBottom - sourceTop;

  if (clippedWidth <= 0 || clippedHeight <= 0) {
    throw new RangeError("boundingBox does not intersect source frame");
  }

  const clippedLongSide = Math.max(clippedWidth, clippedHeight);
  const scale = Math.min(1, MAX_OCCURRENCE_CROP_SIDE / clippedLongSide);
  const destinationWidth = Math.max(1, Math.round(clippedWidth * scale));
  const destinationHeight = Math.max(1, Math.round(clippedHeight * scale));

  return {
    requestedSide,
    requestedLeft,
    requestedTop,
    sourceX: sourceLeft,
    sourceY: sourceTop,
    sourceWidth: clippedWidth,
    sourceHeight: clippedHeight,
    scale,
    destinationWidth,
    destinationHeight,
  };
}

function createCanvas(width, height, canvasFactory) {
  const canvas = canvasFactory?.(width, height);
  if (canvas) return canvas;

  if (typeof document !== "undefined") {
    const htmlCanvas = document.createElement("canvas");
    htmlCanvas.width = width;
    htmlCanvas.height = height;
    return htmlCanvas;
  }

  if (typeof OffscreenCanvas !== "undefined") {
    return new OffscreenCanvas(width, height);
  }

  throw new Error("browser_canvas_unavailable");
}

export function cropOccurrenceToCanvas(
  source,
  boundingBox,
  { canvasFactory } = {},
) {
  const { width: sourceWidth, height: sourceHeight } =
    getSourceDimensions(source);
  const geometry = computeOccurrenceCropGeometry({
    sourceWidth,
    sourceHeight,
    boundingBox,
  });
  const canvas = createCanvas(
    geometry.destinationWidth,
    geometry.destinationHeight,
    canvasFactory,
  );

  canvas.width = geometry.destinationWidth;
  canvas.height = geometry.destinationHeight;
  const context = canvas.getContext("2d", {
    alpha: false,
    colorSpace: "srgb",
  });
  if (!context) throw new Error("browser_2d_canvas_unavailable");

  context.drawImage(
    source,
    geometry.sourceX,
    geometry.sourceY,
    geometry.sourceWidth,
    geometry.sourceHeight,
    0,
    0,
    geometry.destinationWidth,
    geometry.destinationHeight,
  );

  return { canvas, geometry };
}

function canvasToJpeg(canvas, quality) {
  if (typeof canvas.toBlob === "function") {
    return new Promise((resolve, reject) => {
      const callback = (blob) => {
        if (!blob) {
          reject(new Error("jpeg_encoding_failed"));
          return;
        }
        resolve(blob);
      };
      if (quality === undefined) {
        canvas.toBlob(callback, "image/jpeg");
      } else {
        canvas.toBlob(callback, "image/jpeg", quality);
      }
    });
  }

  if (typeof canvas.convertToBlob === "function") {
    const options = { type: "image/jpeg" };
    if (quality !== undefined) options.quality = quality;
    return canvas.convertToBlob(options);
  }

  throw new Error("browser_jpeg_encoding_unavailable");
}

/**
 * Crop one occurrence and encode only the clipped source pixels as JPEG.
 * `quality` is caller-supplied; quality selection and persistence belong to
 * the separate client configuration task.
 */
export async function cropAndEncodeOccurrence(
  source,
  boundingBox,
  { quality, canvasFactory } = {},
) {
  const { canvas, geometry } = cropOccurrenceToCanvas(source, boundingBox, {
    canvasFactory,
  });
  const blob = await canvasToJpeg(canvas, quality);

  return {
    blob,
    contentType: "image/jpeg",
    width: canvas.width,
    height: canvas.height,
    geometry,
  };
}

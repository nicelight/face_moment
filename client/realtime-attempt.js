import { cropAndEncodeOccurrence } from "./crop.js";
import { normalizeJpegQuality } from "./jpeg-quality.js";

export const REALTIME_ATTEMPT_PATH = "/api/realtime/attempts";
export const REALTIME_DETECTOR_ID = "mediapipe_blazeface_full_range";
export const REALTIME_MODEL_VERSION = "blazeface-full-range-1";
export const DEFAULT_CLIENT_RELEASE = "face-moment-client";
export const MAX_REALTIME_OCCURRENCES = 20;

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MANIFEST_CONTENT_TYPE = "application/json; charset=utf-8";

function requireString(value, name) {
  const normalized = String(value ?? "");
  if (!normalized || normalized.length > 255) {
    throw new TypeError(`${name}_must_be_non_empty`);
  }
  return normalized;
}

function requireInteger(value, name) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new TypeError(`${name}_must_be_non_negative_integer`);
  }
  return value;
}

function normalizeReadyAt(value) {
  const normalized = requireString(value, "reference_series_ready_at");
  if (!normalized.includes("T") || !/[zZ]|[+-]\d{2}:?\d{2}$/.test(normalized)) {
    throw new TypeError("reference_series_ready_at_must_be_rfc3339");
  }
  if (!Number.isFinite(Date.parse(normalized))) {
    throw new TypeError("reference_series_ready_at_must_be_rfc3339");
  }
  return normalized;
}

function normalizeTriggerSource(value) {
  const source = requireString(value, "trigger_source");
  if (source === "physical") return "sensor";
  if (source === "sensor" || source === "test") return source;
  throw new TypeError("trigger_source_invalid");
}

function randomUuid() {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  throw new Error("crypto_random_uuid_unavailable");
}

function normalizeAttemptId(value, uuidFactory) {
  const candidate = String(value ?? "");
  const attemptId = UUID_PATTERN.test(candidate) ? candidate : uuidFactory();
  if (!UUID_PATTERN.test(attemptId)) {
    throw new TypeError("attempt_id_must_be_uuid");
  }
  return attemptId;
}

function frameSource(frame) {
  return frame?.image ?? frame?.frame ?? frame;
}

function detectorConfidence(proposal) {
  const candidate = proposal?.detectorConfidence ?? proposal?.categories?.[0]?.score;
  if (
    typeof candidate !== "number" ||
    !Number.isFinite(candidate) ||
    candidate < 0 ||
    candidate > 1
  ) {
    throw new TypeError("detector_confidence_invalid");
  }
  return candidate;
}

function frameOffsetMs(proposal, frameIndex, frameTimestampsMs) {
  if (Number.isSafeInteger(proposal?.frameOffsetMs) && proposal.frameOffsetMs >= 0) {
    return proposal.frameOffsetMs;
  }
  const firstTimestamp = frameTimestampsMs?.[0];
  const timestamp = frameTimestampsMs?.[frameIndex];
  if (
    !Number.isFinite(firstTimestamp) ||
    !Number.isFinite(timestamp) ||
    timestamp < firstTimestamp
  ) {
    throw new TypeError("frame_offset_ms_unavailable");
  }
  return Math.round(timestamp - firstTimestamp);
}

function formDataFactory() {
  if (typeof globalThis.FormData !== "function") {
    throw new Error("form_data_unavailable");
  }
  return new globalThis.FormData();
}

function blobFactory(parts, options) {
  if (typeof globalThis.Blob !== "function") {
    throw new Error("blob_unavailable");
  }
  return new globalThis.Blob(parts, options);
}

/**
 * Form one exact v1 multipart request. Timing values and crop encoding are
 * caller-supplied seams; marker collection and server admission live in
 * their owning tasks.
 */
export async function buildRealtimeAttemptRequest({
  attemptId,
  triggerSource,
  clientRelease = DEFAULT_CLIENT_RELEASE,
  modelVersion = REALTIME_MODEL_VERSION,
  jpegQuality,
  cameraDeviceId,
  clientToken,
  timing,
  frames = [],
  frameTimestampsMs = [],
  proposals = [],
  cropEncoder = cropAndEncodeOccurrence,
  uuidFactory = randomUuid,
  makeFormData = formDataFactory,
  makeBlob = blobFactory,
} = {}) {
  const token = requireString(clientToken, "client_token");
  const normalizedTiming = {
    reference_series_ready_at: normalizeReadyAt(timing?.referenceSeriesReadyAt),
    local_detection_completed_ms: requireInteger(
      timing?.localDetectionCompletedMs,
      "local_detection_completed_ms",
    ),
    request_started_ms: requireInteger(
      timing?.requestStartedMs,
      "request_started_ms",
    ),
  };
  if (
    normalizedTiming.local_detection_completed_ms >
    normalizedTiming.request_started_ms
  ) {
    throw new TypeError("client_monotonic_markers_out_of_order");
  }

  const normalizedProposals = Array.from(proposals);
  if (normalizedProposals.length > MAX_REALTIME_OCCURRENCES) {
    throw new RangeError("realtime_occurrences_exceed_limit");
  }
  const quality = normalizeJpegQuality(jpegQuality);
  const manifestOccurrences = [];
  const encodedCrops = [];

  for (
    let occurrenceIndex = 0;
    occurrenceIndex < normalizedProposals.length;
    occurrenceIndex += 1
  ) {
    const proposal = normalizedProposals[occurrenceIndex];
    const frameIndex = requireInteger(proposal?.frameIndex, "frame_index");
    const cropPart = `crop_${String(occurrenceIndex).padStart(3, "0")}`;
    const source = frameSource(frames[frameIndex]);
    if (!source) throw new TypeError("occurrence_frame_missing");

    const encoded = await cropEncoder(source, proposal.boundingBox, {
      quality,
    });
    const blob = encoded?.blob ?? encoded;
    if (!blob || typeof blob.arrayBuffer !== "function") {
      throw new TypeError("occurrence_jpeg_blob_invalid");
    }

    manifestOccurrences.push({
      occurrence_index: occurrenceIndex,
      frame_index: frameIndex,
      frame_offset_ms: frameOffsetMs(
        proposal,
        frameIndex,
        frameTimestampsMs,
      ),
      detector_confidence: detectorConfidence(proposal),
      crop_part: cropPart,
    });
    encodedCrops.push({ cropPart, blob });
  }

  const manifest = {
    schema_version: 1,
    attempt_id: normalizeAttemptId(attemptId, uuidFactory),
    trigger_source: normalizeTriggerSource(triggerSource),
    client_release: requireString(clientRelease, "client_release"),
    detector_id: REALTIME_DETECTOR_ID,
    model_version: requireString(modelVersion, "model_version"),
    jpeg_quality: quality,
    camera_device_id: requireString(cameraDeviceId, "camera_device_id"),
    timing: normalizedTiming,
    occurrences: manifestOccurrences,
  };

  const body = makeFormData();
  body.append(
    "manifest",
    makeBlob([JSON.stringify(manifest)], { type: MANIFEST_CONTENT_TYPE }),
  );
  for (const { cropPart, blob } of encodedCrops) {
    body.append(cropPart, blob, `${cropPart}.jpg`);
  }

  return {
    body,
    headers: { Authorization: `Bearer ${token}` },
    manifest,
  };
}

/**
 * Submit one already-formed request and return the raw response for the
 * later outcome-owning task. No response branching or retry is performed.
 */
export async function submitRealtimeAttempt({
  fetchImpl = globalThis.fetch,
  path = REALTIME_ATTEMPT_PATH,
  ...options
} = {}) {
  if (typeof fetchImpl !== "function") throw new Error("fetch_unavailable");
  const request = await buildRealtimeAttemptRequest(options);
  const response = await fetchImpl(path, {
    method: "POST",
    headers: request.headers,
    body: request.body,
  });
  return { response, manifest: request.manifest };
}

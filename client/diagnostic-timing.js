export const CLIENT_TIMING_SCHEMA_VERSION = 1;

function requireString(value, name) {
  if (typeof value !== "string" || value.length === 0) {
    throw new TypeError(`${name}_must_be_non_empty`);
  }
  return value;
}

function requireElapsedMs(value) {
  if (
    !Number.isInteger(value) ||
    value < 0 ||
    value > 2_147_483_647
  ) {
    throw new TypeError("response_received_ms_must_be_non_negative_integer");
  }
  return value;
}

export async function reportClientResponseTiming({
  attemptId,
  responseReceivedMs,
  clientToken,
  fetchImpl = globalThis.fetch,
} = {}) {
  if (typeof fetchImpl !== "function") throw new Error("fetch_unavailable");
  const normalizedAttemptId = requireString(attemptId, "attempt_id");
  const token = requireString(clientToken, "client_token");
  const marker = requireElapsedMs(responseReceivedMs);
  return fetchImpl(
    `/api/realtime/attempts/${encodeURIComponent(normalizedAttemptId)}/client-timing`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        schema_version: CLIENT_TIMING_SCHEMA_VERSION,
        response_received_ms: marker,
      }),
    },
  );
}

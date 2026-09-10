/** Bounded, safe diagnostic metadata retained across reloads in one tab. */
const STORAGE_KEY = "face-moment.client-diagnostic-history";

function safeEvent(value) {
  if (!value || typeof value.time !== "string" ||
      !Number.isFinite(Date.parse(value.time)) ||
      typeof value.stage !== "string" || value.stage.length > 100) return null;
  const event = { time: new Date(value.time).toISOString(), stage: value.stage };
  for (const key of ["attemptId", "outcome", "reason", "errorCode"]) {
    if (typeof value[key] === "string" && /^[a-zA-Z0-9_-]{1,100}$/.test(value[key])) {
      event[key] = value[key];
    }
  }
  if (typeof value.displayReportSent === "boolean") event.displayReportSent = value.displayReportSent;
  if (Number.isInteger(value.httpStatus)) event.httpStatus = value.httpStatus;
  return event;
}

export function readClientDiagnosticEvents(storage) {
  try {
    const raw = (storage ?? globalThis.sessionStorage).getItem(STORAGE_KEY);
    if (!raw || raw.length > 64_000) return [];
    const values = JSON.parse(raw);
    return Array.isArray(values) ? values.slice(-20).map(safeEvent).filter(Boolean) : [];
  } catch {
    return [];
  }
}

export function saveClientDiagnosticEvents(events, storage) {
  try {
    (storage ?? globalThis.sessionStorage).setItem(
      STORAGE_KEY, JSON.stringify(events.slice(-20).map(safeEvent).filter(Boolean)),
    );
  } catch {
    // Denied/full storage must not interrupt capture or result presentation.
  }
}

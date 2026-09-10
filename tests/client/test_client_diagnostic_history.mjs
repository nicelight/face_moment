import assert from "node:assert/strict";
import { readClientDiagnosticEvents, saveClientDiagnosticEvents } from "../../client/client-diagnostic-history.js";

let value = null;
const storage = { getItem: () => value, setItem: (_, data) => { value = data; } };
const events = Array.from({ length: 25 }, (_, i) => ({
  time: new Date(1000 * i).toISOString(), stage: "Ответ сервера",
  attemptId: `attempt-${i}`, reason: "http_failure", httpStatus: 401,
  token: "must-not-persist", image: "must-not-persist",
}));
saveClientDiagnosticEvents(events, storage);
const restored = readClientDiagnosticEvents(storage);
assert.equal(restored.length, 20);
assert.equal(restored[0].attemptId, "attempt-5");
assert.equal(restored[19].httpStatus, 401);
assert.equal(value.includes("must-not-persist"), false);
value = "broken JSON";
assert.deepEqual(readClientDiagnosticEvents(storage), []);
const denied = { getItem() { throw Error("denied"); }, setItem() { throw Error("denied"); } };
assert.deepEqual(readClientDiagnosticEvents(denied), []);
assert.doesNotThrow(() => saveClientDiagnosticEvents(events, denied));
console.log("diagnostic history: reload, bounded metadata, malformed and denied storage passed");

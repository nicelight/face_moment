import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const app = await readFile("client/app.js", "utf8");

assert.match(
  app,
  /import \{ submitRealtimeAttempt \} from "\.\/realtime-attempt\.js";/,
);
assert.match(app, /async function submitReadyReferenceSeries\(/);
assert.match(app, /submitRealtimeAttempt\(\{/);
assert.match(app, /new CustomEvent\("face-moment:attempt-request-start"/);
assert.match(app, /new CustomEvent\("face-moment:attempt-response"/);
assert.match(app, /new CustomEvent\("face-moment:attempt-transport-failure"/);
assert.match(app, /void submitReadyReferenceSeries\(event\.detail, proposals\)/);

const readyHandler = app.slice(app.indexOf('"face-moment:reference-series-ready"'));
assert.ok(
  readyHandler.indexOf("detectReferenceSeries") <
    readyHandler.indexOf("submitReadyReferenceSeries"),
  "the real ready-series path must detect before submitting",
);

const requestStart = app.indexOf('"face-moment:attempt-request-start"');
const submitCall = app.indexOf("submitRealtimeAttempt({");
const responseDispatch = app.indexOf('"face-moment:attempt-response"', submitCall);
const transportDispatch = app.indexOf(
  '"face-moment:attempt-transport-failure"',
  submitCall,
);
assert.ok(requestStart < submitCall, "request-start must precede request submission");
assert.ok(submitCall < responseDispatch, "response must be emitted after submission");
assert.ok(submitCall < transportDispatch, "transport failure must be emitted by the same path");
assert.doesNotMatch(app, /window\.dispatchEvent\(new CustomEvent\("face-moment:attempt-response"/s);

console.log(
  "production wiring GREEN: ready series calls the real realtime boundary and routes its response/transport completion into the outcome controller seam",
);

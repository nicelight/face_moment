import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const app = await readFile("client/app.js", "utf8");

assert.match(
  app,
  /import \{\s*createBlazeFaceDetector,\s*detectReferenceSeries,\s*\} from "\.\/blazeface\.js";/,
);
assert.match(
  app,
  /import \{ submitRealtimeAttempt \} from "\.\/realtime-attempt\.js";/,
);
assert.match(
  app,
  /import \{ createAttemptTimingRecorder \} from "\.\/attempt-timing\.js";/,
);
assert.match(app, /async function submitReadyReferenceSeries\(/);
assert.match(app, /createAttemptTimingRecorder\(\{/);
assert.match(app, /timing: timingRecorder\.manifestTiming\(\)/);
assert.match(app, /timingRecorder\.recordResponseReceived\(\)/);
assert.match(app, /timing: timingRecorder\.snapshot\(\)/);
assert.match(app, /submitRealtimeAttempt\(\{/);
assert.match(app, /new CustomEvent\("face-moment:attempt-request-start"/);
assert.match(app, /new CustomEvent\("face-moment:attempt-response"/);
assert.match(app, /new CustomEvent\("face-moment:attempt-transport-failure"/);
assert.match(app, /void submitReadyReferenceSeries\(event\.detail, proposals\)/);
assert.match(app, /async function createAndWarmBlazeFaceDetector\(\)/);
assert.match(app, /warmupImage\.width = 64;/);
assert.match(app, /warmupImage\.height = 64;/);
assert.match(app, /await detector\.detect\(warmupImage\);/);

const warmupStart = app.indexOf(
  "void getBlazeFaceDetector().catch(renderDetectorFailure);",
);
const readyListener = app.indexOf('"face-moment:reference-series-ready"');
assert.ok(
  warmupStart >= 0 && warmupStart < readyListener,
  "detector warm-up must start on page startup",
);

const readyHandler = app.slice(app.indexOf('"face-moment:reference-series-ready"'));
assert.ok(
  readyHandler.indexOf("getBlazeFaceDetector") <
    readyHandler.indexOf("detectReferenceSeries"),
  "the real ready-series path must reuse the startup detector",
);
assert.ok(
  readyHandler.indexOf("detectReferenceSeries") <
    readyHandler.indexOf("submitReadyReferenceSeries"),
  "the real ready-series path must detect before submitting",
);
assert.match(
  readyHandler,
  /detectReferenceSeries\(event\.detail\?\.frames, \{\s*detector,\s*\}\)/,
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
assert.doesNotMatch(app, /function monotonicNowMs\(/);
assert.doesNotMatch(app, /function referenceSeriesReadyAt\(/);

console.log(
  "production wiring GREEN: ready series calls the real realtime boundary and routes its response/transport completion into the outcome controller seam",
);

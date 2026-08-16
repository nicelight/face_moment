import assert from "node:assert/strict";
import { SensorPassageClient, decodePassageEvent } from "../../client/sensor.js";

const EVENT = {
  schema_version: 1,
  sensor_id: "fm-sensor1",
  boot_id: "48cf0a18-2c87-46b6-bb26-c46e81606535",
  sequence: 17,
  type: "passage",
};

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
const response = (status, body) => ({
  status,
  json: async () => body,
});

async function provesOneOutstandingPollAndImmediate204Renewal() {
  let active = 0;
  let maximumActive = 0;
  let calls = 0;
  let release;
  const urls = [];
  const fetchImpl = (url, options) => {
    calls += 1;
    active += 1;
    maximumActive = Math.max(maximumActive, active);
    urls.push(url);
    assert.equal(options.method, "GET");
    assert.equal(options.headers.Authorization, "Bearer fixture-secret");
    assert.equal(options.mode, "cors");
    return new Promise((resolve) => {
      release = (result) => {
        active -= 1;
        resolve(result);
      };
    });
  };
  const client = new SensorPassageClient({
    host: "http://fm-sensor1.local",
    sensorId: "fm-sensor1",
    secret: "fixture-secret",
    fetchImpl,
    pollTimeoutMs: 60_000,
    retryDelayMs: 60_000,
  });

  client.start();
  await tick();
  assert.equal(calls, 1);
  assert.equal(active, 1);
  release(response(204));
  await tick();
  assert.equal(calls, 2);
  assert.equal(active, 1);
  assert.equal(maximumActive, 1);
  assert.deepEqual(urls, [
    "http://fm-sensor1.local/api/v1/passage-events/next",
    "http://fm-sensor1.local/api/v1/passage-events/next",
  ]);
  client.stop();
  release(response(204));
  await tick();
  assert.equal(active, 0);
}

async function provesStrictDecodeAndInMemoryDuplicateSuppression() {
  const events = [];
  const statuses = [];
  let calls = 0;
  const fetchImpl = async (url, options) => {
    calls += 1;
    assert.equal(url, "http://fm-sensor1.local/api/v1/passage-events/next");
    assert.equal(options.headers.Authorization, "Bearer fixture-secret");
    return calls === 1 || calls === 2 ? response(200, EVENT) : response(204);
  };
  let client;
  client = new SensorPassageClient({
    host: "http://fm-sensor1.local",
    sensorId: "fm-sensor1",
    secret: "fixture-secret",
    fetchImpl,
    retryDelayMs: 60_000,
    onEvent: (event) => events.push(event),
    onStatus: (status) => {
      statuses.push(status);
      if (status === "advertising" && calls === 3) client.stop();
    },
  });

  client.start();
  await tick();
  await tick();
  assert.equal(calls, 3);
  assert.deepEqual(events, [EVENT]);
  assert.ok(statuses.includes("passage"));
  assert.ok(statuses.includes("advertising"));
  assert.equal(decodePassageEvent(EVENT, "fm-sensor1").sequence, 17);
  assert.throws(
    () => decodePassageEvent({ ...EVENT, unexpected: true }, "fm-sensor1"),
    /passage_event_shape_invalid/,
  );
}

await provesOneOutstandingPollAndImmediate204Renewal();
await provesStrictDecodeAndInMemoryDuplicateSuppression();
console.log("sensor poller GREEN: one outstanding request, 204 renewal, strict decode, duplicate suppression");

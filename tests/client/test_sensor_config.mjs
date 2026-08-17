import assert from "node:assert/strict";
import {
  normalizeSensorConfig,
  readSensorConfig,
  saveSensorConfig,
  SENSOR_CONFIG_STORAGE_KEY,
} from "../../client/sensor-config.js";

function makeStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
}

const storage = makeStorage();
const saved = saveSensorConfig(
  {
    host: "http://fm-sensor1.local/",
    sensorId: "fm-sensor1",
    secret: "fixture-secret-never-in-url",
  },
  storage,
);

assert.deepEqual(saved, {
  host: "http://fm-sensor1.local",
  sensorId: "fm-sensor1",
  secret: "fixture-secret-never-in-url",
});
assert.deepEqual(readSensorConfig(storage), saved);
assert.ok(storage.getItem(SENSOR_CONFIG_STORAGE_KEY));
assert.throws(
  () => normalizeSensorConfig({ host: "http://fm-sensor1.local/path", sensorId: "fm-sensor1", secret: "secret" }),
  /sensor_host_path_invalid/,
);
assert.throws(
  () => normalizeSensorConfig({ host: "http://fm-sensor1.local", sensorId: "fm-sensor1", secret: "line\nfeed" }),
  /sensor_secret_invalid/,
);

console.log("sensor config GREEN: localStorage persistence and fixed-host validation");

import { normalizeSensorHost } from "./sensor.js";

export const SENSOR_CONFIG_STORAGE_KEY = "face-moment.sensor-config";

function browserStorage(storage) {
  if (storage !== undefined) return storage;
  try {
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

export function normalizeSensorConfig({ host, sensorId, secret } = {}) {
  const normalizedHost = normalizeSensorHost(host);
  const normalizedSensorId = String(sensorId ?? "").trim();
  const normalizedSecret = String(secret ?? "").trim();

  if (!normalizedSensorId) throw new Error("sensor_id_missing");
  if (!normalizedSecret) throw new Error("sensor_secret_missing");
  if (/\r|\n/.test(normalizedSecret)) {
    throw new Error("sensor_secret_invalid");
  }

  return Object.freeze({
    host: normalizedHost,
    sensorId: normalizedSensorId,
    secret: normalizedSecret,
  });
}

export function readSensorConfig(storage) {
  const target = browserStorage(storage);
  try {
    const raw = target?.getItem(SENSOR_CONFIG_STORAGE_KEY);
    if (!raw) return null;
    return normalizeSensorConfig(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function saveSensorConfig(config, storage) {
  const target = browserStorage(storage);
  if (!target) throw new Error("sensor_config_storage_unavailable");
  const normalized = normalizeSensorConfig(config);
  try {
    target.setItem(SENSOR_CONFIG_STORAGE_KEY, JSON.stringify(normalized));
  } catch (error) {
    throw new Error("sensor_config_persistence_failed", { cause: error });
  }
  return normalized;
}

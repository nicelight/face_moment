import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium, expect, test } = require("playwright/test");

const PROJECT_ROOT = path.resolve(import.meta.dirname, "../..");
const ORIGIN = "https://face-moment-degraded.test";
const SENSOR_CONFIG = JSON.stringify({
  host: "http://sensor-fixture.local",
  sensorId: "sensor-fixture",
  secret: "fixture-sensor-secret",
});
const DETECTOR_ASSETS = [
  "vision_bundle.mjs",
  "vision_wasm_internal.js",
  "vision_wasm_internal.wasm",
  "blaze_face_full_range.tflite",
];

function contentType(filePath) {
  if (filePath.endsWith(".js") || filePath.endsWith(".mjs")) return "text/javascript";
  if (filePath.endsWith(".css")) return "text/css";
  if (filePath.endsWith(".html")) return "text/html";
  if (filePath.endsWith(".json")) return "application/json";
  if (filePath.endsWith(".tflite")) return "application/octet-stream";
  if (filePath.endsWith(".wasm")) return "application/wasm";
  return "application/octet-stream";
}

async function routeClient(context, { failModel = false, requestedPaths }) {
  await context.route(`${ORIGIN}/**`, async (route) => {
    const requestPath = new URL(route.request().url()).pathname;
    requestedPaths.push(requestPath);
    const relativePath = requestPath === "/" ? "client/index.html" : requestPath.slice(1);
    if (!relativePath.startsWith("client/")) {
      await route.fulfill({ status: 404, body: "not found" });
      return;
    }
    if (failModel && relativePath.startsWith("client/models/")) {
      await route.fulfill({ status: 503, body: "model fixture unavailable" });
      return;
    }

    const filePath = path.resolve(PROJECT_ROOT, relativePath);
    if (!filePath.startsWith(path.join(PROJECT_ROOT, "client") + path.sep)) {
      await route.fulfill({ status: 404, body: "not found" });
      return;
    }
    try {
      await route.fulfill({
        status: 200,
        contentType: contentType(filePath),
        body: await readFile(filePath),
      });
    } catch {
      await route.fulfill({ status: 404, body: "not found" });
    }
  });
}

async function launchClient({ failModel = false, sensorUnavailable = false } = {}) {
  const profilePath = await mkdtemp(path.join(tmpdir(), "face-moment-degraded-"));
  const requestedPaths = [];
  const context = await chromium.launchPersistentContext(profilePath, {
    headless: true,
  });
  await routeClient(context, { failModel, requestedPaths });
  const page = context.pages()[0] ?? await context.newPage();
  await page.addInitScript(
    ({ sensorConfig, sensorUnavailable: shouldFailSensor }) => {
      Object.defineProperty(navigator, "mediaDevices", {
        configurable: true,
        value: {
          enumerateDevices: async () => [],
          getUserMedia: async () => {
            throw new DOMException("fixture camera unavailable", "NotFoundError");
          },
        },
      });

      if (sensorConfig) {
        localStorage.setItem("face-moment.sensor-config", sensorConfig);
      }
      if (shouldFailSensor) {
        const browserFetch = globalThis.fetch.bind(globalThis);
        globalThis.fetch = async (input, init) => {
          if (String(input).includes("sensor-fixture.local")) {
            throw new Error("fixture sensor unavailable");
          }
          return browserFetch(input, init);
        };
      }
    },
    { sensorConfig: sensorUnavailable ? SENSOR_CONFIG : null, sensorUnavailable },
  );
  return { context, page, profilePath, requestedPaths };
}

async function closeClient(client) {
  await client.context.close().catch(() => {});
  await rm(client.profilePath, { recursive: true, force: true });
}

test("FT-003-AC-004 BlazeFace is warmed once during page startup", async () => {
  const client = await launchClient();
  try {
    await client.page.goto(`${ORIGIN}/#advertising`);
    await expect
      .poll(() =>
        DETECTOR_ASSETS.every((asset) =>
          client.requestedPaths.some((path) => path.endsWith(asset)),
        ),
      )
      .toBe(true);

    const runEmptySeries = (attemptId) =>
      client.page.evaluate(
        (id) =>
          new Promise((resolve) => {
            window.addEventListener("face-moment:proposals-ready", resolve, {
              once: true,
            });
            window.dispatchEvent(
              new CustomEvent("face-moment:reference-series-ready", {
                detail: { attemptId: id, trigger_source: "test", frames: [] },
              }),
            );
          }),
        attemptId,
      );

    await runEmptySeries("startup-warmup-one");
    const firstAssetRequestCount = client.requestedPaths.filter((path) =>
      DETECTOR_ASSETS.some((asset) => path.endsWith(asset)),
    ).length;

    await runEmptySeries("startup-warmup-two");
    const secondAssetRequestCount = client.requestedPaths.filter((path) =>
      DETECTOR_ASSETS.some((asset) => path.endsWith(asset)),
    ).length;

    expect(secondAssetRequestCount).toBe(firstAssetRequestCount);
    await expect(client.page.locator("body")).toHaveAttribute(
      "data-detector-state",
      "ready",
    );
  } finally {
    await closeClient(client);
  }
});

test("FT-003-AC-008 missing camera keeps the loaded client in advertising", async () => {
  const client = await launchClient();
  try {
    await client.page.goto(`${ORIGIN}/#advertising`);
    await expect(client.page.locator('[data-view="advertising"]')).toBeVisible();

    await client.page.goto(`${ORIGIN}/#configuration`);
    await expect(client.page.locator("#camera-status")).toHaveText("Выберите камеру явно.");
    await client.page.goto(`${ORIGIN}/#advertising`);
    await expect(client.page.locator('[data-view="advertising"]')).toBeVisible();
  } finally {
    await closeClient(client);
  }
});

test("FT-003-AC-008 sensor unavailability keeps advertising and exposes recovery feedback", async () => {
  const client = await launchClient({ sensorUnavailable: true });
  try {
    await client.page.goto(`${ORIGIN}/#advertising`);
    await expect(client.page.locator('[data-view="advertising"]')).toBeVisible();
    await expect(client.page.locator("body")).toHaveAttribute(
      "data-sensor-state",
      "recoverable-error",
    );

    await client.page.goto(`${ORIGIN}/#configuration`);
    await expect(client.page.locator("#sensor-status")).toHaveText(
      "Сенсор временно недоступен. Реклама продолжает работать.",
    );
    await client.page.goto(`${ORIGIN}/#advertising`);
    await expect(client.page.locator('[data-view="advertising"]')).toBeVisible();
  } finally {
    await closeClient(client);
  }
});

test("FT-003-AC-008 BlazeFace load failure returns to retryable advertising", async () => {
  const client = await launchClient({ failModel: true });
  try {
    await client.page.goto(`${ORIGIN}/#advertising`);
    await expect
      .poll(() =>
        DETECTOR_ASSETS.every((asset) =>
          client.requestedPaths.some((path) => path.endsWith(asset)),
        ),
      )
      .toBe(true);
    await expect(client.page.locator("body")).toHaveAttribute(
      "data-detector-state",
      "recoverable-error",
    );
    await client.page.evaluate(() => {
      document.body.dataset.triggerState = "searching";
      window.dispatchEvent(
        new CustomEvent("face-moment:reference-series-ready", {
          detail: {
            attemptId: "capture-model-failure",
            trigger_source: "test",
            frames: [],
          },
        }),
      );
    });
    await expect(client.page.locator('[data-detector-error="true"]')).toBeVisible();
    await expect(client.page.locator("body")).toHaveAttribute(
      "data-trigger-state",
      "advertising",
    );
    await expect(client.page.locator('[data-view="advertising"]')).toBeVisible();
  } finally {
    await closeClient(client);
  }
});

test("FT-003-AC-008 central-service failure returns advertising with the existing notice", async () => {
  const client = await launchClient();
  try {
    await client.page.goto(`${ORIGIN}/#advertising`);
    await client.page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent("face-moment:attempt-request-start", {
          detail: { attemptId: "central-service-failure", captureId: "capture-service" },
        }),
      );
      window.dispatchEvent(
        new CustomEvent("face-moment:attempt-response", {
          detail: {
            attemptId: "central-service-failure",
            captureId: "capture-service",
            response: { status: 503 },
          },
        }),
      );
    });
    await expect(client.page.locator("body")).toHaveAttribute(
      "data-attempt-state",
      "advertising",
    );
    await expect(client.page.locator("#communication-notice")).toBeVisible();
    await expect(client.page.locator("#communication-notice")).toContainText(
      "Попытка связи с сервером была не успешна в ",
    );
    await expect(client.page.locator('[data-view="advertising"]')).toBeVisible();
  } finally {
    await closeClient(client);
  }
});

test("FT-003-AC-008 optional assets do not block the valid result seam", async () => {
  const client = await launchClient();
  try {
    await client.page.goto(`${ORIGIN}/#advertising`);
    await client.page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent("face-moment:attempt-request-start", {
          detail: { attemptId: "optional-assets", captureId: "capture-optional" },
        }),
      );
      window.dispatchEvent(
        new CustomEvent("face-moment:attempt-response", {
          detail: {
            attemptId: "optional-assets",
            captureId: "capture-optional",
            response: {
              status: 200,
              json: async () => ({
                schema_version: 1,
                attempt_id: "optional-assets",
                outcome: "result",
                result: { session_id: "synthetic-result" },
              }),
            },
          },
        }),
      );
    });
    await expect(client.page.locator("body")).toHaveAttribute("data-attempt-state", "result");
    assert.equal(
      client.requestedPaths.some((requestPath) => /audio|animation/i.test(requestPath)),
      false,
      "optional assets must not be a mandatory request in the valid-result path",
    );
  } finally {
    await closeClient(client);
  }
});

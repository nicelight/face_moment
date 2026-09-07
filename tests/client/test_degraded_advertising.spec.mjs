import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium, expect, test } = require("@playwright/test");

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
const PROMO_DISPLAY_CONFIGURATION = JSON.stringify({
  schema_version: 1,
  result_display_ms: 60_000,
  success_cooldown_ms: 1_000,
});
const PROMO_PREVIEW_JPEG = Buffer.from(
  "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAUDBAQEAwUEBAQFBQUGBwwIBwcHBw8LCwkMEQ8SEhEPERETFhwXExQaFRERGCEYGh0dHx8fExciJCIeJBweHx7/2wBDAQUFBQcGBw4ICA4eFBEUHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh7/wAARCAACAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3t1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD2Kiiivxw+uP/Z",
  "base64",
);

function deferred() {
  let resolve;
  const promise = new Promise((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

function contentType(filePath) {
  if (filePath.endsWith(".js") || filePath.endsWith(".mjs")) return "text/javascript";
  if (filePath.endsWith(".css")) return "text/css";
  if (filePath.endsWith(".html")) return "text/html";
  if (filePath.endsWith(".json")) return "application/json";
  if (filePath.endsWith(".tflite")) return "application/octet-stream";
  if (filePath.endsWith(".wasm")) return "application/wasm";
  return "application/octet-stream";
}

async function routeClient(
  context,
  { failModel = false, requestedPaths, routeOverrides = {} },
) {
  await context.route(`${ORIGIN}/**`, async (route) => {
    const requestPath = new URL(route.request().url()).pathname;
    requestedPaths.push(requestPath);
    if (requestPath === "/api/promo/display/config") {
      if (routeOverrides.displayConfig) {
        await routeOverrides.displayConfig(route);
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: PROMO_DISPLAY_CONFIGURATION,
      });
      return;
    }
    if (requestPath.startsWith("/api/promo/media/")) {
      if (routeOverrides.media) {
        await routeOverrides.media(route);
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "image/jpeg",
        body: PROMO_PREVIEW_JPEG,
      });
      return;
    }
    if (requestPath === "/api/promo/sessions/synthetic-result/display") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "{}",
      });
      return;
    }
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

async function launchClient({
  failModel = false,
  sensorUnavailable = false,
  routeOverrides = {},
} = {}) {
  const profilePath = await mkdtemp(path.join(tmpdir(), "face-moment-degraded-"));
  const requestedPaths = [];
  const context = await chromium.launchPersistentContext(profilePath, {
    headless: true,
  });
  await routeClient(context, { failModel, requestedPaths, routeOverrides });
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
      const browserFetch = globalThis.fetch.bind(globalThis);
      globalThis.fetch = async (input, init) => {
        if (shouldFailSensor && String(input).includes("sensor-fixture.local")) {
          throw new Error("fixture sensor unavailable");
        }
        return browserFetch(input, init);
      };
    },
    { sensorConfig: sensorUnavailable ? SENSOR_CONFIG : null, sensorUnavailable },
  );
  return { context, page, profilePath, requestedPaths };
}

async function closeClient(client) {
  await client.context.close().catch(() => {});
  await rm(client.profilePath, { recursive: true, force: true });
}

async function installAttemptProbe(page) {
  await page.evaluate(() => {
    window.__attemptFinishedEvents = [];
    window.__unhandledRejections = [];
    window.addEventListener("face-moment:attempt-finished", (event) => {
      window.__attemptFinishedEvents.push({ ...event.detail });
    });
    window.addEventListener("unhandledrejection", (event) => {
      window.__unhandledRejections.push(String(event.reason?.message ?? event.reason));
      event.preventDefault();
    });
  });
}

async function dispatchAttemptRequest(page, attemptId) {
  await page.evaluate((id) => {
    window.dispatchEvent(
      new CustomEvent("face-moment:attempt-request-start", {
        detail: { attemptId: id, captureId: `capture-${id}` },
      }),
    );
  }, attemptId);
}

async function dispatchAttemptResult(page, attemptId) {
  await page.evaluate((id) => {
    window.dispatchEvent(
      new CustomEvent("face-moment:attempt-response", {
        detail: {
          attemptId: id,
          captureId: `capture-${id}`,
          response: {
            status: 200,
            json: async () => ({
              schema_version: 1,
              attempt_id: id,
              outcome: "result",
              result: {
                session_id: "synthetic-result-session",
                n: 4,
                qr_url: `${globalThis.location.origin}/q?ticket=${id}-ticket`,
                qr_first_open_expires_at: "2099-01-01T00:00:00Z",
                teasers: [1, 2, 3, 4].map((index) => ({
                  photo_id: `${id}-photo-${index}`,
                  media_url: `${globalThis.location.origin}/api/promo/media/${id}-${index}`,
                })),
              },
            }),
          },
        },
      }),
    );
  }, attemptId);
}

async function finishedEvent(page, attemptId, success) {
  return page.evaluate(
    ({ id, expectedSuccess }) =>
      window.__attemptFinishedEvents.some(
        (event) => event.attemptId === id && event.success === expectedSuccess,
      ),
    { id: attemptId, expectedSuccess: success },
  );
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
    await expect(client.page.locator('[data-view="advertising"]')).toBeVisible();
    await expect(client.page.locator("body")).toHaveAttribute(
      "data-sensor-state",
      "disabled",
    );
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
                result: {
                  session_id: "synthetic-result",
                  n: 4,
                  qr_url: `${globalThis.location.origin}/q?ticket=synthetic-result-ticket`,
                  qr_first_open_expires_at: "2099-01-01T00:00:00Z",
                  teasers: [1, 2, 3, 4].map((index) => ({
                    photo_id: `synthetic-photo-${index}`,
                    media_url: `${globalThis.location.origin}/api/promo/media/synthetic-photo-${index}`,
                  })),
                },
              }),
            },
          },
        }),
      );
    });
    await expect(client.page.locator("body")).toHaveAttribute("data-attempt-state", "result");
    const resultView = client.page.locator('[data-view="result"]');
    await expect(resultView).toBeVisible();
    const previews = resultView.locator(".promo-teaser");
    await expect(previews).toHaveCount(4);
    await expect
      .poll(() =>
        previews.evaluateAll((images) =>
          images.every((image) => image.complete && image.naturalWidth > 0),
        ),
      )
      .toBe(true);
    await expect(client.page.locator("[data-qr-content]")).toHaveAttribute(
      "data-qr-content",
      `${ORIGIN}/q?ticket=synthetic-result-ticket`,
    );
    assert.equal(
      client.requestedPaths.some((requestPath) => /audio|animation/i.test(requestPath)),
      false,
      "optional assets must not be a mandatory request in the valid-result path",
    );
  } finally {
    await closeClient(client);
  }
});

test("Promo config deadline releases a held result and the next attempt renders", async () => {
  test.setTimeout(20_000);
  const configGate = deferred();
  const configStarted = deferred();
  let configCalls = 0;
  const client = await launchClient({
    routeOverrides: {
      displayConfig: async (route) => {
        configStarted.resolve();
        if (configCalls++ === 0) await configGate.promise;
        try {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: PROMO_DISPLAY_CONFIGURATION,
          });
        } catch {
          // The first fetch is expected to be aborted before this late release.
        }
      },
    },
  });
  const pageErrors = [];
  client.page.on("pageerror", (error) => pageErrors.push(error));
  try {
    await client.page.goto(`${ORIGIN}/#advertising`);
    await installAttemptProbe(client.page);
    await dispatchAttemptRequest(client.page, "config-deadline-old");
    await configStarted.promise;

    // Keep the normal result response until config has already rejected. This
    // exercises the rejection observer installed at request start.
    await client.page.waitForTimeout(5_250);
    assert.deepEqual(
      await client.page.evaluate(() => window.__unhandledRejections),
      [],
    );
    await dispatchAttemptResult(client.page, "config-deadline-old");
    await expect
      .poll(() => finishedEvent(client.page, "config-deadline-old", false))
      .toBe(true);
    await expect(client.page.locator('[data-view="advertising"]')).toBeVisible();

    configGate.resolve();
    await client.page.waitForTimeout(250);
    await expect(client.page.locator('[data-view="advertising"]')).toBeVisible();
    assert.deepEqual(
      await client.page.evaluate(() => window.__unhandledRejections),
      [],
    );

    await dispatchAttemptRequest(client.page, "config-deadline-next");
    await dispatchAttemptResult(client.page, "config-deadline-next");
    await expect(client.page.locator('[data-view="result"]')).toBeVisible();
    await expect(client.page.locator(".promo-teaser")).toHaveCount(4);
    await expect
      .poll(() => finishedEvent(client.page, "config-deadline-next", true))
      .toBe(true);
    assert.equal(pageErrors.length, 0);
    assert.deepEqual(
      await client.page.evaluate(() => window.__unhandledRejections),
      [],
    );
  } finally {
    configGate.resolve();
    await closeClient(client);
  }
});

test("one stalled Promo preview fails cleanly and cannot replace the next result", async () => {
  test.setTimeout(20_000);
  const mediaGate = deferred();
  const mediaStarted = deferred();
  let mediaCalls = 0;
  const client = await launchClient({
    routeOverrides: {
      media: async (route) => {
        if (mediaCalls++ === 0) {
          mediaStarted.resolve();
          await mediaGate.promise;
        }
        try {
          await route.fulfill({
            status: 200,
            contentType: "image/jpeg",
            body: PROMO_PREVIEW_JPEG,
          });
        } catch {
          // The first request is expected to be aborted before this late release.
        }
      },
    },
  });
  const pageErrors = [];
  client.page.on("pageerror", (error) => pageErrors.push(error));
  try {
    await client.page.goto(`${ORIGIN}/#advertising`);
    await installAttemptProbe(client.page);
    await dispatchAttemptRequest(client.page, "preview-deadline-old");
    await dispatchAttemptResult(client.page, "preview-deadline-old");
    await mediaStarted.promise;

    // Preparing previews may take up to the bounded deadline. The shared
    // shell must keep its advertising view visible until a complete result is
    // ready or the preparation fails.
    await expect(client.page.locator('[data-view="advertising"]')).toBeVisible();
    await expect(client.page.locator('[data-view="result"]')).toHaveCount(0);

    await client.page.waitForTimeout(5_250);
    await expect
      .poll(() => finishedEvent(client.page, "preview-deadline-old", false))
      .toBe(true);
    await expect(client.page.locator('[data-view="advertising"]')).toBeVisible();

    mediaGate.resolve();
    await client.page.waitForTimeout(250);
    await expect(client.page.locator('[data-view="advertising"]')).toBeVisible();
    assert.deepEqual(
      await client.page.evaluate(() => window.__unhandledRejections),
      [],
    );

    await dispatchAttemptRequest(client.page, "preview-deadline-next");
    await dispatchAttemptResult(client.page, "preview-deadline-next");
    await expect(client.page.locator('[data-view="result"]')).toBeVisible();
    await expect(client.page.locator(".promo-teaser")).toHaveCount(4);
    await expect
      .poll(() => finishedEvent(client.page, "preview-deadline-next", true))
      .toBe(true);
    assert.equal(pageErrors.length, 0);
    assert.deepEqual(
      await client.page.evaluate(() => window.__unhandledRejections),
      [],
    );
  } finally {
    mediaGate.resolve();
    await closeClient(client);
  }
});

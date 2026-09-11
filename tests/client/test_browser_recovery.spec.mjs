import { readFile } from "node:fs/promises";
import { mkdtemp, rm } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium, expect, test } = require("@playwright/test");

const PROJECT_ROOT = path.resolve(import.meta.dirname, "../..");
const SERVICE_PATH = path.join(
  PROJECT_ROOT,
  "deploy/kiosk/spa-promo-client.service",
);
const ORIGIN = "https://face-moment-recovery.test";
const PROMO_DISPLAY_CONFIGURATION = JSON.stringify({
  schema_version: 1,
  result_display_ms: 60_000,
  success_cooldown_ms: 1_000,
});
const PROMO_PREVIEW_JPEG = Buffer.from(
  "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAUDBAQEAwUEBAQFBQUGBwwIBwcHBw8LCwkMEQ8SEhEPERETFhwXExQaFRERGCEYGh0dHx8fExciJCIeJBweHx7/2wBDAQUFBQcGBw4ICA4eFBEUHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh7/wAARCAACAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3t1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD2Kiiivxw+uP/Z",
  "base64",
);

const MANAGED_CONFIG = Object.freeze({
  "face-moment.display-client-token": "synthetic-display-token-not-a-secret",
  "face-moment.camera.device-id": "synthetic-camera",
  "face-moment.jpeg-quality": "0.9",
  "face-moment.sensor-config": JSON.stringify({
    host: "sensor-fixture.local",
    sensorId: "sensor-fixture",
    secret: "synthetic-sensor-secret-not-a-secret",
  }),
});

async function routeClient(context) {
  await context.route(`${ORIGIN}/**`, async (route) => {
    const requestPath = new URL(route.request().url()).pathname;
    if (requestPath === "/api/promo/display/config") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: PROMO_DISPLAY_CONFIGURATION,
      });
      return;
    }
    if (requestPath.startsWith("/api/promo/media/")) {
      await route.fulfill({
        status: 200,
        contentType: "image/jpeg",
        body: PROMO_PREVIEW_JPEG,
      });
      return;
    }
    if (requestPath === "/api/promo/sessions/synthetic-result-session/display") {
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
    const filePath = path.resolve(PROJECT_ROOT, relativePath);
    if (!filePath.startsWith(path.join(PROJECT_ROOT, "client") + path.sep)) {
      await route.fulfill({ status: 404, body: "not found" });
      return;
    }
    const contentType = filePath.endsWith(".js") || filePath.endsWith(".mjs")
      ? "text/javascript"
      : filePath.endsWith(".css")
        ? "text/css"
        : filePath.endsWith(".html")
          ? "text/html"
          : "application/octet-stream";
    try {
      await route.fulfill({
        status: 200,
        contentType,
        body: await readFile(filePath),
      });
    } catch {
      await route.fulfill({ status: 404, body: "not found" });
    }
  });
}

async function launchProfile(profilePath, { seedManagedConfiguration = false } = {}) {
  const context = await chromium.launchPersistentContext(profilePath, {
    headless: true,
  });
  await routeClient(context);
  const page = context.pages()[0] ?? await context.newPage();
  if (seedManagedConfiguration) {
    await page.addInitScript((entries) => {
      for (const [key, value] of Object.entries(entries)) {
        localStorage.setItem(key, value);
      }
    }, MANAGED_CONFIG);
  }
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        enumerateDevices: async () => [],
        getUserMedia: async () => {
          throw new DOMException("fixture camera unavailable", "NotFoundError");
        },
      },
    });
    const browserFetch = globalThis.fetch.bind(globalThis);
    globalThis.fetch = async (input, init) => {
      const url = new URL(String(input), globalThis.location.href);
      if (url.hostname === "sensor-fixture.local") {
        return new Response(null, { status: 503 });
      }
      return browserFetch(input, init);
    };
  });
  return { context, page };
}

async function enterParticipantState(page, state) {
  await page.evaluate(async (targetState) => {
    const participantSnapshot = {
      referenceFrame: "synthetic-frame",
      qrSessionToken: "synthetic-session-token",
      activeAttempt: "synthetic-attempt",
    };
    Object.assign(document.body.dataset, participantSnapshot);

    if (targetState === "advertising") {
      document.body.dataset.attemptState = "advertising";
      return;
    }

    const attemptId = `synthetic-${targetState}`;
    window.dispatchEvent(new CustomEvent("face-moment:attempt-request-start", {
      detail: { attemptId, captureId: `series-${targetState}` },
    }));
    if (targetState === "active") return;

    window.dispatchEvent(new CustomEvent("face-moment:attempt-response", {
      detail: {
        attemptId,
        captureId: `series-${targetState}`,
        response: {
          status: 200,
          json: async () => ({
            schema_version: 1,
            attempt_id: attemptId,
            outcome: "result",
            result: {
              session_id: "synthetic-result-session",
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
    }));
  }, state);
  const expectedState = state === "active" ? "searching" : state;
  await expect(page.locator("body")).toHaveAttribute(
    "data-attempt-state",
    expectedState,
  );
  if (state === "result") {
    const resultView = page.locator('[data-view="result"]');
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
    await expect(page.locator("[data-qr-content]")).toHaveAttribute(
      "data-qr-content",
      `${ORIGIN}/q?ticket=synthetic-result-ticket`,
    );
  }
}

for (const state of ["advertising", "active", "result"]) {
  test(`FT-003-AC-012 reload from ${state} retains only managed kiosk configuration`, async () => {
    const service = await readFile(SERVICE_PATH, "utf8");
    expect(service.match(/^Restart=.*$/gm)).toEqual(["Restart=always"]);
    expect(service).toMatch(/^User=display$/m);
    expect(service).toMatch(/^Group=display$/m);
    expect(service).not.toMatch(/--no-sandbox|--disable-setuid-sandbox/);

    const profilePath = await mkdtemp(path.join(tmpdir(), "face-moment-task-054."));
    let launched;
    try {
      launched = await launchProfile(profilePath, { seedManagedConfiguration: true });
      await launched.page.goto(`${ORIGIN}/#advertising`);
      await expect(launched.page.locator('[data-view="advertising"]')).toBeAttached();
      await expect(launched.page.locator('#replay-last-promo')).toBeVisible();
      await expect(launched.page.locator("body")).toHaveAttribute(
        "data-sensor-state",
        "recoverable-error",
      );
      await enterParticipantState(launched.page, state);
      await launched.context.close();
      launched = undefined;

      launched = await launchProfile(profilePath);
      await launched.page.goto(`${ORIGIN}/#advertising`);
      await expect(launched.page.locator('[data-view="advertising"]')).toBeAttached();
      await expect(launched.page.locator('#replay-last-promo')).toBeVisible();
      await expect(launched.page.locator("body")).toHaveAttribute(
        "data-sensor-state",
        "recoverable-error",
      );
      const recovered = await launched.page.evaluate(async () => {
        const { readSensorConfig } = await import("/client/sensor-config.js");
        return {
          config: Object.fromEntries(
            Object.keys(localStorage)
              .sort()
              .map((key) => [key, localStorage.getItem(key)]),
          ),
          sensorConfig: readSensorConfig(),
          participant: {
            attemptState: document.body.dataset.attemptState ?? null,
            referenceFrame: document.body.dataset.referenceFrame ?? null,
            qrSessionToken: document.body.dataset.qrSessionToken ?? null,
            activeAttempt: document.body.dataset.activeAttempt ?? null,
          },
        };
      });
      expect(recovered.config).toEqual(MANAGED_CONFIG);
      expect(recovered.sensorConfig).toEqual({
        host: "http://sensor-fixture.local",
        sensorId: "sensor-fixture",
        secret: "synthetic-sensor-secret-not-a-secret",
      });
      expect(recovered.participant).toEqual({
        attemptState: null,
        referenceFrame: null,
        qrSessionToken: null,
        activeAttempt: null,
      });
      await launched.context.close();
      launched = undefined;
    } finally {
      await launched?.context.close().catch(() => {});
      await rm(profilePath, { recursive: true, force: true });
    }
  });
}

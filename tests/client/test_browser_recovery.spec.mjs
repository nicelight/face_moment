import { readFile } from "node:fs/promises";
import { mkdtemp, rm } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium, expect, test } = require("playwright/test");

const PROJECT_ROOT = path.resolve(import.meta.dirname, "../..");
const SERVICE_PATH = path.join(
  PROJECT_ROOT,
  "deploy/kiosk/spa-promo-client.service",
);
const ORIGIN = "https://face-moment-recovery.test";

const MANAGED_CONFIG = Object.freeze({
  "face-moment.display-client-token": "synthetic-display-token-not-a-secret",
  "face-moment.camera.device-id": "synthetic-camera",
  "face-moment.jpeg-quality": "0.9",
  "face-moment.sensor-config": JSON.stringify({
    host: "sensor-fixture.local",
    sensor_id: "sensor-fixture",
    secret: "synthetic-sensor-secret-not-a-secret",
  }),
});

async function routeClient(context) {
  await context.route(`${ORIGIN}/**`, async (route) => {
    const requestPath = new URL(route.request().url()).pathname;
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

async function launchProfile(profilePath) {
  const context = await chromium.launchPersistentContext(profilePath, {
    headless: true,
  });
  await routeClient(context);
  const page = context.pages()[0] ?? await context.newPage();
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
    globalThis.fetch = async () => ({ status: 204, ok: true });
  });
  return { context, page };
}

async function seedManagedConfiguration(page) {
  await page.evaluate((entries) => {
    for (const [key, value] of Object.entries(entries)) {
      localStorage.setItem(key, value);
    }
  }, MANAGED_CONFIG);
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
            result: { session_id: "synthetic-result-session", teasers: [] },
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
      launched = await launchProfile(profilePath);
      await launched.page.goto(`${ORIGIN}/#advertising`);
      await expect(launched.page.locator('[data-view="advertising"]')).toBeVisible();
      await seedManagedConfiguration(launched.page);
      await enterParticipantState(launched.page, state);
      await launched.context.close();
      launched = undefined;

      launched = await launchProfile(profilePath);
      await launched.page.goto(`${ORIGIN}/#advertising`);
      await expect(launched.page.locator('[data-view="advertising"]')).toBeVisible();
      const recovered = await launched.page.evaluate(() => ({
        config: Object.fromEntries(
          Object.keys(localStorage)
            .sort()
            .map((key) => [key, localStorage.getItem(key)]),
        ),
        participant: {
          attemptState: document.body.dataset.attemptState ?? null,
          referenceFrame: document.body.dataset.referenceFrame ?? null,
          qrSessionToken: document.body.dataset.qrSessionToken ?? null,
          activeAttempt: document.body.dataset.activeAttempt ?? null,
        },
      }));
      expect(recovered.config).toEqual(MANAGED_CONFIG);
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

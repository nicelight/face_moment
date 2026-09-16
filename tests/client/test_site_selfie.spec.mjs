import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const { expect, test } = require("@playwright/test");

const PROJECT_ROOT = path.resolve(import.meta.dirname, "../..");
const ORIGIN = "https://face-moment-site.test";

function contentType(filePath) {
  if (filePath.endsWith(".html")) return "text/html";
  if (filePath.endsWith(".css")) return "text/css";
  if (filePath.endsWith(".js")) return "text/javascript";
  return "application/octet-stream";
}

async function routeSite(page) {
  await page.route(`${ORIGIN}/**`, async (route) => {
    const requestPath = new URL(route.request().url()).pathname;
    const relativePath = requestPath === "/" ? "client/site.html" : requestPath.slice(1);
    if (!relativePath.startsWith("client/")) {
      await route.fulfill({ status: 404, body: "not found" });
      return;
    }
    try {
      const filePath = path.resolve(PROJECT_ROOT, relativePath);
      await route.fulfill({
        contentType: contentType(filePath),
        body: await readFile(filePath),
      });
    } catch {
      await route.fulfill({ status: 404, body: "not found" });
    }
  });
}

async function installCameraFixture(page) {
  await page.addInitScript(() => {
    let attempts = 0;
    const tracks = [{ stop() {} }];
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: async () => {
          attempts += 1;
          if (attempts === 1) throw new DOMException("fixture permission denied", "NotAllowedError");
          return { getTracks: () => tracks };
        },
      },
    });
    Object.defineProperty(HTMLMediaElement.prototype, "srcObject", {
      configurable: true,
      get() { return this.__fixtureSrcObject ?? null; },
      set(value) { this.__fixtureSrcObject = value; },
    });
    globalThis.__selfieCameraAttempts = () => attempts;
    Object.defineProperty(HTMLMediaElement.prototype, "readyState", {
      configurable: true,
      get: () => HTMLMediaElement.HAVE_ENOUGH_DATA,
    });
    Object.defineProperty(HTMLVideoElement.prototype, "videoWidth", {
      configurable: true,
      get: () => 640,
    });
    Object.defineProperty(HTMLVideoElement.prototype, "videoHeight", {
      configurable: true,
      get: () => 480,
    });
    HTMLMediaElement.prototype.play = async () => {};
    HTMLCanvasElement.prototype.getContext = () => ({ drawImage() {} });
    HTMLCanvasElement.prototype.toBlob = (callback) => callback(new Blob(["fixture"], { type: "image/jpeg" }));
    HTMLImageElement.prototype.decode = async () => {};
  });
}

test("public selfie viewport owns camera start/capture and preserves honest retry limits", async ({ page }) => {
  await routeSite(page);
  await installCameraFixture(page);
  await page.goto(`${ORIGIN}/`);

  await expect(page.getByText("Настроить Fluid", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Включить камеру/ })).toHaveCount(0);
  await expect(page.locator("#how-it-works .fm-step")).toHaveCount(3);
  await expect(page.locator(".fm-selfie-copy")).toHaveCount(0);

  const viewport = page.locator("#selfie-viewport");
  await viewport.click();
  await expect(page.locator("#selfie-status")).toContainText("не разрешён");
  await expect(viewport).toHaveAttribute("data-state", "error");

  await viewport.click();
  await expect(viewport).toHaveAttribute("data-state", "ready");
  await expect(page.locator("#selfie-ready-overlay")).toBeVisible();
  await expect(page.locator("#selfie-ready-overlay text")).toHaveText("Жмак меня");
  await expect(viewport).toHaveAttribute("aria-label", "Сделать снимок");

  await viewport.focus();
  await page.keyboard.press("Enter");
  await expect(viewport).toHaveAttribute("data-state", "captured");
  await expect(page.locator("#selfie-search-overlay")).toHaveText("подбираем Ваши фото..");
  await expect(page.locator("#selfie-search-overlay")).toBeVisible();
  await expect(page.locator("#selfie-ready-overlay")).toBeHidden();
  await expect(page.locator("#selfie-retake")).toBeVisible();
  expect(await page.evaluate(() => globalThis.__selfieCameraAttempts())).toBe(2);
  await expect(page.locator("#selfie-status")).toContainText("Отправка на поиск станет доступна после запуска сервиса");
});

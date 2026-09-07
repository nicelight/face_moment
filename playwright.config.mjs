import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/client",
  testMatch: "**/*.spec.mjs",
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  outputDir: ".tasks/ASTRA-findings/07-browser-runner/playwright-results",
  use: {
    browserName: "chromium",
    headless: true,
  },
});

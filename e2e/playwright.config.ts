import { defineConfig } from "@playwright/test";

// Caddy e2e serves a self-signed internal-CA cert on https://localhost (API)
// and https://localhost:3000 (app) — bypass for both Node helpers and browser.
process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";

export default defineConfig({
  testDir: "./tests",
  // Specs poll server-side ticks up to 120s plus UI assertions on top
  // (04 missed-lock, 06 refill feed) — 300s covers the worst case.
  timeout: 300_000,
  expect: { timeout: 15_000 },
  // Serial: one shared stack + deterministic seed state.
  workers: 1,
  retries: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  outputDir: "./test-results",
  use: {
    baseURL: process.env.E2E_APP_URL ?? "https://localhost:3000",
    ignoreHTTPSErrors: true,
    timezoneId: "UTC",
    locale: "en-US",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
});

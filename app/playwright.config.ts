import { defineConfig, devices } from "@playwright/test";

/**
 * E2E for the web build. Run `npm run export:web` first; the static build is served on :4173.
 * The app talks to the API at http://<host>:8000 (see src/api/client.ts). Without a backend the
 * app falls back to clearly-labelled MOCK fixtures, so the flow is still testable.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:4173", trace: "retain-on-failure" },
  projects: [
    { name: "chromium-desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : { command: "npx serve -s dist -l 4173", port: 4173, reuseExistingServer: true, timeout: 60_000 },
});

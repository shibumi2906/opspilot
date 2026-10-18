import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "../tests/e2e",
  tsconfig: "./tsconfig.json",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  expect: { timeout: 20000 },
  retries: 0,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8080",
    browserName: "chromium",
    channel: process.env.E2E_BROWSER_CHANNEL,
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});

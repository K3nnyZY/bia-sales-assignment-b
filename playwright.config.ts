import { defineConfig } from "@playwright/test";

process.loadEnvFile(".env");

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45000,
  use: {
    baseURL:
      process.env.E2E_BASE_URL ||
      `http://127.0.0.1:${process.env.WEB_PORT || "3000"}`,
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    headless: true,
    trace: "retain-on-failure",
  },
  reporter: "list",
});

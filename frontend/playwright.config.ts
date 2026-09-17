import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against the real stack: Next.js, FastAPI and PostgreSQL.
 * Servers are expected to be running already (see docs/DEVELOPMENT.md).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // the suite shares one database
  workers: 1,
  reporter: [["list"]],
  timeout: 30_000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Use the Chromium already present in the environment rather than
        // downloading a matching build.
        launchOptions: process.env.CHROMIUM_PATH
          ? { executablePath: process.env.CHROMIUM_PATH }
          : {},
      },
    },
  ],
});

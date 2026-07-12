import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",
  testMatch: "**/*.runtime.spec.ts",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    ...devices["Desktop Chrome"],
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: "corepack pnpm --filter @cf/card-web dev",
    url: "http://127.0.0.1:4173/c/tuotu",
    reuseExistingServer: true,
    timeout: 120_000,
    env: {
      ...process.env,
      VITE_API_BASE_URL: "http://127.0.0.1:8000/api/v1",
    },
  },
});

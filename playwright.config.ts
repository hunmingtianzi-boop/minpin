import { defineConfig, devices } from "@playwright/test";

const apiBaseUrl = "http://127.0.0.1:8000/api/v1";

export default defineConfig({
  testDir: "tests/e2e",
  testIgnore: "**/*.runtime.spec.ts",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI
    ? [["line"], ["html", { outputFolder: "artifacts/playwright-report", open: "never" }]]
    : "list",
  use: {
    ...devices["Desktop Chrome"],
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: "corepack pnpm --filter @cf/card-web dev",
      url: "http://127.0.0.1:4173/c/template",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { ...process.env, VITE_API_BASE_URL: apiBaseUrl },
    },
    {
      command: "corepack pnpm --filter @cf/admin-web dev",
      url: "http://127.0.0.1:4174/",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { ...process.env, VITE_API_BASE_URL: apiBaseUrl },
    },
  ],
});

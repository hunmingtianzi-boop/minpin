import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "tests/performance",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  reporter: "line",
  outputDir: "artifacts/playwright-performance",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4183",
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command:
      "corepack pnpm --filter @cf/card-web preview --host 127.0.0.1 --port 4183 --strictPort",
    url: "http://127.0.0.1:4183/c/template",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});

import { mkdir, writeFile } from "node:fs/promises";
import { expect, test, type Browser, type Page } from "@playwright/test";

const SAMPLE_COUNT = 5;
const LCP_P75_LIMIT_MS = 2_500;
const CLS_P75_LIMIT = 0.1;

type Sample = {
  lcpMs: number;
  cls: number;
  fcpMs: number;
  ttfbMs: number;
  loadMs: number;
};

function nearestRank(values: number[], percentile: number) {
  if (!values.length) throw new Error("Web Vitals sample set is empty.");
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.max(0, Math.ceil(percentile * sorted.length) - 1)];
}

async function instrument(page: Page) {
  await page.addInitScript(() => {
    const state = { lcpMs: 0, cls: 0 };
    Object.defineProperty(window, "__cfWebVitals", {
      configurable: false,
      enumerable: false,
      value: state,
      writable: false,
    });
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      const last = entries.at(-1);
      if (last) state.lcpMs = last.startTime;
    }).observe({ type: "largest-contentful-paint", buffered: true });
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as PerformanceEntry & {
          hadRecentInput?: boolean;
          value?: number;
        };
        if (!shift.hadRecentInput) state.cls += shift.value ?? 0;
      }
    }).observe({ type: "layout-shift", buffered: true });
  });

  await page.route("**/api/v1/**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json; charset=utf-8",
      body: JSON.stringify({
        error: { code: "CARD_NOT_FOUND", message: "Performance fixture has no published card." },
      }),
    });
  });
}

async function measure(browser: Browser): Promise<Sample> {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    serviceWorkers: "block",
  });
  const page = await context.newPage();
  await instrument(page);
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 150,
    downloadThroughput: (4 * 1024 * 1024) / 8,
    uploadThroughput: (750 * 1024) / 8,
    connectionType: "cellular4g",
  });
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });

  await page.goto("/c/template", { waitUntil: "networkidle" });
  await page.evaluate(async () => {
    await document.fonts.ready;
    const aboveFoldImages = Array.from(document.images).filter(
      (image) => image.getBoundingClientRect().top < window.innerHeight * 1.5,
    );
    await Promise.race([
      Promise.all(
        aboveFoldImages.map((image) =>
          image.complete
            ? Promise.resolve()
            : new Promise<void>((resolve) => {
                image.addEventListener("load", () => resolve(), { once: true });
                image.addEventListener("error", () => resolve(), { once: true });
              }),
        ),
      ),
      new Promise<void>((resolve) => window.setTimeout(resolve, 3_000)),
    ]);
  });
  await page.waitForTimeout(1_000);

  const sample = await page.evaluate(() => {
    const state = (
      window as typeof window & { __cfWebVitals: { lcpMs: number; cls: number } }
    ).__cfWebVitals;
    const navigation = performance.getEntriesByType("navigation")[0] as
      | PerformanceNavigationTiming
      | undefined;
    const fcp = performance.getEntriesByName("first-contentful-paint")[0];
    return {
      lcpMs: state.lcpMs,
      cls: state.cls,
      fcpMs: fcp?.startTime ?? 0,
      ttfbMs: navigation ? navigation.responseStart - navigation.requestStart : 0,
      loadMs: navigation?.loadEventEnd ?? 0,
    };
  });
  await context.close();
  return sample;
}

test("production card build meets the common-4G P75 Web Vitals gate", async ({ browser }) => {
  const samples: Sample[] = [];
  for (let index = 0; index < SAMPLE_COUNT; index += 1) {
    samples.push(await measure(browser));
  }

  const lcpP75Ms = nearestRank(samples.map((sample) => sample.lcpMs), 0.75);
  const clsP75 = nearestRank(samples.map((sample) => sample.cls), 0.75);
  const passed = lcpP75Ms <= LCP_P75_LIMIT_MS && clsP75 <= CLS_P75_LIMIT;
  const report = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    buildId: process.env.GITHUB_SHA ?? "local-worktree",
    target: "card-web production preview /c/template",
    measurement: "Chromium PerformanceObserver; nearest-rank P75",
    conditions: {
      network: "controlled common 4G",
      latencyMs: 150,
      downloadMbps: 4,
      uploadKbps: 750,
      cpuSlowdownMultiplier: 4,
      cache: "disabled",
      samples: SAMPLE_COUNT,
    },
    thresholds: { lcpP75Ms: LCP_P75_LIMIT_MS, clsP75: CLS_P75_LIMIT },
    observed: { lcpP75Ms, clsP75 },
    samples,
    passed,
    disclaimer:
      "This controlled CI regression gate does not replace staging capacity, availability, or field-data acceptance.",
  };
  await mkdir("artifacts/perf", { recursive: true });
  await writeFile("artifacts/perf/web-vitals.json", `${JSON.stringify(report, null, 2)}\n`, "utf8");

  expect(lcpP75Ms, JSON.stringify(report, null, 2)).toBeGreaterThan(0);
  expect(lcpP75Ms, JSON.stringify(report, null, 2)).toBeLessThanOrEqual(LCP_P75_LIMIT_MS);
  expect(clsP75, JSON.stringify(report, null, 2)).toBeLessThanOrEqual(CLS_P75_LIMIT);
});

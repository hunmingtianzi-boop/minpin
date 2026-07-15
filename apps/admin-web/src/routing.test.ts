import { afterEach, describe, expect, it, vi } from "vitest";

async function loadRouting(baseUrl: string) {
  vi.resetModules();
  vi.stubEnv("BASE_URL", baseUrl);
  return import("./routing");
}

describe("admin subpath routing", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    window.history.replaceState({}, "", "/");
  });

  it("keeps root deployment paths unchanged", async () => {
    const routing = await loadRouting("/");

    expect(routing.appHref(routing.APP_PATHS.visits)).toBe("/visits");
    expect(routing.appPathFromBrowser("/visits")).toBe("/visits");
  });

  it("maps browser URLs into and out of the production admin base", async () => {
    const routing = await loadRouting("/c/admin/");

    expect(routing.appHref(routing.APP_PATHS.overview)).toBe("/c/admin/");
    expect(routing.appHref(routing.APP_PATHS.visits)).toBe("/c/admin/visits");
    expect(routing.appHref("/conversations?visitorId=visitor-1")).toBe(
      "/c/admin/conversations?visitorId=visitor-1",
    );
    expect(routing.appPathFromBrowser("/c/admin/visits")).toBe("/visits");
    expect(routing.appPathFromBrowser("/c/admin/")).toBe("/");
    expect(routing.appPathFromBrowser("/unrelated")).toBe("/unrelated");
  });
});

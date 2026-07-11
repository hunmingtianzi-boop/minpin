import { afterEach, describe, expect, it, vi } from "vitest";

import {
  loadTenant,
  registeredTenantSlugs,
  resolveTenantSlug,
} from ".";
import { templateTenant } from "./template/tenant";
import { tuotuTenant } from "./tuotu/tenant";

describe("tenant registry", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("resolves a tenant from the card path before the query string", () => {
    const slug = resolveTenantSlug({
      pathname: "/c/tuotu",
      search: "?tenant=unknown",
    });

    expect(slug).toBe("tuotu");
  });

  it("resolves the card path and ignores letter case", () => {
    const slug = resolveTenantSlug({ pathname: "/c/TUOTU", search: "" });

    expect(slug).toBe("tuotu");
  });

  it("does not substitute another brand when a tenant is not registered", async () => {
    await expect(loadTenant("missing")).resolves.toBeUndefined();
    await expect(loadTenant("tuo!tu")).resolves.toBeUndefined();
    await expect(loadTenant("TUOTU")).resolves.toBeUndefined();
    expect(resolveTenantSlug({ pathname: "/c/missing", search: "" })).toBe("missing");
    expect(resolveTenantSlug({ pathname: "/c/tuo!tu", search: "" })).toBeUndefined();
    await expect(loadTenant("tuotu")).resolves.toBe(tuotuTenant);
  });

  it("registers the runnable generic template tenant", async () => {
    expect(registeredTenantSlugs).toEqual(["template", "tuotu"]);
    await expect(loadTenant("template")).resolves.toBe(templateTenant);
    expect(resolveTenantSlug({ pathname: "/c/template", search: "" })).toBe(
      "template",
    );
  });

  it("uses the template tenant for a tenant-free root", () => {
    vi.stubEnv("VITE_DEFAULT_TENANT", "");

    expect(resolveTenantSlug({ pathname: "/", search: "" })).toBe("template");
  });

  it("keeps a safe unknown slug for database lookup without static fallback", () => {
    vi.stubEnv("VITE_DEFAULT_TENANT", "");

    expect(
      resolveTenantSlug({ pathname: "/", search: "?tenant=missing" }),
    ).toBe("missing");
    expect(
      resolveTenantSlug({ pathname: "/c/missing", search: "" }),
    ).toBe("missing");
  });

  it("honors a configured default without affecting explicit Tuotu routes", () => {
    vi.stubEnv("VITE_DEFAULT_TENANT", "template");

    expect(resolveTenantSlug({ pathname: "/", search: "" })).toBe("template");
    expect(resolveTenantSlug({ pathname: "/c/tuotu", search: "" })).toBe(
      "tuotu",
    );
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getTenant,
  resolveTenantSlug,
  templateTenant,
  tenantRegistry,
  tuotuTenant,
} from ".";

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

  it("does not substitute another brand when a tenant is not registered", () => {
    expect(getTenant("missing")).toBeUndefined();
    expect(getTenant("tuo!tu")).toBeUndefined();
    expect(getTenant("TUOTU")).toBeUndefined();
    expect(resolveTenantSlug({ pathname: "/c/missing", search: "" })).toBeUndefined();
    expect(getTenant("tuotu")).toBe(tuotuTenant);
  });

  it("registers the runnable generic template tenant", () => {
    expect(tenantRegistry.template).toBe(templateTenant);
    expect(getTenant("template")).toBe(templateTenant);
    expect(resolveTenantSlug({ pathname: "/c/template", search: "" })).toBe(
      "template",
    );
  });

  it("uses the template tenant for a tenant-free root", () => {
    vi.stubEnv("VITE_DEFAULT_TENANT", "");

    expect(resolveTenantSlug({ pathname: "/", search: "" })).toBe("template");
  });

  it("does not fall back when an unknown tenant is requested explicitly", () => {
    vi.stubEnv("VITE_DEFAULT_TENANT", "");

    expect(
      resolveTenantSlug({ pathname: "/", search: "?tenant=missing" }),
    ).toBeUndefined();
    expect(
      resolveTenantSlug({ pathname: "/c/missing", search: "" }),
    ).toBeUndefined();
  });

  it("honors a configured default without affecting explicit Tuotu routes", () => {
    vi.stubEnv("VITE_DEFAULT_TENANT", "template");

    expect(resolveTenantSlug({ pathname: "/", search: "" })).toBe("template");
    expect(resolveTenantSlug({ pathname: "/c/tuotu", search: "" })).toBe(
      "tuotu",
    );
  });
});

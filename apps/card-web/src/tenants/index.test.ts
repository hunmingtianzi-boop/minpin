import { afterEach, describe, expect, it, vi } from "vitest";

import {
  isBlankEnterpriseTemplateEnabled,
  loadTenant,
  registeredTenantSlugs,
  resolveTenantSlug,
} from ".";
import { blankEnterpriseTenant } from "./blank/tenant";
import { templateTenant } from "./template/tenant";
import { tuotuTenant } from "./tuotu/tenant";

describe("tenant registry", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("keeps the blank enterprise build gate explicit outside development", () => {
    expect(
      isBlankEnterpriseTemplateEnabled({ dev: false, configured: undefined }),
    ).toBe(false);
    expect(
      isBlankEnterpriseTemplateEnabled({ dev: false, configured: "false" }),
    ).toBe(false);
    expect(
      isBlankEnterpriseTemplateEnabled({ dev: false, configured: "true" }),
    ).toBe(true);
    expect(
      isBlankEnterpriseTemplateEnabled({ dev: true, configured: undefined }),
    ).toBe(true);
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
    expect(registeredTenantSlugs).toEqual(["template", "blank-enterprise", "tuotu"]);
    await expect(loadTenant("template")).resolves.toBe(templateTenant);
    expect(resolveTenantSlug({ pathname: "/c/template", search: "" })).toBe(
      "template",
    );
  });

  it("registers a neutral blank enterprise without client facts", async () => {
    await expect(loadTenant("blank-enterprise")).resolves.toBe(
      blankEnterpriseTenant,
    );
    expect(
      resolveTenantSlug({ pathname: "/c/blank-enterprise", search: "" }),
    ).toBe("blank-enterprise");
    expect(blankEnterpriseTenant.isBlankTemplate).toBe(true);
    expect(JSON.stringify(blankEnterpriseTenant)).not.toMatch(
      /tuotu|拓浙|拓拓|浙江大学/i,
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

import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "./client";
import { createPlatformApi } from "./platformApi";

describe("platformApi", () => {
  it("normalizes enterprise list records", async () => {
    const client = {
      get: vi.fn().mockResolvedValue({
        data: [
          {
            tenant_id: "tenant-1",
            tenant_slug: "acme",
            tenant_name: "Acme Tenant",
            company_id: "company-1",
            company_name: "Acme",
            status: "active",
            created_at: "2026-07-11T00:00:00Z",
          },
        ],
        total: 1,
      }),
    } as unknown as ApiClient;

    const values = await createPlatformApi(client).listEnterprises();

    expect(values).toEqual([
      expect.objectContaining({ tenantSlug: "acme", companyName: "Acme" }),
    ]);
    expect(client.get).toHaveBeenCalledWith("/platform/enterprises?limit=50&offset=0");
  });

  it("sends the initial administrator secret only in the create request", async () => {
    const client = {
      post: vi.fn().mockResolvedValue({
        data: {
          tenant_id: "tenant-1",
          tenant_slug: "acme",
          tenant_name: "Acme Tenant",
          company_id: "company-1",
          company_name: "Acme",
          company_status: "active",
          admin_user_id: "user-1",
          admin_membership_id: "membership-1",
          initial_card_id: "card-1",
          initial_card_slug: "c-random",
          created_at: "2026-07-11T00:00:00Z",
        },
      }),
    } as unknown as ApiClient;

    const created = await createPlatformApi(client).createEnterprise({
      tenantSlug: "acme",
      tenantName: "Acme Tenant",
      companyName: "Acme",
      industry: "AI",
      adminAccount: "admin@acme.test",
      adminDisplayName: "Acme Admin",
      adminPassword: "Initial-Password-2026!",
      initialCardTitle: "Acme Card",
    });

    expect(created.initialCardSlug).toBe("c-random");
    expect(client.post).toHaveBeenCalledWith(
      "/platform/enterprises",
      expect.objectContaining({
        tenant_slug: "acme",
        admin_password: "Initial-Password-2026!",
      }),
    );
    expect(JSON.stringify(created)).not.toContain("Initial-Password-2026!");
  });
});

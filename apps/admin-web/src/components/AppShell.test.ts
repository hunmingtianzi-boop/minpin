import { describe, expect, it } from "vitest";

import type { AdminUser } from "../api/types";
import { hasNavPermission } from "./AppShell";

function user(role: string, permissions: string[] = []): AdminUser {
  return {
    id: "user-1",
    displayName: "林顾问",
    membershipId: "membership-1",
    tenantId: "tenant-1",
    companyId: "company-1",
    role,
    permissions,
  };
}

describe("hasNavPermission", () => {
  it("allows company administrators to reach every management area", () => {
    expect(hasNavPermission(user("company_admin"), "catalog.read")).toBe(true);
    expect(hasNavPermission(user("company_admin"), "forbidden_topic.read")).toBe(true);
  });

  it("keeps card owners inside explicitly granted areas", () => {
    const owner = user("card_owner", ["card.read"]);
    expect(hasNavPermission(owner, "card.read")).toBe(true);
    expect(hasNavPermission(owner, "visits.read", true)).toBe(true);
    expect(hasNavPermission(owner, "conversations.read", true)).toBe(true);
    expect(hasNavPermission(owner, "leads.read", true)).toBe(true);
    expect(hasNavPermission(owner, "catalog.read")).toBe(false);
    expect(hasNavPermission(owner, "privacy.manage")).toBe(false);
    expect(hasNavPermission(owner, "forbidden_topic.read")).toBe(false);
  });

  it("accepts workflow permission aliases but hides unrelated governance areas", () => {
    const operator = user("staff", ["conversations.read", "leads.write"]);
    expect(hasNavPermission(operator, "analytics.read")).toBe(true);
    expect(hasNavPermission(operator, "visits.read")).toBe(true);
    expect(hasNavPermission(operator, "leads.read")).toBe(true);
    expect(hasNavPermission(operator, "privacy.manage")).toBe(false);
  });
});

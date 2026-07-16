import { describe, expect, it } from "vitest";

import type { AdminUser } from "../api/types";
import {
  adminWorkspaceForUser,
  canAccessAdminWorkspace,
  hasPermission,
} from "./permissions";

function user(role: string, permissions: string[] = []): AdminUser {
  return {
    id: "user-1",
    displayName: "User",
    membershipId: "membership-1",
    tenantId: "tenant-1",
    companyId: "company-1",
    role,
    permissions,
  };
}

describe("admin workspace boundaries", () => {
  it("keeps platform administrators inside platform permissions", () => {
    const platform = user("platform_admin");

    expect(adminWorkspaceForUser(platform)).toBe("platform");
    expect(canAccessAdminWorkspace(platform, "platform")).toBe(true);
    expect(canAccessAdminWorkspace(platform, "enterprise")).toBe(false);
    expect(hasPermission(platform, "platform.llm.manage")).toBe(true);
    expect(hasPermission(platform, "knowledge.write")).toBe(false);
  });

  it("keeps every non-platform staff membership in the enterprise workspace", () => {
    const companyAdmin = user("company_admin");
    const delegatedAuditor = user("auditor", ["analytics.read"]);

    expect(adminWorkspaceForUser(companyAdmin)).toBe("enterprise");
    expect(adminWorkspaceForUser(delegatedAuditor)).toBe("enterprise");
    expect(canAccessAdminWorkspace(companyAdmin, "platform")).toBe(false);
    expect(hasPermission(companyAdmin, "platform.enterprise.read")).toBe(false);
    expect(hasPermission(companyAdmin, "knowledge.write")).toBe(true);
  });
});

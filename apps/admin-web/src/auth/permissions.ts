import type { AdminUser } from "../api/types";

export type AdminWorkspace = "platform" | "enterprise";

export const PLATFORM_ROLE = "platform_admin" as const;

export const permissionAliases: Record<string, string[]> = {
  "company.read": ["company.profile.read", "company.profile.write", "company.manage"],
  "card.read": ["card.read", "card.write", "card.manage"],
  "catalog.read": [
    "catalog.read",
    "catalog.write",
    "catalog.publish",
    "catalog.manage",
    "product.read",
    "product.write",
    "product.publish",
    "case_study.read",
    "case_study.write",
    "case_study.publish",
  ],
  "knowledge.read": [
    "knowledge.read",
    "knowledge.write",
    "knowledge.review",
    "knowledge.publish",
    "knowledge.manage",
  ],
  "forbidden_topic.read": [
    "forbidden_topic.read",
    "forbidden_topic.write",
    "forbidden_topic.manage",
  ],
  "analytics.read": ["analytics.read", "visits.read", "conversations.read"],
  "visits.read": ["visits.read", "conversations.read"],
  "conversations.read": ["conversations.read", "summaries.read", "summaries.write"],
  "summaries.write": ["summaries.write", "conversations.write"],
  "leads.read": ["leads.read", "leads.write"],
  "leads.write": ["leads.write"],
  "exports.read": ["visits.read", "leads.read", "conversations.read"],
  "knowledge.review": ["knowledge.review", "knowledge.write", "knowledge.publish"],
  "knowledge.publish": ["knowledge.publish", "knowledge.review"],
  "privacy.manage": ["privacy.manage"],
  "members.manage": ["members.manage", "members.write", "company.manage"],
};

export function hasPermission(
  user: AdminUser | undefined,
  permission?: string,
  options: { allowCardOwner?: boolean } = {},
): boolean {
  if (!permission) return true;
  if (!user) return false;
  const platformPermission = permission.startsWith("platform.");
  if (platformPermission) return user.role === PLATFORM_ROLE;
  if (user.role === PLATFORM_ROLE) return false;
  if (user.role === "company_admin") return true;
  if (options.allowCardOwner && user.role === "card_owner") return true;
  const granted = new Set(user.permissions);
  if (granted.has("*") || granted.has("admin:*")) return true;
  return (permissionAliases[permission] ?? [permission]).some((value) =>
    granted.has(value),
  );
}

export function adminWorkspaceForUser(
  user: AdminUser | undefined,
): AdminWorkspace | undefined {
  if (!user?.role) return undefined;
  return user.role === PLATFORM_ROLE ? "platform" : "enterprise";
}

export function canAccessAdminWorkspace(
  user: AdminUser | undefined,
  workspace: AdminWorkspace,
): boolean {
  return adminWorkspaceForUser(user) === workspace;
}

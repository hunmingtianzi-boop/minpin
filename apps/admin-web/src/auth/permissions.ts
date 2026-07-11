import type { AdminUser } from "../api/types";

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
  "knowledge.review": ["knowledge.review", "knowledge.write", "knowledge.publish"],
  "knowledge.publish": ["knowledge.publish", "knowledge.review"],
  "privacy.manage": ["privacy.manage"],
};

export function hasPermission(
  user: AdminUser | undefined,
  permission?: string,
  options: { allowCardOwner?: boolean } = {},
): boolean {
  if (!permission) return true;
  if (!user) return false;
  if (user.role === "company_admin" || user.role === "platform_admin") return true;
  if (options.allowCardOwner && user.role === "card_owner") return true;
  const granted = new Set(user.permissions);
  if (granted.has("*") || granted.has("admin:*")) return true;
  return (permissionAliases[permission] ?? [permission]).some((value) =>
    granted.has(value),
  );
}

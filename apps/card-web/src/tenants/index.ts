import type { EnterpriseCardConfig } from "../domain/card";
import { templateTenant } from "./template/tenant";
import { tuotuTenant } from "./tuotu/tenant";

export const tenantRegistry = {
  template: templateTenant,
  tuotu: tuotuTenant,
} satisfies Record<string, EnterpriseCardConfig>;

export type TenantSlug = keyof typeof tenantRegistry;

const normalizeSlug = (value: string | null | undefined) =>
  value?.trim().toLocaleLowerCase("en-US") ?? "";

const isTenantSlug = (slug: string): slug is TenantSlug =>
  Object.prototype.hasOwnProperty.call(tenantRegistry, slug);

export function resolveTenantSlug(
  location: Pick<Location, "pathname" | "search">,
): TenantSlug | undefined {
  const pathMatch = location.pathname.match(/(?:^|\/)c\/([^/?#]+)/i);
  const pathSlug = normalizeSlug(pathMatch?.[1]);
  const querySlug = normalizeSlug(new URLSearchParams(location.search).get("tenant"));
  const configuredSlug = normalizeSlug(import.meta.env.VITE_DEFAULT_TENANT);
  const requestedSlug = pathSlug || querySlug || configuredSlug;

  if (requestedSlug) {
    return isTenantSlug(requestedSlug) ? requestedSlug : undefined;
  }

  return "template";
}

export function getTenant(
  slug: string | null | undefined,
): EnterpriseCardConfig | undefined {
  return slug && isTenantSlug(slug) ? tenantRegistry[slug] : undefined;
}

export { defineTenant } from "./defineTenant";
export { templateTenant } from "./template/tenant";
export { tuotuTenant } from "./tuotu/tenant";

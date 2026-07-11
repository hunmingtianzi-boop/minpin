import type { EnterpriseCardConfig } from "../domain/card";

const tenantLoaders = {
  template: () => import("./template/tenant").then((module) => module.templateTenant),
  tuotu: () => import("./tuotu/tenant").then((module) => module.tuotuTenant),
} satisfies Record<string, () => Promise<EnterpriseCardConfig>>;

export const registeredTenantSlugs = Object.freeze(Object.keys(tenantLoaders));
export type TenantSlug = keyof typeof tenantLoaders;

const normalizeSlug = (value: string | null | undefined) =>
  value?.trim().toLocaleLowerCase("en-US") ?? "";

const isTenantSlug = (slug: string): slug is TenantSlug =>
  Object.prototype.hasOwnProperty.call(tenantLoaders, slug);

const isSafeRuntimeSlug = (slug: string) =>
  /^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$/.test(slug);

export function resolveTenantSlug(
  location: Pick<Location, "pathname" | "search">,
): string | undefined {
  const pathMatch = location.pathname.match(/(?:^|\/)c\/([^/?#]+)/i);
  const pathSlug = normalizeSlug(pathMatch?.[1]);
  const querySlug = normalizeSlug(new URLSearchParams(location.search).get("tenant"));
  const configuredSlug = normalizeSlug(import.meta.env.VITE_DEFAULT_TENANT);
  const requestedSlug = pathSlug || querySlug || configuredSlug;

  if (requestedSlug) {
    return isSafeRuntimeSlug(requestedSlug) ? requestedSlug : undefined;
  }

  return "template";
}

export async function loadTenant(
  slug: string | null | undefined,
): Promise<EnterpriseCardConfig | undefined> {
  return slug && isTenantSlug(slug) ? tenantLoaders[slug]() : undefined;
}

export { defineTenant } from "./defineTenant";

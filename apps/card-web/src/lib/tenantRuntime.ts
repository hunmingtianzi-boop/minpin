import type { EnterpriseCardConfig, ThemeTokens } from "../domain/card";

type ThemeMode = "system" | "light" | "dark";

const tokenNames: Record<keyof ThemeTokens, string> = {
  accent: "accent",
  accentStrong: "accent-strong",
  accentSoft: "accent-soft",
  background: "bg",
  surface: "surface",
  surfaceRaised: "surface-raised",
  surfaceMuted: "surface-muted",
  text: "text",
  textSoft: "text-soft",
  textFaint: "text-faint",
  line: "line",
  lineStrong: "line-strong",
  shadow: "shadow",
};

function upsertMeta(selector: string, attribute: "name" | "property", value: string) {
  let meta = document.head.querySelector<HTMLMetaElement>(selector);
  if (!meta) {
    meta = document.createElement("meta");
    meta.setAttribute(attribute, selector.match(/["'](.+)["']/)?.[1] ?? "");
    document.head.append(meta);
  }
  meta.content = value;
}

function applyModeTokens(mode: "light" | "dark", tokens: ThemeTokens) {
  const root = document.documentElement;
  for (const [key, value] of Object.entries(tokens) as [keyof ThemeTokens, string][]) {
    root.style.setProperty(`--tenant-${tokenNames[key]}-${mode}`, value);
  }
}

export const getThemeStorageKey = (tenantId: string) => `cf-card-theme:${tenantId}`;

function getSelectedTheme(tenant: EnterpriseCardConfig): ThemeMode {
  const saved = window.localStorage.getItem(getThemeStorageKey(tenant.id));
  return saved === "system" || saved === "light" || saved === "dark"
    ? saved
    : tenant.theme.defaultMode;
}

function resolveTheme(mode: ThemeMode): "light" | "dark" {
  return mode === "system"
    ? window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light"
    : mode;
}

function applyInitialTheme(tenant: EnterpriseCardConfig) {
  const resolved = resolveTheme(getSelectedTheme(tenant));
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
  upsertMeta(
    'meta[name="theme-color"]',
    "name",
    resolved === "dark" ? tenant.theme.dark.background : tenant.theme.light.background,
  );
}

export function applyTenantRuntime(tenant: EnterpriseCardConfig) {
  const root = document.documentElement;
  root.dataset.tenant = tenant.id;
  document.title = tenant.seo.title;

  upsertMeta('meta[name="description"]', "name", tenant.seo.description);
  upsertMeta('meta[property="og:title"]', "property", tenant.seo.title);
  upsertMeta('meta[property="og:description"]', "property", tenant.seo.description);
  applyModeTokens("light", tenant.theme.light);
  applyModeTokens("dark", tenant.theme.dark);
  root.style.setProperty("--tenant-action", tenant.theme.action);
  root.style.setProperty("--tenant-on-action", tenant.theme.onAction);
  root.style.setProperty("--tenant-radius-card", tenant.theme.radiusCard);
  root.style.setProperty("--tenant-radius-control", tenant.theme.radiusControl);
  root.style.setProperty("--tenant-radius-small", tenant.theme.radiusSmall);
  root.style.setProperty("--tenant-hero-light", tenant.theme.light.background);
  root.style.setProperty("--tenant-hero-dark", tenant.theme.dark.background);
  root.style.setProperty(
    "--tenant-hero-overlay-light",
    tenant.theme.heroOverlay.light,
  );
  root.style.setProperty(
    "--tenant-hero-overlay-dark",
    tenant.theme.heroOverlay.dark,
  );

  let favicon = document.head.querySelector<HTMLLinkElement>('link[data-tenant-asset="icon"]');
  if (!favicon) {
    favicon = document.createElement("link");
    favicon.rel = "icon";
    favicon.type = tenant.brand.logo.src.endsWith(".webp")
      ? "image/webp"
      : "image/png";
    favicon.dataset.tenantAsset = "icon";
    favicon.href = tenant.brand.logo.src;
    document.head.append(favicon);
  } else {
    favicon.href = tenant.brand.logo.src;
    favicon.type = tenant.brand.logo.src.endsWith(".webp")
      ? "image/webp"
      : "image/png";
  }

  let heroPreload = document.head.querySelector<HTMLLinkElement>(
    'link[data-tenant-asset="hero"]',
  );
  if (!heroPreload) {
    heroPreload = document.createElement("link");
    heroPreload.rel = "preload";
    heroPreload.as = "image";
    heroPreload.dataset.tenantAsset = "hero";
    heroPreload.href = tenant.hero.art.src;
    document.head.append(heroPreload);
  } else {
    heroPreload.href = tenant.hero.art.src;
  }

  applyInitialTheme(tenant);
}

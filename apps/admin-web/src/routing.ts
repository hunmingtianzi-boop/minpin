import { useSyncExternalStore } from "react";

export const APP_PATHS = {
  overview: "/",
  visits: "/visits",
  visitorProfiles: "/visitor-profiles",
  conversations: "/conversations",
  opportunities: "/opportunities",
  leads: "/leads",
  exports: "/exports",
  knowledgeGaps: "/knowledge-gaps",
  notifications: "/notifications",
  privacyRequests: "/privacy-requests",
  company: "/company",
  members: "/members",
  card: "/card",
  cards: "/cards",
  products: "/products",
  cases: "/cases",
  forbiddenTopics: "/forbidden-topics",
  knowledge: "/knowledge",
  platformOverview: "/platform",
  platformEnterprises: "/platform/enterprises",
} as const;

export type AppPath = (typeof APP_PATHS)[keyof typeof APP_PATHS];

const knownPaths = new Set<string>(Object.values(APP_PATHS));

function normalizeBasePath(value: string): string {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "/") return "/";
  return `/${trimmed.replace(/^\/+|\/+$/g, "")}/`;
}

export const APP_BASE_PATH = normalizeBasePath(import.meta.env.BASE_URL);

export function appHref(path: string): string {
  if (APP_BASE_PATH === "/") return path;
  if (path === "/") return APP_BASE_PATH;
  return `${APP_BASE_PATH.slice(0, -1)}${path}`;
}

export function appPathFromBrowser(pathname: string): string {
  if (APP_BASE_PATH === "/") return pathname;
  const baseWithoutSlash = APP_BASE_PATH.slice(0, -1);
  if (pathname === baseWithoutSlash || pathname === APP_BASE_PATH) return "/";
  if (!pathname.startsWith(APP_BASE_PATH)) return pathname;
  return `/${pathname.slice(APP_BASE_PATH.length)}`;
}

function subscribe(callback: () => void) {
  window.addEventListener("popstate", callback);
  return () => window.removeEventListener("popstate", callback);
}

function snapshot() {
  return appPathFromBrowser(window.location.pathname);
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, snapshot, () => APP_PATHS.overview);
}

export function isAppPath(path: string): path is AppPath {
  return knownPaths.has(path);
}

export function navigate(path: AppPath): void {
  const browserPath = appHref(path);
  if (window.location.pathname === browserPath) return;
  window.history.pushState({}, "", browserPath);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function onInternalLinkClick(
  event: React.MouseEvent<HTMLAnchorElement>,
  path: AppPath,
): void {
  if (
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey
  ) {
    return;
  }
  event.preventDefault();
  navigate(path);
}

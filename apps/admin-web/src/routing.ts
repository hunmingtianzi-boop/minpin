import { useSyncExternalStore } from "react";

export const APP_PATHS = {
  overview: "/",
  visits: "/visits",
  visitorProfiles: "/visitor-profiles",
  conversations: "/conversations",
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

function subscribe(callback: () => void) {
  window.addEventListener("popstate", callback);
  return () => window.removeEventListener("popstate", callback);
}

function snapshot() {
  return window.location.pathname;
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, snapshot, () => APP_PATHS.overview);
}

export function isAppPath(path: string): path is AppPath {
  return knownPaths.has(path);
}

export function navigate(path: AppPath): void {
  if (window.location.pathname === path) return;
  window.history.pushState({}, "", path);
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

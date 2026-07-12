const PROFILE_LINK_PREFIX = "cf-card-profile-link:";
const PROFILE_REVOKE_PENDING_PREFIX = "cf-card-profile-revoke-pending:";

function localStorageOrUndefined() {
  try {
    return globalThis.localStorage;
  } catch {
    return undefined;
  }
}

function sessionStorageOrUndefined() {
  try {
    return globalThis.sessionStorage;
  } catch {
    return undefined;
  }
}

export function getProfileLinkStorageKey(companyId: string) {
  return `${PROFILE_LINK_PREFIX}${companyId.trim()}`;
}

export function getProfileRevokePendingStorageKey(companyId: string) {
  return `${PROFILE_REVOKE_PENDING_PREFIX}${companyId.trim()}`;
}

export function readProfileRevokePending(companyId: string) {
  if (!companyId.trim()) return false;
  const key = getProfileRevokePendingStorageKey(companyId);
  try {
    if (sessionStorageOrUndefined()?.getItem(key) === "1") return true;
  } catch {
    // Fall back to a token-free marker in local storage.
  }
  try {
    return localStorageOrUndefined()?.getItem(key) === "1";
  } catch {
    return false;
  }
}

export function markProfileRevokePending(companyId: string) {
  if (!companyId.trim()) return false;
  const key = getProfileRevokePendingStorageKey(companyId);
  for (const storage of [sessionStorageOrUndefined(), localStorageOrUndefined()]) {
    try {
      if (!storage) continue;
      storage.setItem(key, "1");
      if (storage.getItem(key) === "1") return true;
    } catch {
      // Try the next storage. Neither marker contains the profile link token.
    }
  }
  return false;
}

export function clearProfileRevokePending(companyId: string) {
  if (!companyId.trim()) return;
  const key = getProfileRevokePendingStorageKey(companyId);
  for (const storage of [sessionStorageOrUndefined(), localStorageOrUndefined()]) {
    try {
      storage?.removeItem(key);
    } catch {
      // A stale marker only causes another safe, explicit revocation attempt.
    }
  }
}

export function readProfileLinkToken(companyId: string) {
  if (!companyId.trim()) return undefined;
  try {
    const value = localStorageOrUndefined()?.getItem(getProfileLinkStorageKey(companyId));
    return value?.trim() || undefined;
  } catch {
    return undefined;
  }
}

export function canPersistProfileLink() {
  const storage = localStorageOrUndefined();
  if (!storage) return false;
  const probe = `${PROFILE_LINK_PREFIX}storage-probe`;
  try {
    storage.setItem(probe, "1");
    storage.removeItem(probe);
    return true;
  } catch {
    return false;
  }
}

export function writeProfileLinkToken(companyId: string, token: string) {
  if (!companyId.trim() || !token.trim()) return false;
  try {
    const storage = localStorageOrUndefined();
    if (!storage) return false;
    storage.setItem(getProfileLinkStorageKey(companyId), token.trim());
    return storage.getItem(getProfileLinkStorageKey(companyId)) === token.trim();
  } catch {
    return false;
  }
}

export function clearProfileLinkToken(companyId: string) {
  if (!companyId.trim()) return;
  try {
    localStorageOrUndefined()?.removeItem(getProfileLinkStorageKey(companyId));
  } catch {
    // Revocation must remain usable when storage is blocked or disappears.
  }
}

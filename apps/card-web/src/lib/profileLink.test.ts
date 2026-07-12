import { afterEach, describe, expect, it, vi } from "vitest";

import {
  canPersistProfileLink,
  clearProfileLinkToken,
  clearProfileRevokePending,
  getProfileLinkStorageKey,
  getProfileRevokePendingStorageKey,
  markProfileRevokePending,
  readProfileLinkToken,
  readProfileRevokePending,
  writeProfileLinkToken,
} from "./profileLink";

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

describe("profile link storage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("isolates long-lived tokens by company and never uses a card slug key", () => {
    vi.stubGlobal("localStorage", new MemoryStorage());
    vi.stubGlobal("sessionStorage", new MemoryStorage());

    expect(writeProfileLinkToken("company-a", "token-a")).toBe(true);
    expect(writeProfileLinkToken("company-b", "token-b")).toBe(true);
    expect(readProfileLinkToken("company-a")).toBe("token-a");
    expect(readProfileLinkToken("company-b")).toBe("token-b");
    expect(getProfileLinkStorageKey("company-a")).toBe(
      "cf-card-profile-link:company-a",
    );

    clearProfileLinkToken("company-a");
    expect(readProfileLinkToken("company-a")).toBeUndefined();
    expect(readProfileLinkToken("company-b")).toBe("token-b");
  });

  it("persists token-free pending revocations in session storage and isolates companies", () => {
    const local = new MemoryStorage();
    const session = new MemoryStorage();
    vi.stubGlobal("localStorage", local);
    vi.stubGlobal("sessionStorage", session);

    expect(markProfileRevokePending("company-a")).toBe(true);
    expect(readProfileRevokePending("company-a")).toBe(true);
    expect(readProfileRevokePending("company-b")).toBe(false);
    expect(session.getItem(getProfileRevokePendingStorageKey("company-a"))).toBe("1");
    expect(local.getItem(getProfileRevokePendingStorageKey("company-a"))).toBeNull();

    markProfileRevokePending("company-b");
    clearProfileRevokePending("company-a");
    expect(readProfileRevokePending("company-a")).toBe(false);
    expect(readProfileRevokePending("company-b")).toBe(true);
  });

  it("fails closed when browser storage is unavailable", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => { throw new DOMException("blocked", "SecurityError"); },
      setItem: () => { throw new DOMException("blocked", "SecurityError"); },
      removeItem: () => { throw new DOMException("blocked", "SecurityError"); },
    });
    vi.stubGlobal("sessionStorage", {
      getItem: () => { throw new DOMException("blocked", "SecurityError"); },
      setItem: () => { throw new DOMException("blocked", "SecurityError"); },
      removeItem: () => { throw new DOMException("blocked", "SecurityError"); },
    });

    expect(canPersistProfileLink()).toBe(false);
    expect(writeProfileLinkToken("company-a", "token-a")).toBe(false);
    expect(readProfileLinkToken("company-a")).toBeUndefined();
    expect(() => clearProfileLinkToken("company-a")).not.toThrow();
    expect(markProfileRevokePending("company-a")).toBe(false);
    expect(readProfileRevokePending("company-a")).toBe(false);
  });
});

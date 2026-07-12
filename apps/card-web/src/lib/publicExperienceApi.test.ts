import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getAssistantSessionStorageKey } from "./assistantApi";
import {
  getProfileLinkStorageKey,
  getProfileRevokePendingStorageKey,
} from "./profileLink";
import {
  fetchPublicCaseStudy,
  fetchPublicCatalog,
  fetchPublicProduct,
  safeContactHref,
  setProfilePersonalizationConsent,
  submitPrivacyRequest,
  submitPublicLead,
} from "./publicExperienceApi";

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length() {
    return this.values.size;
  }

  clear() {
    this.values.clear();
  }

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  key(index: number) {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string) {
    this.values.delete(key);
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

const policies = {
  privacy: "privacy-v4",
  chatNotice: "chat-v3",
  leadConsent: "lead-v7",
  profilePersonalization: "profile-v2",
};

function jsonResponse(data: unknown, status = 200, headers?: HeadersInit) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function visitResponse(token: string) {
  return jsonResponse(
    {
      data: {
        visit_id: `visit-${token}`,
        visitor_session_token: token,
        expires_at: "2099-01-01T00:00:00Z",
      },
    },
    201,
  );
}

describe("public experience API", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1/");
    vi.stubGlobal("sessionStorage", new MemoryStorage());
    vi.stubGlobal("localStorage", new MemoryStorage());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads public product and case lists plus their detail endpoints", async () => {
    const product = {
      slug: "data-service",
      name: "数据服务",
      category: "企业服务",
      summary: "整理业务数据",
      detail: "提供数据治理和分析支持。",
      audience: "成长型企业",
      price_boundary: "按项目评估",
      image_url: null,
      sort_order: 1,
      published_at: "2026-07-11T00:00:00Z",
    };
    const caseStudy = {
      slug: "retail-growth",
      title: "零售增长案例",
      industry: "零售",
      background: "客户需要统一经营数据。",
      solution: "建设统一数据看板。",
      result: "决策效率得到提升。",
      client_display_name: "某零售企业",
      image_url: null,
      sort_order: 2,
      published_at: "2026-07-10T00:00:00Z",
    };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ data: [product], total: 1, limit: 50, offset: 0 }))
      .mockResolvedValueOnce(jsonResponse({ data: [caseStudy], total: 1, limit: 50, offset: 0 }))
      .mockResolvedValueOnce(jsonResponse({ data: product }))
      .mockResolvedValueOnce(jsonResponse({ data: caseStudy }));
    vi.stubGlobal("fetch", fetchMock);

    const catalog = await fetchPublicCatalog("tenant-a");
    const productDetail = await fetchPublicProduct("tenant-a", "data-service");
    const caseDetail = await fetchPublicCaseStudy("tenant-a", "retail-growth");

    expect(catalog.products[0]).toMatchObject({
      slug: "data-service",
      priceBoundary: "按项目评估",
    });
    expect(catalog.cases[0]).toMatchObject({
      slug: "retail-growth",
      clientDisplayName: "某零售企业",
    });
    expect(productDetail.detail).toContain("数据治理");
    expect(caseDetail.result).toContain("提升");
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "https://api.example.test/api/v1/public/cards/tenant-a/products?limit=50&offset=0",
      "https://api.example.test/api/v1/public/cards/tenant-a/case-studies?limit=50&offset=0",
      "https://api.example.test/api/v1/public/cards/tenant-a/products/data-service",
      "https://api.example.test/api/v1/public/cards/tenant-a/case-studies/retail-growth",
    ]);
  });

  it("records current lead consent before creating a lead with separate stable keys", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(visitResponse("visitor-token"))
      .mockResolvedValueOnce(jsonResponse({ data: { id: "consent-1" } }, 201))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            data: {
              id: "lead-1",
              status: "new",
              created_at: "2026-07-11T01:00:00Z",
            },
          },
          201,
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    const result = await submitPublicLead({
      cardSlug: "tenant-a",
      policyVersions: policies,
      input: {
        conversationId: "33333333-3333-3333-3333-333333333333",
        name: "张三",
        mobile: "13800138000",
        companyName: "示例企业",
        demand: "希望进一步沟通。",
      },
      consentIdempotencyKey: "consent-key-0001",
      leadIdempotencyKey: "lead-key-00000001",
    });

    expect(result.id).toBe("lead-1");
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "https://api.example.test/api/v1/public/cards/tenant-a/visits",
      "https://api.example.test/api/v1/public/cards/tenant-a/consents",
      "https://api.example.test/api/v1/public/cards/tenant-a/leads",
    ]);
    const consent = fetchMock.mock.calls[1][1]!;
    expect(consent.headers).toMatchObject({
      Authorization: "Bearer visitor-token",
      "Idempotency-Key": "consent-key-0001",
    });
    expect(JSON.parse(String(consent.body))).toEqual({
      scope: "lead_contact",
      policy_version: "lead-v7",
      granted: true,
    });
    const lead = fetchMock.mock.calls[2][1]!;
    expect(lead.headers).toMatchObject({
      Authorization: "Bearer visitor-token",
      "Idempotency-Key": "lead-key-00000001",
    });
    expect(JSON.parse(String(lead.body))).toMatchObject({
      name: "张三",
      mobile: "13800138000",
      conversation_id: "33333333-3333-3333-3333-333333333333",
      consent_policy_version: "lead-v7",
      consent_granted: true,
    });
  });

  it("recreates an expired or rejected visitor session and repeats consent before lead", async () => {
    sessionStorage.setItem(
      getAssistantSessionStorageKey("tenant-a"),
      JSON.stringify({
        token: "expired-token",
        expiresAt: "2020-01-01T00:00:00Z",
        privacyVersion: "privacy-v1",
        chatNoticeVersion: "chat-v1",
      }),
    );
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(visitResponse("visitor-token-1"))
      .mockResolvedValueOnce(jsonResponse({ data: { id: "consent-1" } }, 201))
      .mockResolvedValueOnce(
        jsonResponse(
          { error: { code: "TOKEN_EXPIRED", message: "会话已失效" } },
          401,
        ),
      )
      .mockResolvedValueOnce(visitResponse("visitor-token-2"))
      .mockResolvedValueOnce(jsonResponse({ data: { id: "consent-2" } }, 201))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            data: {
              id: "lead-2",
              status: "new",
              created_at: "2026-07-11T02:00:00Z",
            },
          },
          201,
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      submitPublicLead({
        cardSlug: "tenant-a",
        policyVersions: policies,
        input: {
          conversationId: "44444444-4444-4444-4444-444444444444",
          name: "李四",
          email: "li@example.test",
          demand: "需要方案。",
        },
        consentIdempotencyKey: "consent-key-0002",
        leadIdempotencyKey: "lead-key-00000002",
      }),
    ).resolves.toMatchObject({ id: "lead-2" });

    expect(fetchMock).toHaveBeenCalledTimes(6);
    expect(fetchMock.mock.calls[4][1]?.headers).toMatchObject({
      Authorization: "Bearer visitor-token-2",
      "Idempotency-Key": "consent-key-0002",
    });
    expect(fetchMock.mock.calls[5][1]?.headers).toMatchObject({
      Authorization: "Bearer visitor-token-2",
      "Idempotency-Key": "lead-key-00000002",
    });
    expect(JSON.parse(String(fetchMock.mock.calls[5][1]?.body))).not.toHaveProperty(
      "conversation_id",
    );
  });

  it("surfaces a stale consent policy and never sends the lead request", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(visitResponse("visitor-token"))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error: {
              code: "POLICY_VERSION_MISMATCH",
              message: "授权告知已更新",
            },
          },
          409,
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      submitPublicLead({
        cardSlug: "tenant-a",
        policyVersions: policies,
        input: { name: "王五", wechat: "wangwu", demand: "预约演示。" },
        consentIdempotencyKey: "consent-key-0003",
        leadIdempotencyKey: "lead-key-00000003",
      }),
    ).rejects.toMatchObject({ code: "POLICY_VERSION_MISMATCH", status: 409 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("submits a privacy request using the shared visitor session", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(visitResponse("visitor-token"))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            data: {
              id: "privacy-1",
              visitor_id: "visitor-1",
              request_type: "withdraw_consent",
              status: "pending",
              created_at: "2026-07-11T03:00:00Z",
              updated_at: "2026-07-11T03:00:00Z",
            },
          },
          201,
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    const result = await submitPrivacyRequest({
      cardSlug: "tenant-a",
      policyVersions: policies,
      input: {
        requestType: "withdraw_consent",
        consentScope: "lead_contact",
        note: "不再需要联系",
      },
      idempotencyKey: "privacy-key-0001",
    });

    expect(result).toMatchObject({ id: "privacy-1", status: "pending" });
    const request = fetchMock.mock.calls[1][1]!;
    expect(request.headers).toMatchObject({
      Authorization: "Bearer visitor-token",
      "Idempotency-Key": "privacy-key-0001",
    });
    expect(JSON.parse(String(request.body))).toEqual({
      request_type: "withdraw_consent",
      note: "不再需要联系",
      consent_scope: "lead_contact",
    });
  });

  it("grants profile personalization and persists only the company-scoped link token", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(visitResponse("visitor-session-token"))
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            id: "consent-1",
            scope: "profile_personalization",
            policy_version: "profile-v2",
            granted: true,
            recorded_at: "2026-07-12T01:00:00Z",
            profile_link_token: "long-lived-company-token",
          },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      setProfilePersonalizationConsent({
        cardSlug: "tenant-a",
        companyId: "company-a",
        policyVersions: policies,
        granted: true,
        idempotencyKey: "profile-consent-key-1",
      }),
    ).resolves.toEqual({
      granted: true,
      recordedAt: "2026-07-12T01:00:00Z",
    });

    expect(localStorage.getItem(getProfileLinkStorageKey("company-a"))).toBe(
      "long-lived-company-token",
    );
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      scope: "profile_personalization",
      policy_version: "profile-v2",
      granted: true,
    });
    expect(localStorage.getItem(getProfileLinkStorageKey("tenant-a"))).toBeNull();
    expect(localStorage.getItem(getAssistantSessionStorageKey("tenant-a"))).toBeNull();
  });

  it("removes the local profile link immediately even when server revocation fails", async () => {
    localStorage.setItem(getProfileLinkStorageKey("company-a"), "long-lived-token");
    sessionStorage.setItem(
      getAssistantSessionStorageKey("tenant-a"),
      JSON.stringify({
        token: "visitor-session-token",
        expiresAt: "2099-01-01T00:00:00Z",
        privacyVersion: policies.privacy,
        chatNoticeVersion: policies.chatNotice,
      }),
    );
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline")));

    await expect(
      setProfilePersonalizationConsent({
        cardSlug: "tenant-a",
        companyId: "company-a",
        policyVersions: policies,
        granted: false,
        idempotencyKey: "profile-consent-key-2",
      }),
    ).rejects.toMatchObject({ code: "PROFILE_REVOKE_PENDING", retryable: true });
    expect(localStorage.getItem(getProfileLinkStorageKey("company-a"))).toBeNull();
    expect(sessionStorage.getItem(getProfileRevokePendingStorageKey("company-a"))).toBe("1");
  });

  it("surfaces failed grant compensation and clears the company pending marker after retry", async () => {
    const backing = new MemoryStorage();
    let profileTokenWrites = 0;
    vi.stubGlobal("localStorage", {
      get length() { return backing.length; },
      clear: () => backing.clear(),
      getItem: (key: string) => backing.getItem(key),
      key: (index: number) => backing.key(index),
      removeItem: (key: string) => backing.removeItem(key),
      setItem: (key: string, value: string) => {
        if (key === getProfileLinkStorageKey("company-a")) {
          profileTokenWrites += 1;
          throw new DOMException("quota", "QuotaExceededError");
        }
        backing.setItem(key, value);
      },
    } satisfies Storage);
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(visitResponse("visitor-session-token"))
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            granted: true,
            recorded_at: "2026-07-12T01:00:00Z",
            profile_link_token: "server-issued-token",
          },
        }),
      )
      .mockRejectedValueOnce(new TypeError("offline during compensation"))
      .mockResolvedValueOnce(
        jsonResponse({
          data: { granted: false, recorded_at: "2026-07-12T01:05:00Z" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      setProfilePersonalizationConsent({
        cardSlug: "tenant-a",
        companyId: "company-a",
        policyVersions: policies,
        granted: true,
        idempotencyKey: "profile-grant-key",
      }),
    ).rejects.toMatchObject({ code: "PROFILE_REVOKE_PENDING", retryable: true });
    expect(profileTokenWrites).toBe(1);
    expect(sessionStorage.getItem(getProfileRevokePendingStorageKey("company-a"))).toBe("1");
    expect(sessionStorage.getItem(getProfileRevokePendingStorageKey("company-b"))).toBeNull();

    await expect(
      setProfilePersonalizationConsent({
        cardSlug: "tenant-a",
        companyId: "company-a",
        policyVersions: policies,
        granted: false,
        idempotencyKey: "profile-revoke-retry-key",
      }),
    ).resolves.toEqual({
      granted: false,
      recordedAt: "2026-07-12T01:05:00Z",
    });
    expect(sessionStorage.getItem(getProfileRevokePendingStorageKey("company-a"))).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("rejects unsafe contact protocols while inferring safe phone and mail links", () => {
    expect(safeContactHref({ label: "官网", value: "点击", href: "javascript:alert(1)" })).toBeUndefined();
    expect(safeContactHref({ label: "邮箱", value: "hello@example.com" })).toBe(
      "mailto:hello@example.com",
    );
    expect(safeContactHref({ label: "电话", value: "+86 138-0013-8000" })).toBe(
      "tel:+8613800138000",
    );
  });
});

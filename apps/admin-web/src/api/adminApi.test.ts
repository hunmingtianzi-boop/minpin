import { describe, expect, it, vi } from "vitest";

import { createAdminApi } from "./adminApi";
import { ApiClient } from "./client";

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function authenticatedApi(fetcher: ReturnType<typeof vi.fn<typeof fetch>>) {
  const client = new ApiClient({
    baseUrl: "https://api.example.test/api/v1",
    fetcher,
  });
  await client.login("admin@example.test", "password");
  return createAdminApi(client);
}

function tokenResponse() {
  return jsonResponse({
    data: {
      access_token: "access-token",
      csrf_token: "csrf-token",
      token_type: "bearer",
      expires_in: 900,
      refresh_expires_in: 604800,
    },
  });
}

describe("adminApi real contract", () => {
  it("reads the nested current-user contract", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            user: { id: "user-1", display_name: "林顾问" },
            membership: {
              id: "membership-1",
              tenant_id: "tenant-1",
              company_id: "company-1",
              role: "company_admin",
              permissions: ["company.profile.read"],
            },
          },
        }),
      );
    const api = await authenticatedApi(fetcher);

    await expect(api.me()).resolves.toEqual({
      id: "user-1",
      displayName: "林顾问",
      membershipId: "membership-1",
      tenantId: "tenant-1",
      companyId: "company-1",
      role: "company_admin",
      permissions: ["company.profile.read"],
    });
  });

  it("sends only allowed company and card fields with If-Match", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({ data: {} }))
      .mockResolvedValueOnce(jsonResponse({ data: {} }));
    const api = await authenticatedApi(fetcher);

    await api.updateCompanyProfile({
      name: "创非凡",
      summary: "企业简介",
      industry: "企业服务",
      region: "杭州",
      website: "https://example.test",
      logoUrl: "",
      version: 7,
    });
    await api.updateCard({
      slug: "lin-advisor",
      displayName: "林顾问",
      title: "解决方案顾问",
      avatarUrl: "",
      assistantName: "企业助手",
      welcomeMessage: "欢迎咨询",
      suggestedQuestions: ["你们提供什么服务？"],
      policyVersions: {
        privacy: "privacy-v2",
        chatNotice: "",
        leadConsent: "",
      },
      version: 4,
    });

    const companyRequest = fetcher.mock.calls[1];
    expect(companyRequest[0]).toBe(
      "https://api.example.test/api/v1/admin/company/profile",
    );
    expect((companyRequest[1]?.headers as Headers).get("If-Match")).toBe("7");
    expect(JSON.parse(String(companyRequest[1]?.body))).toEqual({
      name: "创非凡",
      summary: "企业简介",
      industry: "企业服务",
      region: "杭州",
      website: "https://example.test",
      logo_url: null,
    });

    const cardRequest = fetcher.mock.calls[2];
    expect((cardRequest[1]?.headers as Headers).get("If-Match")).toBe("4");
    expect(JSON.parse(String(cardRequest[1]?.body))).toEqual({
      slug: "lin-advisor",
      display_name: "林顾问",
      title: "解决方案顾问",
      avatar_url: null,
      assistant_name: "企业助手",
      welcome_message: "欢迎咨询",
      suggested_questions: ["你们提供什么服务？"],
      policy_versions: { privacy: "privacy-v2" },
    });
  });

  it("loads detail before editing and uses the two-stage FAQ create flow", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            id: "document-1",
            title: "交付周期",
            status: "draft",
            version: 2,
            latest_version: null,
            updated_at: "2026-07-11T00:00:00Z",
            raw_text: "通常需要四周。",
            visibility: "public",
            metadata: { source_label: "企业后台" },
            editable_version_id: "version-1",
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          data: {
            id: "document-2",
            title: "付款方式",
            status: "draft",
            version: 1,
          },
        }, 201),
      )
      .mockResolvedValueOnce(jsonResponse({ data: { document: {}, draft_version: {} } }))
      .mockResolvedValueOnce(jsonResponse({ data: { index_status: "pending" } }));
    const api = await authenticatedApi(fetcher);

    await expect(api.getKnowledgeDocument("document-1")).resolves.toMatchObject({
      rawText: "通常需要四周。",
      visibility: "public",
      metadata: { source_label: "企业后台" },
      editableVersionId: "version-1",
    });
    const createdId = await api.createKnowledgeDocument("付款方式");
    await api.updateKnowledgeDocument(createdId, {
      title: "付款方式",
      answer: "以合同约定为准。",
      visibility: "public",
      metadata: { source_label: "企业后台" },
    });
    await api.publishKnowledgeDocument(createdId);

    expect(createdId).toBe("document-2");
    expect(JSON.parse(String(fetcher.mock.calls[2][1]?.body))).toEqual({
      title: "付款方式",
      source_type: "faq",
    });
    expect(JSON.parse(String(fetcher.mock.calls[3][1]?.body))).toEqual({
      raw_text: "以合同约定为准。",
      title: "付款方式",
      visibility: "public",
      metadata: { source_label: "企业后台" },
    });
    expect(JSON.parse(String(fetcher.mock.calls[4][1]?.body))).toEqual({});
  });

  it("normalizes catalog resources and protects lifecycle mutations with If-Match", async () => {
    const product = {
      id: "product-1",
      slug: "enterprise-ai",
      name: "企业 AI 助手",
      summary: "可追溯问答",
      detail: "产品详情",
      visibility: "public",
      status: "draft",
      version: 3,
      sort_order: 0,
      settings: {},
    };
    const card = {
      id: "card-1",
      owner_user_id: "user-1",
      slug: "c-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      display_name: "林顾问",
      title: "解决方案顾问",
      status: "published",
      version: 8,
      share_url: "https://cards.example.test/c/card-1",
      qr_url: "https://cards.example.test/c/card-1",
    };
    const forbiddenTopic = {
      id: "topic-1",
      topic: "价格承诺",
      match_terms: ["最低价"],
      action: "refuse",
      is_active: true,
      version: 2,
    };
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse({ data: [product] }))
      .mockResolvedValueOnce(
        jsonResponse({ data: { ...product, status: "published", version: 4 } }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: [card] }))
      .mockResolvedValueOnce(
        jsonResponse({ data: { ...card, status: "archived", version: 9 } }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: [forbiddenTopic] }))
      .mockResolvedValueOnce(
        jsonResponse({ data: { ...forbiddenTopic, is_active: false, version: 3 } }),
      );
    const api = await authenticatedApi(fetcher);

    await expect(api.listProducts()).resolves.toMatchObject([
      { id: "product-1", name: "企业 AI 助手", version: 3 },
    ]);
    await api.publishProduct("product-1", 3);
    await expect(api.listManagedCards()).resolves.toMatchObject([
      { id: "card-1", ownerUserId: "user-1", version: 8 },
    ]);
    await api.deactivateManagedCard("card-1", 8);
    await expect(api.listForbiddenTopics()).resolves.toMatchObject([
      { id: "topic-1", matchTerms: ["最低价"], isActive: true },
    ]);
    await api.setForbiddenTopicActive("topic-1", 2, false);

    expect(fetcher.mock.calls[2][0]).toBe(
      "https://api.example.test/api/v1/admin/products/product-1:publish",
    );
    expect((fetcher.mock.calls[2][1]?.headers as Headers).get("If-Match")).toBe("3");
    expect(fetcher.mock.calls[4][0]).toBe(
      "https://api.example.test/api/v1/admin/cards/card-1:deactivate",
    );
    expect((fetcher.mock.calls[4][1]?.headers as Headers).get("If-Match")).toBe("8");
    expect(fetcher.mock.calls[6][0]).toBe(
      "https://api.example.test/api/v1/admin/forbidden-topics/topic-1/deactivate",
    );
    expect((fetcher.mock.calls[6][1]?.headers as Headers).get("If-Match")).toBe("2");
  });
});

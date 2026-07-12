import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AssistantApiError } from "../lib/assistantApi";
import type { PublicCardData } from "../lib/publicCardApi";
import type { PublicCatalog, PublicProduct } from "../lib/publicExperienceApi";
import { getProfileLinkStorageKey } from "../lib/profileLink";
import { PublicExperience } from "./PublicExperience";

const mocks = vi.hoisted(() => ({
  fetchCatalog: vi.fn(),
  fetchProduct: vi.fn(),
  fetchCase: vi.fn(),
  submitLead: vi.fn(),
  submitPrivacy: vi.fn(),
  setProfileConsent: vi.fn(),
  fetchCard: vi.fn(),
}));

vi.mock("../lib/publicExperienceApi", async () => {
  const actual = await vi.importActual<typeof import("../lib/publicExperienceApi")>(
    "../lib/publicExperienceApi",
  );
  return {
    ...actual,
    isPublicExperienceConfigured: () => true,
    fetchPublicCatalog: mocks.fetchCatalog,
    fetchPublicProduct: mocks.fetchProduct,
    fetchPublicCaseStudy: mocks.fetchCase,
    submitPublicLead: mocks.submitLead,
    submitPrivacyRequest: mocks.submitPrivacy,
    setProfilePersonalizationConsent: mocks.setProfileConsent,
    createPublicIdempotencyKey: vi
      .fn()
      .mockReturnValueOnce("consent-key-0001")
      .mockReturnValueOnce("lead-key-00000001")
      .mockReturnValue("privacy-key-0001"),
  };
});

vi.mock("../lib/publicCardApi", async () => {
  const actual = await vi.importActual<typeof import("../lib/publicCardApi")>(
    "../lib/publicCardApi",
  );
  return { ...actual, fetchPublicCard: mocks.fetchCard };
});

const product: PublicProduct = {
  slug: "data-service",
  name: "数据服务",
  category: "企业服务",
  summary: "帮助企业整理业务数据。",
  detail: "提供数据治理和分析支持。",
  audience: "成长型企业",
  priceBoundary: "按项目评估",
  sortOrder: 1,
  publishedAt: "2026-07-11T00:00:00Z",
};

const emptyCatalog: PublicCatalog = { products: [], cases: [] };

const card: PublicCardData = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "tenant-a",
  display_name: "示例企业",
  title: "示例企业名片",
  contact_fields: [
    { label: "电话", value: "13800138000", href: "tel:13800138000" },
    { label: "微信", value: "example-wechat" },
  ],
  company: {
    id: "22222222-2222-2222-2222-222222222222",
    name: "示例企业",
    summary: "面向企业客户提供可信服务。",
  },
  featured_products: [],
  featured_cases: [],
  faq_items: [],
  ai_assistant: {
    available: true,
    display_name: "示例企业 AI 助手",
    disclosure: "回答由 AI 生成",
    welcome_message: "你好",
    suggested_questions: [],
  },
  policy_versions: {
    privacy: "privacy-v1",
    chat_notice: "chat-v1",
    lead_consent: "lead-v1",
    profile_personalization: "profile-v1",
  },
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function renderExperience() {
  return render(<PublicExperience card={card} onAssistant={vi.fn()} />);
}

async function openAndFillLeadForm() {
  fireEvent.click(screen.getByRole("button", { name: "留下需求" }));
  fireEvent.change(screen.getByLabelText("姓名 *"), { target: { value: "张三" } });
  fireEvent.change(screen.getByLabelText("手机"), { target: { value: "13800138000" } });
  fireEvent.change(screen.getByLabelText("合作需求 *"), {
    target: { value: "希望预约产品演示。" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
}

describe("PublicExperience", () => {
  beforeEach(() => {
    mocks.fetchCatalog.mockReset().mockResolvedValue(emptyCatalog);
    mocks.fetchProduct.mockReset().mockResolvedValue(product);
    mocks.fetchCase.mockReset();
    mocks.submitLead.mockReset();
    mocks.submitPrivacy.mockReset();
    mocks.setProfileConsent.mockReset();
    mocks.setProfileConsent.mockResolvedValue({
      granted: true,
      recordedAt: "2026-07-12T01:00:00Z",
    });
    window.localStorage.clear();
    window.sessionStorage.clear();
    mocks.fetchCard.mockReset().mockResolvedValue(card);
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("offers retry after a catalog error and then renders the empty state", async () => {
    mocks.fetchCatalog
      .mockRejectedValueOnce(new AssistantApiError("网络不可用", { code: "NETWORK_ERROR" }))
      .mockResolvedValueOnce(emptyCatalog);
    renderExperience();

    expect(await screen.findByText("暂时没有读取到业务资料")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));

    expect(await screen.findByText("产品资料正在准备")).toBeInTheDocument();
    expect(mocks.fetchCatalog).toHaveBeenCalledTimes(2);
  });

  it("supports roving keyboard focus across the product and case tabs", async () => {
    renderExperience();
    const productsTab = screen.getByRole("tab", { name: /^产品与服务/ });
    const casesTab = screen.getByRole("tab", { name: /^公开案例/ });

    productsTab.focus();
    fireEvent.keyDown(productsTab, { key: "ArrowRight" });

    await waitFor(() => expect(casesTab).toHaveFocus());
    expect(casesTab).toHaveAttribute("aria-selected", "true");
    expect(casesTab).toHaveAttribute("tabindex", "0");
    expect(productsTab).toHaveAttribute("tabindex", "-1");
  });

  it("closes dialogs with Escape and restores focus to the mobile-sized trigger", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    renderExperience();
    const trigger = screen.getByRole("button", { name: "留下需求" });
    trigger.focus();
    fireEvent.click(trigger);

    expect(await screen.findByRole("dialog", { name: "留下合作需求" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("姓名 *")).toHaveFocus());
    fireEvent.keyDown(window, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("opens a product from the public list and fetches its detail endpoint", async () => {
    mocks.fetchCatalog.mockResolvedValue({ products: [product], cases: [] });
    renderExperience();

    const item = await screen.findByRole("button", { name: /数据服务/ });
    fireEvent.click(item);

    await waitFor(() => expect(mocks.fetchProduct).toHaveBeenCalledWith(
      "tenant-a",
      "data-service",
      expect.any(AbortSignal),
    ));
    expect(await screen.findByRole("dialog", { name: "数据服务" })).toBeInTheDocument();
    expect(await screen.findByText("提供数据治理和分析支持。")).toBeInTheDocument();
  });

  it("blocks rapid duplicate lead submissions while preserving one request", async () => {
    const result = deferred<{ id: string; status: string; createdAt: string }>();
    mocks.submitLead.mockReturnValue(result.promise);
    renderExperience();
    await openAndFillLeadForm();

    const submit = screen.getByRole("button", { name: "确认授权并提交" });
    fireEvent.click(submit);
    fireEvent.click(submit);

    expect(mocks.submitLead).toHaveBeenCalledTimes(1);
    result.resolve({ id: "lead-1", status: "new", createdAt: "2026-07-11" });
    expect(await screen.findByText("需求已安全提交")).toBeInTheDocument();
    expect(screen.getByText(/lead-1/)).toBeInTheDocument();
  });

  it("refreshes a stale policy, clears consent, and requires explicit reconfirmation", async () => {
    mocks.submitLead.mockRejectedValueOnce(
      new AssistantApiError("授权告知已更新", {
        code: "POLICY_VERSION_MISMATCH",
        status: 409,
        retryable: true,
      }),
    );
    mocks.fetchCard.mockResolvedValueOnce({
      ...card,
      policy_versions: { ...card.policy_versions, lead_consent: "lead-v2" },
    });
    renderExperience();
    await openAndFillLeadForm();

    fireEvent.click(screen.getByRole("button", { name: "确认授权并提交" }));

    expect(await screen.findByText("授权告知已更新，请阅读并重新勾选后提交。")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByText(/lead-v2/)).toBeInTheDocument();
    expect(mocks.fetchCard).toHaveBeenCalledWith("tenant-a");
  });

  it("renders a locally generated QR code and copyable canonical share URL", async () => {
    renderExperience();
    fireEvent.click(screen.getByRole("button", { name: "分享名片" }));

    expect(
      await screen.findByRole("img", { name: "示例企业名片二维码" }),
    ).toBeInTheDocument();
    expect(screen.getByText(`${window.location.origin}${window.location.pathname}`)).toBeInTheDocument();
  });

  it("keeps long-term personalization off by default and requires explicit consent", async () => {
    renderExperience();

    expect(screen.getByText("仅在本企业内记住兴趣")).toBeInTheDocument();
    expect(screen.getByText(/不会跨企业关联，默认不开启，且可随时撤回/)).toBeInTheDocument();
    const grant = screen.getByRole("button", { name: "同意并开启" });
    expect(grant).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(grant);
    await waitFor(() =>
      expect(mocks.setProfileConsent).toHaveBeenCalledWith(
        expect.objectContaining({
          cardSlug: "tenant-a",
          companyId: "22222222-2222-2222-2222-222222222222",
          granted: true,
          policyVersions: expect.objectContaining({
            profilePersonalization: "profile-v1",
          }),
        }),
      ),
    );
    expect(await screen.findByRole("button", { name: "撤回并停止记住" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("shows a recoverable state when server revocation is temporarily unavailable", async () => {
    window.localStorage.setItem(
      getProfileLinkStorageKey(card.company.id),
      "existing-profile-token",
    );
    mocks.setProfileConsent.mockRejectedValueOnce(
      new AssistantApiError("网络不可用", { code: "NETWORK_ERROR", retryable: true }),
    );
    renderExperience();

    fireEvent.click(screen.getByRole("button", { name: "撤回并停止记住" }));

    expect(
      await screen.findByText(/服务器可能仍处于开启状态/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试完成撤回" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试完成撤回" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("never claims revocation after failed grant compensation and retries it", async () => {
    mocks.setProfileConsent
      .mockRejectedValueOnce(
        new AssistantApiError("服务器暂未确认撤回", {
          code: "PROFILE_REVOKE_PENDING",
          retryable: true,
        }),
      )
      .mockResolvedValueOnce({
        granted: false,
        recordedAt: "2026-07-12T01:05:00Z",
      });
    renderExperience();

    fireEvent.click(screen.getByRole("button", { name: "同意并开启" }));

    expect(await screen.findByText(/服务器可能仍处于开启状态/)).toBeInTheDocument();
    expect(screen.queryByText(/已撤回并删除/)).not.toBeInTheDocument();
    const retry = screen.getByRole("button", { name: "重试完成撤回" });
    fireEvent.click(retry);

    expect(await screen.findByText("已撤回并删除本设备上的长期关联信息。")).toBeInTheDocument();
    expect(mocks.setProfileConsent).toHaveBeenLastCalledWith(
      expect.objectContaining({ granted: false, companyId: card.company.id }),
    );
  });
});

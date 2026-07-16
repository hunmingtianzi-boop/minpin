import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PublicCardData } from "./lib/publicCardApi";
import { BusinessCardPrototypeApp } from "./prototype/BusinessCardPrototypeApp";
import { templateTenant } from "./tenants/template/tenant";

const publishedCard: PublicCardData = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "example",
  display_name: "示例顾问",
  title: "解决方案顾问",
  contact_fields: [],
  company: {
    id: "22222222-2222-2222-2222-222222222222",
    name: "示例企业",
    summary: "可信企业服务。",
    website: "https://example.cn",
  },
  featured_products: [],
  featured_cases: [],
  faq_items: [],
  ai_assistant: {
    available: false,
    display_name: "示例助手",
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

describe("BusinessCardPrototypeApp", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/c/template");
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses the imported card prototype shell and keeps real actions wired", () => {
    const onAssistant = vi.fn();
    const onLead = vi.fn();
    const onShare = vi.fn();

    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        onAssistant={onAssistant}
        onLead={onLead}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={onShare}
      />,
    );

    expect(screen.getByRole("heading", { name: templateTenant.brand.shortName })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "业务介绍" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "发起合作" }));
    fireEvent.click(screen.getByRole("button", { name: "分享名片" }));
    fireEvent.click(screen.getByRole("button", { name: new RegExp(templateTenant.assistant.knowledgeBase[0].shortQuestion) }));

    expect(onLead).toHaveBeenCalledOnce();
    expect(onShare).toHaveBeenCalledOnce();
    expect(onAssistant).toHaveBeenCalledWith(templateTenant.assistant.knowledgeBase[0].shortQuestion);

    fireEvent.click(screen.getByRole("button", { name: new RegExp(templateTenant.brand.name) }));
    expect(screen.getByRole("heading", { name: "企业介绍" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "名片导航" })).toBeInTheDocument();
  });

  it("exposes privacy and profile controls without fake visitor login", () => {
    window.history.replaceState({}, "", "/c/template?view=me");
    const onPrivacy = vi.fn();
    const onProfile = vi.fn();

    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        onAssistant={vi.fn()}
        onLead={vi.fn()}
        onPrivacy={onPrivacy}
        onProfile={onProfile}
        onShare={vi.fn()}
      />,
    );

    expect(screen.queryByText("微信授权登录")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /长期访客画像授权/ }));
    fireEvent.click(screen.getByRole("button", { name: /个人信息权利/ }));

    expect(onProfile).toHaveBeenCalledOnce();
    expect(onPrivacy).toHaveBeenCalledOnce();
  });

  it("respects a disabled AI assistant and preserves the published website", () => {
    window.history.replaceState({}, "", "/c/example?view=me");
    const onAssistant = vi.fn();

    render(
      <BusinessCardPrototypeApp
        tenant={templateTenant}
        card={publishedCard}
        onAssistant={onAssistant}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    expect(screen.getByRole("link", { name: /示例企业官网/ })).toHaveAttribute(
      "href",
      "https://example.cn/",
    );
    fireEvent.click(screen.getByRole("button", { name: "名片" }));
    expect(screen.getByText("企业尚未开放 AI 问答，请先通过合作需求与企业联系。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始咨询" })).not.toBeInTheDocument();
    expect(onAssistant).not.toHaveBeenCalled();
  });

  it("keeps a direct AI entry when no suggested questions are configured", () => {
    const onAssistant = vi.fn();
    const tenantWithoutQuestions = {
      ...templateTenant,
      assistant: {
        ...templateTenant.assistant,
        quickQuestionIds: [],
        knowledgeBase: [],
      },
    };

    render(
      <BusinessCardPrototypeApp
        tenant={tenantWithoutQuestions}
        onAssistant={onAssistant}
        onLead={vi.fn()}
        onPrivacy={vi.fn()}
        onProfile={vi.fn()}
        onShare={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /开始咨询/ }));
    expect(onAssistant).toHaveBeenCalledWith();
  });
});

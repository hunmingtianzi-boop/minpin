import type { EnterpriseCardConfig } from "../domain/card";
import type { PublicCardData } from "./publicCardApi";

export type MockCardKind = "employee" | "enterprise";

export function resolveMockCardKind(search: string): MockCardKind | undefined {
  const value = new URLSearchParams(search).get("mock-card");
  return value === "employee" || value === "enterprise" ? value : undefined;
}

export function createMockPublicCard(
  tenant: EnterpriseCardConfig,
  kind: MockCardKind,
): PublicCardData {
  const companyName = tenant.brand.name;
  const isEmployee = kind === "employee";
  return {
    id: `mock-${kind}`,
    slug: tenant.id,
    card_kind: kind,
    display_name: isEmployee ? "徐松波" : companyName,
    title: isEmployee ? "创始人 / 总经理" : "企业官方名片",
    avatar_url: null,
    contact_fields: [
      { label: "商务电话", value: "186 5718 9955", href: "tel:18657189955" },
      { label: "企业微信", value: "创非凡商务合作" },
    ],
    company: {
      id: `mock-company-${tenant.id}`,
      name: companyName,
      summary:
        tenant.hero.summary ||
        "以 AI 数智名片为入口，为企业提供持续在线的商务接待、需求识别与线索沉淀。",
      industry: "人工智能与企业服务",
      region: "浙江杭州",
      website: tenant.brand.officialAction.target,
      logo_url: tenant.brand.logo.src,
      official_card_slug: tenant.id,
    },
    featured_products: [
      { title: "企业 AI 商务接待", description: "基于企业公开资料回答业务问题并识别合作意向。" },
      { title: "数智名片", description: "连接个人身份、企业能力与访客需求。" },
    ],
    featured_cases: [
      { title: "商协会企业 AI 接待试点", description: "用统一名片入口承接企业展示、问答与合作需求。", industry: "商协会" },
    ],
    faq_items: [
      {
        id: "mock-faq-1",
        question: "数智名片和普通电子名片有什么区别？",
        answer: "数智名片不仅展示信息，还通过 AI 主动接待、意图识别和拜访纪要延续商务沟通。",
        source_label: "模拟企业公开资料",
      },
    ],
    ai_assistant: {
      available: true,
      display_name: isEmployee ? "徐松波的 AI 助手" : `${companyName} AI 助手`,
      disclosure: "当前为前端模拟；正式回答将基于企业已发布资料并提供必要的人工确认。",
      welcome_message: isEmployee
        ? "您好，我可以先介绍徐松波负责的业务、代表案例和合作方式。"
        : "您好，我可以介绍企业能力、产品服务、公开案例和合作路径。",
      suggested_questions: [
        "你们最适合服务哪类企业？",
        "可以介绍一个代表案例吗？",
        "我想谈合作，下一步怎么做？",
      ],
    },
    policy_versions: {
      privacy: "mock-privacy-v1",
      chat_notice: "mock-chat-v1",
      lead_consent: "mock-lead-v1",
      profile_personalization: "mock-profile-v1",
    },
  };
}

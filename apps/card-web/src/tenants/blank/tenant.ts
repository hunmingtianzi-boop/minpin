import type { KnowledgeItem } from "../../domain/card";
import { defineTenant } from "../defineTenant";

const assetBase = import.meta.env.BASE_URL.replace(/\/?$/, "/");
const sharedTemplateAsset = (fileName: string) =>
  `${assetBase}tenants/template/assets/${fileName}`;

const setupSource = "空白企业模板配置说明";

// This satisfies the assistant contract without adding client facts. The
// assistant stays disabled until reviewed enterprise knowledge is published.
const setupKnowledge: KnowledgeItem[] = [
  {
    id: "knowledge-not-configured",
    question: "为什么当前不能使用 AI 助手？",
    shortQuestion: "AI 为什么不可用？",
    answer:
      "这是未录入企业资料的空白模板。完成企业身份、产品服务和知识资料审核并发布后，AI 助手才会开放。",
    keywords: ["空白模板", "AI", "配置", "知识库"],
    source: setupSource,
  },
];

export const blankEnterpriseTenant = defineTenant({
  id: "blank-enterprise",
  version: "2026.07-blank-v1",
  isBlankTemplate: true,
  seo: {
    title: "空白企业数智名片 | 待配置",
    description: "用于录入甲方资料并生成企业数智名片的空白租户模板。",
  },
  brand: {
    name: "企业名称待录入",
    shortName: "姓名待录入",
    tagline: "品牌定位待录入",
    headerDescriptor: "职务待录入",
    logo: {
      src: sharedTemplateAsset("template-mark.webp"),
      alt: "空白企业模板标记",
      width: 432,
      height: 432,
    },
    homeAriaLabel: "返回空白企业名片首页",
    officialAction: {
      kind: "external",
      label: "企业官网待录入",
      target: "https://example.invalid",
    },
  },
  theme: {
    defaultMode: "light",
    action: "#146ef5",
    onAction: "#ffffff",
    light: {
      accent: "#146ef5",
      accentStrong: "#0758c9",
      accentSoft: "rgba(20, 110, 245, 0.1)",
      background: "#f2f5f7",
      surface: "#ffffff",
      surfaceRaised: "#f8fafb",
      surfaceMuted: "#edf1f4",
      text: "#1f2937",
      textSoft: "#64748b",
      textFaint: "#8491a3",
      line: "rgba(31, 41, 55, 0.12)",
      lineStrong: "rgba(31, 41, 55, 0.2)",
      shadow: "0 24px 70px rgba(31, 41, 55, 0.1)",
    },
    dark: {
      accent: "#69a7ff",
      accentStrong: "#9cc5ff",
      accentSoft: "rgba(105, 167, 255, 0.14)",
      background: "#10151c",
      surface: "#171e27",
      surfaceRaised: "#1d2631",
      surfaceMuted: "#25303d",
      text: "#f5f7fa",
      textSoft: "#bdc7d4",
      textFaint: "#8f9baa",
      line: "rgba(235, 241, 248, 0.14)",
      lineStrong: "rgba(235, 241, 248, 0.24)",
      shadow: "0 24px 76px rgba(0, 0, 0, 0.35)",
    },
    heroOverlay: {
      light: "rgba(242, 245, 247, 0.18)",
      dark: "rgba(9, 13, 18, 0.3)",
    },
    radiusCard: "20px",
    radiusControl: "12px",
    radiusSmall: "10px",
  },
  hero: {
    id: "top",
    kicker: "空白企业模板 · 尚未发布",
    titleLines: ["企业名称待录入", "品牌主张待录入"],
    summary: "企业简介、产品服务、案例、联系人和知识资料尚未录入。",
    art: {
      src: sharedTemplateAsset("template-hero.webp"),
      alt: "等待装入企业资料的空白模板示意",
      width: 1672,
      height: 941,
    },
    actions: [],
    metrics: [],
  },
  sections: [
    {
      type: "closing",
      id: "setup",
      navLabel: "配置",
      showInNav: false,
      heading: "企业资料尚未录入",
      description: "从企业管理后台录入并审核资料后，再生成对外展示页面。",
      art: {
        src: sharedTemplateAsset("template-hero.webp"),
        alt: "空白企业资料配置示意",
        width: 1672,
        height: 941,
      },
      actions: [],
    },
  ],
  assistant: {
    title: "企业 AI 助手待配置",
    status: "待配置",
    subtitle: "尚未发布企业知识",
    launcherAriaLabel: "企业 AI 助手尚未开放",
    launcherKicker: "知识库待配置",
    launcherLabel: "AI 助手待配置",
    initialMessage: {
      text: "企业知识资料尚未录入，审核发布后才能开始问答。",
      source: setupSource,
    },
    quickQuestionIds: [],
    labels: {
      closeBackdrop: "关闭助手",
      closeButton: "关闭助手",
      quickQuestions: "常见问题",
      quickQuestionsIntro: "可以先问",
      loading: "正在检索企业知识",
      input: "向企业助手提问",
      placeholder: "企业知识尚未配置",
      send: "发送问题",
      sourcePrefix: "来源：",
    },
    disclaimer: "企业知识尚未配置，当前模板不会生成或猜测任何企业信息。",
    knowledgeBase: setupKnowledge,
    fallback: {
      answer: "企业知识尚未配置，请先在管理后台录入、审核并发布资料。",
      source: setupSource,
    },
  },
  footer: {
    brandNote: "空白企业数智名片模板 · 尚未发布",
    disclaimer: "当前页面不代表任何真实企业，不包含企业事实或业务承诺。",
    backToTopAction: { kind: "anchor", label: "返回顶部", target: "#top" },
  },
});

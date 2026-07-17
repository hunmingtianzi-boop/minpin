import {
  ArrowLeftIcon,
  BookmarkSimpleIcon,
  BuildingsIcon,
  CaretRightIcon,
  ChatCircleDotsIcon,
  HandshakeIcon,
  IdentificationCardIcon,
  PaperPlaneTiltIcon,
  SealCheckIcon,
  ShareNetworkIcon,
  SparkleIcon,
  SquaresFourIcon,
  UserCircleIcon,
} from "@phosphor-icons/react";
import { useEffect, useState, type ReactNode } from "react";

import type { EnterpriseCardConfig } from "../domain/card";
import { AssistantApiError } from "../lib/assistantApi";
import { copyText } from "../lib/clipboard";
import type { PublicCardData } from "../lib/publicCardApi";
import {
  fetchPublicCaseStudy,
  fetchPublicCatalog,
  fetchPublicProduct,
  fetchPublicRecommendations,
  isPublicExperienceConfigured,
  safeContactHref,
  type PublicCaseStudy,
  type PublicCatalog,
  type PublicProduct,
  type PublicRecommendation,
} from "../lib/publicExperienceApi";

import "./prototype.css";
import "./prototype-overrides.css";
import "./integration.css";

type View = "card" | "company" | "square" | "me" | "detail";
type BaseView = Exclude<View, "detail">;
type SquareFilter = "全部" | "产品" | "案例";
type DetailTarget =
  | { kind: "product"; item: PublicProduct; from: BaseView }
  | { kind: "case"; item: PublicCaseStudy; from: BaseView };
type DetailInput =
  | { kind: "product"; item: PublicProduct }
  | { kind: "case"; item: PublicCaseStudy };
type DetailHistoryTarget = {
  kind: DetailInput["kind"];
  slug: string;
  from: BaseView;
};
type DetailRoute = Pick<DetailHistoryTarget, "kind" | "slug">;
type PrototypeHistoryState =
  | { bpView: BaseView; from?: BaseView }
  | { bpView: "detail"; detail: DetailHistoryTarget };

type CatalogState =
  | { status: "idle" | "loading" }
  | { status: "ready"; data: PublicCatalog }
  | { status: "error"; message: string };
type DetailLookupState =
  | { status: "idle" }
  | { status: "loading"; key: string }
  | { status: "missing"; key: string }
  | { status: "error"; key: string; message: string };

const publicViews: BaseView[] = ["card", "company", "square", "me"];

function isBaseView(value: unknown): value is BaseView {
  return typeof value === "string" && publicViews.includes(value as BaseView);
}

function initialBaseView(): BaseView {
  const candidate = new URLSearchParams(window.location.search).get("view");
  return isBaseView(candidate) ? candidate : "card";
}

function scrollPageToTop() {
  const frame = document.querySelector<HTMLElement>(".bp-phone-frame");
  if (typeof frame?.scrollTo === "function") {
    frame.scrollTo({ top: 0, behavior: "auto" });
  }
  document.documentElement.scrollTop = 0;
  document.body.scrollTop = 0;
}

function initials(value: string) {
  const normalized = value.trim();
  if (!normalized) return "名";
  return Array.from(normalized).slice(-2).join("");
}

function recordLabel(record: Record<string, string>) {
  return (
    record.name ||
    record.title ||
    record.label ||
    record.summary ||
    record.value ||
    ""
  ).trim();
}

function detailRouteFromLocation() {
  const raw = new URLSearchParams(window.location.search).get("detail");
  const [kind, ...slugParts] = raw?.split(":") ?? [];
  const slug = slugParts.join(":").trim();
  if ((kind === "product" || kind === "case") && slug) {
    return { kind, slug } as const;
  }
  return undefined;
}

function publicCardHref(slug: string, fromEmployeeSlug?: string) {
  const url = new URL(window.location.href);
  const encodedSlug = encodeURIComponent(slug);
  url.pathname = /(?:^|\/)c\/[^/]+/i.test(url.pathname)
    ? url.pathname.replace(/((?:^|\/)c\/)[^/]+/i, `$1${encodedSlug}`)
    : `/c/${encodedSlug}`;
  const isMock = url.searchParams.has("mock-card");
  url.search = "";
  if (isMock) url.searchParams.set("mock-card", "enterprise");
  if (fromEmployeeSlug) url.searchParams.set("from_employee", fromEmployeeSlug);
  return `${url.pathname}${url.search}`;
}

function employeeCardHref(slug: string) {
  const url = new URL(window.location.href);
  const encodedSlug = encodeURIComponent(slug);
  url.pathname = /(?:^|\/)c\/[^/]+/i.test(url.pathname)
    ? url.pathname.replace(/((?:^|\/)c\/)[^/]+/i, `$1${encodedSlug}`)
    : `/c/${encodedSlug}`;
  const isMock = url.searchParams.has("mock-card");
  url.search = "";
  if (isMock) url.searchParams.set("mock-card", "employee");
  return `${url.pathname}${url.search}`;
}

function recommendationSlug(item: PublicRecommendation) {
  try {
    const segments = new URL(item.url, window.location.origin).pathname
      .split("/")
      .filter(Boolean);
    return decodeURIComponent(segments.at(-1) ?? "");
  } catch {
    return "";
  }
}

function Arrow() {
  return <CaretRightIcon aria-hidden="true" size={17} weight="bold" />;
}

function Avatar({ label, src, small = false }: { label: string; src?: string; small?: boolean }) {
  if (src) {
    return (
      <img
        className={`bp-avatar${small ? " bp-avatar-small" : ""}`}
        src={src}
        alt={`${label}的职业头像`}
      />
    );
  }
  return (
    <span
      className={`bp-avatar bp-avatar-fallback${small ? " bp-avatar-small" : ""}`}
      aria-label={`${label}的姓名缩写`}
    >
      {initials(label)}
    </span>
  );
}

function AppHeader({
  back,
  title,
  onShare,
}: {
  back?: () => void;
  title?: string;
  onShare?: () => void;
}) {
  const [clock, setClock] = useState(() =>
    new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(
      new Date(),
    ),
  );

  useEffect(() => {
    const timer = window.setInterval(() => {
      setClock(
        new Intl.DateTimeFormat("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        }).format(new Date()),
      );
    }, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <>
      <div className="bp-statusbar bp-card-statusbar" aria-hidden="true">
        <strong>{clock}</strong>
        <i />
        <span>▮▮▮　◒　▰</span>
      </div>
      <header className={`bp-topbar${title ? "" : " bp-card-topbar"}`}>
        {back ? (
          <button type="button" onClick={back} aria-label="返回">
            <ArrowLeftIcon size={26} />
          </button>
        ) : (
          <span className="bp-topbar-spacer" aria-hidden="true" />
        )}
        <strong>{title ?? ""}</strong>
        {onShare ? (
          <button type="button" onClick={onShare} aria-label="分享名片">
            <ShareNetworkIcon size={24} />
            {!title && <small>分享</small>}
          </button>
        ) : (
          <span className="bp-topbar-spacer" aria-hidden="true" />
        )}
      </header>
    </>
  );
}

function Section({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="bp-section">
      <div className="bp-section-title">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function NavIcon({ view, active }: { view: View; active: boolean }) {
  const props = { size: 22, weight: active ? "fill" : "regular" } as const;
  if (view === "card") return <IdentificationCardIcon {...props} />;
  if (view === "square") return <SquaresFourIcon {...props} />;
  if (view === "company") return <BuildingsIcon {...props} />;
  return <UserCircleIcon {...props} />;
}

function LoadingRows({ label }: { label: string }) {
  return (
    <div className="bp-resource-state" role="status">
      <span />
      <span />
      <p>正在加载{label}</p>
    </div>
  );
}

export function BusinessCardPrototypeApp({
  tenant,
  card,
  onAssistant,
  onLead,
  onPrivacy,
  onProfile,
  onShare,
}: {
  tenant: EnterpriseCardConfig;
  card?: PublicCardData;
  onAssistant: (question?: string) => void;
  onLead: () => void;
  onPrivacy: () => void;
  onProfile: () => void;
  onShare: () => void;
}) {
  const standaloneKind = card?.card_kind;
  const isStandaloneCard = standaloneKind === "employee" || standaloneKind === "enterprise";
  const standaloneRoot: BaseView = standaloneKind === "enterprise" ? "company" : "card";
  const defaultBaseView: BaseView = isStandaloneCard ? standaloneRoot : "card";
  const initialCardView = () => {
    if (detailRouteFromLocation()) return "detail" as const;
    if (!isStandaloneCard) return initialBaseView();
    return new URLSearchParams(window.location.search).get("view") === "square"
      ? "square"
      : standaloneRoot;
  };
  const [view, setView] = useState<View>(initialCardView);
  const [detail, setDetail] = useState<DetailTarget | null>(null);
  const [detailLookup, setDetailLookup] = useState<DetailLookupState>({ status: "idle" });
  const [locationRevision, setLocationRevision] = useState(0);
  const [catalog, setCatalog] = useState<CatalogState>({ status: "idle" });
  const [recommendations, setRecommendations] = useState<PublicRecommendation[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<SquareFilter>("全部");
  const [copyFeedback, setCopyFeedback] = useState<{
    key: string;
    status: "copied" | "failed";
  } | null>(null);
  const [openFaq, setOpenFaq] = useState<string | null>(card?.faq_items[0]?.id ?? null);
  const storageKey = `cf-card-saved:${card?.slug ?? tenant.id}`;
  const [saved, setSaved] = useState(() => {
    try {
      return window.localStorage.getItem(storageKey) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    setOpenFaq(card?.faq_items[0]?.id ?? null);
  }, [card?.faq_items]);

  useEffect(() => {
    const handlePopState = (event: PopStateEvent) => {
      const state = event.state as PrototypeHistoryState | null;
      if (state?.bpView === "detail" && state.detail) {
        setDetail(null);
        setView("detail");
      } else {
        setDetail(null);
        setView(
          isBaseView(state?.bpView)
            ? state.bpView
            : initialCardView(),
        );
      }
      setLocationRevision((current) => current + 1);
      scrollPageToTop();
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [isStandaloneCard, standaloneRoot]);

  useEffect(() => {
    if (!card || !isPublicExperienceConfigured()) {
      setCatalog({ status: "idle" });
      setRecommendations([]);
      return undefined;
    }
    const controller = new AbortController();
    setCatalog({ status: "loading" });
    void fetchPublicCatalog(card.slug, controller.signal)
      .then((data) => setCatalog({ status: "ready", data }))
      .catch(() => {
        if (!controller.signal.aborted) {
          setCatalog({ status: "error", message: "业务资料暂时无法加载，请稍后重试。" });
        }
      });
    void fetchPublicRecommendations(card.slug, controller.signal)
      .then(setRecommendations)
      .catch(() => {
        if (!controller.signal.aborted) setRecommendations([]);
      });
    return () => controller.abort();
  }, [card]);

  const featureSection = tenant.sections.find((section) => section.type === "feature-grid");
  const tenantBusinesses = featureSection?.businesses ?? [];
  const products = catalog.status === "ready" ? catalog.data.products : [];
  const cases = catalog.status === "ready" ? catalog.data.cases : [];
  const requestedDetail = detailRouteFromLocation();

  useEffect(() => {
    const route = detailRouteFromLocation();
    if (!route) {
      setDetailLookup({ status: "idle" });
      if (view === "detail") {
        setDetail(null);
        setView(defaultBaseView);
      }
      return;
    }
    setView("detail");
    if (catalog.status !== "ready") {
      setDetail(null);
      setDetailLookup({ status: "idle" });
      return;
    }
    const item = route.kind === "product"
      ? catalog.data.products.find((candidate) => candidate.slug === route.slug)
      : catalog.data.cases.find((candidate) => candidate.slug === route.slug);
    const historyState = window.history.state as PrototypeHistoryState | null;
    const from = historyState?.bpView === "detail" &&
      historyState.detail.kind === route.kind &&
      historyState.detail.slug === route.slug
      ? historyState.detail.from
      : defaultBaseView;
    if (item) {
      setDetailLookup({ status: "idle" });
      setDetail(
        route.kind === "product"
          ? { kind: "product", item: item as PublicProduct, from }
          : { kind: "case", item: item as PublicCaseStudy, from },
      );
      scrollPageToTop();
      return;
    }
    if (!card?.slug) {
      setDetail(null);
      setDetailLookup({ status: "missing", key: `${route.kind}:${route.slug}` });
      return;
    }

    const controller = new AbortController();
    const key = `${route.kind}:${route.slug}`;
    setDetail(null);
    setDetailLookup({ status: "loading", key });
    const request = route.kind === "product"
      ? fetchPublicProduct(card.slug, route.slug, controller.signal)
      : fetchPublicCaseStudy(card.slug, route.slug, controller.signal);
    void request
      .then((resolved) => {
        setDetailLookup({ status: "idle" });
        setDetail(
          route.kind === "product"
            ? { kind: "product", item: resolved as PublicProduct, from }
            : { kind: "case", item: resolved as PublicCaseStudy, from },
        );
        scrollPageToTop();
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof AssistantApiError && error.status === 404) {
          setDetailLookup({ status: "missing", key });
          return;
        }
        setDetailLookup({
          status: "error",
          key,
          message: "详情暂时无法加载，请稍后重试。",
        });
      });
    return () => controller.abort();
  }, [card?.slug, catalog, defaultBaseView, locationRevision, view]);
  const isBlankTemplate = Boolean(tenant.isBlankTemplate && !card);
  const isPublished = Boolean(card);
  const companyName = card?.company.name ?? tenant.brand.name;
  const companySummary = card?.company.summary || tenant.hero.summary;
  const displayName = card?.display_name ?? tenant.brand.shortName;
  const title = card?.title ?? tenant.brand.headerDescriptor;
  const avatar = isBlankTemplate ? undefined : card?.avatar_url || undefined;
  const companyLogo = isBlankTemplate
    ? undefined
    : card?.company.logo_url || tenant.brand.logo.src;
  const assistantName = card?.ai_assistant.display_name ?? tenant.assistant.title;
  const assistantAvailable =
    !isBlankTemplate && (card?.ai_assistant.available ?? true);
  const tenantQuestions = tenant.assistant.quickQuestionIds.flatMap((id) => {
    const item = tenant.assistant.knowledgeBase.find((candidate) => candidate.id === id);
    return item ? [item.shortQuestion || item.question] : [];
  });
  const suggestedQuestions: string[] = (
    card?.ai_assistant.suggested_questions.length
      ? card.ai_assistant.suggested_questions
      : tenantQuestions
  ).slice(0, 3);
  const featuredLabels = (card?.featured_products ?? []).map(recordLabel).filter(Boolean);
  const tags = [...featuredLabels, ...tenantBusinesses.map((item) => item.title)]
    .filter((value, index, all) => all.indexOf(value) === index)
    .slice(0, 3);
  const introParagraphs = [companySummary, ...tenantBusinesses.map((item) => item.description)]
    .filter(Boolean)
    .slice(0, 4);
  const representativeCase = cases[0];
  const representativeProduct = products[0];
  const contactFields = card?.contact_fields.filter((item) => item.label && item.value) ?? [];
  const websiteHref = isBlankTemplate
    ? undefined
    : card?.company.website
      ? safeContactHref({ href: card.company.website })
      : safeContactHref({ href: tenant.brand.officialAction.target });
  const websiteLabel = card?.company.website
    ? `${companyName}官网`
    : tenant.brand.officialAction.label;
  const adminHref =
    import.meta.env.VITE_ADMIN_BASE_URL?.trim() || `${import.meta.env.BASE_URL}admin/`;
  const onboardingHref = `${adminHref.replace(/\/*$/, "/")}platform/onboarding`;
  const officialCompanyHref = card?.company.official_card_slug
    ? publicCardHref(
      card.company.official_card_slug,
      standaloneKind === "employee" ? card.slug : undefined,
    )
    : undefined;
  const employeeReturnSlug = standaloneKind === "enterprise"
    ? new URLSearchParams(window.location.search).get("from_employee")
    : undefined;
  const employeeReturnHref = employeeReturnSlug
    ? employeeCardHref(employeeReturnSlug)
    : undefined;
  const returnToEmployeeCard = () => {
    if (employeeReturnHref) window.location.assign(employeeReturnHref);
  };

  const go = (next: BaseView) => {
    if (next === view && detail === null) return;
    const from = view === "detail" ? detail?.from ?? defaultBaseView : view;
    setDetail(null);
    setView(next);
    const url = new URL(window.location.href);
    url.searchParams.delete("detail");
    if (next === defaultBaseView) url.searchParams.delete("view");
    else url.searchParams.set("view", next);
    window.history.pushState({ bpView: next, from }, "", url);
    scrollPageToTop();
  };

  const replaceWithView = (next: BaseView) => {
    setDetail(null);
    setView(next);
    const url = new URL(window.location.href);
    url.searchParams.delete("detail");
    if (next === defaultBaseView) url.searchParams.delete("view");
    else url.searchParams.set("view", next);
    window.history.replaceState({ bpView: next }, "", url);
    scrollPageToTop();
  };

  const replaceWithCard = () => replaceWithView("card");

  const returnFromCompany = () => {
    const state = window.history.state as PrototypeHistoryState | null;
    if (state?.bpView === "company" && state.from) {
      window.history.back();
      return;
    }
    replaceWithCard();
  };

  const openDetail = (target: DetailInput) => {
    const from: BaseView = view === "detail"
      ? detail?.from ?? defaultBaseView
      : view;
    const nextDetail: DetailTarget = target.kind === "product"
      ? { kind: "product", item: target.item, from }
      : { kind: "case", item: target.item, from };
    setDetail(nextDetail);
    setDetailLookup({ status: "idle" });
    const url = new URL(window.location.href);
    url.searchParams.set("detail", `${target.kind}:${target.item.slug}`);
    window.history.pushState(
      {
        bpView: "detail",
        detail: { kind: target.kind, slug: target.item.slug, from },
      } satisfies PrototypeHistoryState,
      "",
      url,
    );
    setView("detail");
    scrollPageToTop();
  };

  const openDetailRoute = (route: DetailRoute) => {
    const from: BaseView = view === "detail"
      ? detail?.from ?? defaultBaseView
      : view;
    setDetail(null);
    setDetailLookup({ status: "idle" });
    const url = new URL(window.location.href);
    url.searchParams.set("detail", `${route.kind}:${route.slug}`);
    window.history.pushState(
      { bpView: "detail", detail: { ...route, from } } satisfies PrototypeHistoryState,
      "",
      url,
    );
    setView("detail");
    setLocationRevision((current) => current + 1);
    scrollPageToTop();
  };

  const returnFromDetail = () => {
    const state = window.history.state as PrototypeHistoryState | null;
    if (state?.bpView === "detail") {
      window.history.back();
      return;
    }
    replaceWithView(detail?.from ?? defaultBaseView);
  };

  const copyContact = async (key: string, value: string) => {
    try {
      await copyText(value);
      setCopyFeedback({ key, status: "copied" });
    } catch {
      setCopyFeedback({ key, status: "failed" });
    }
  };

  const toggleSaved = () => {
    const next = !saved;
    setSaved(next);
    try {
      if (next) window.localStorage.setItem(storageKey, "1");
      else window.localStorage.removeItem(storageKey);
    } catch {
      // The visual state remains useful when storage is unavailable.
    }
  };

  const normalizedQuery = query.trim().toLocaleLowerCase("zh-CN");
  const visibleProducts = products.filter((item) => {
    if (filter === "案例") return false;
    return !normalizedQuery || `${item.name}${item.category ?? ""}${item.summary}`.toLocaleLowerCase("zh-CN").includes(normalizedQuery);
  });
  const visibleCases = cases.filter((item) => {
    if (filter === "产品") return false;
    return !normalizedQuery || `${item.title}${item.industry ?? ""}${item.background}${item.result}`.toLocaleLowerCase("zh-CN").includes(normalizedQuery);
  });

  const recommendationTarget = (item: PublicRecommendation): DetailInput | undefined => {
    const slug = recommendationSlug(item);
    if (item.resourceType === "product") {
      const product = products.find((candidate) => candidate.slug === slug)
        ?? products.find((candidate) => candidate.name === item.title);
      return product ? { kind: "product", item: product } : undefined;
    }
    if (item.resourceType === "case_study") {
      const caseStudy = cases.find((candidate) => candidate.slug === slug)
        ?? cases.find((candidate) => candidate.title === item.title);
      return caseStudy ? { kind: "case", item: caseStudy } : undefined;
    }
    return undefined;
  };

  const recommendationRoute = (item: PublicRecommendation): DetailRoute | undefined => {
    const slug = recommendationSlug(item);
    if (!slug) return undefined;
    if (item.resourceType === "product") return { kind: "product", slug };
    if (item.resourceType === "case_study") return { kind: "case", slug };
    return undefined;
  };

  const bottom = (
    <nav className="bp-bottom-nav" aria-label="名片导航">
      {([
        ["名片", "card"],
        ["业务", "square"],
        ["企业", "company"],
        ["我的", "me"],
      ] as Array<[string, BaseView]>).map(([label, target]) => (
        <button
          key={target}
          className={view === target ? "active" : ""}
          type="button"
          onClick={() => go(target)}
        >
          <span><NavIcon view={target} active={view === target} /></span>
          <small>{label}</small>
        </button>
      ))}
    </nav>
  );

  const cardPage = (
    <>
      <AppHeader onShare={onShare} />
      <main className="bp-page bp-card-page">
        <div className="bp-person-head">
          {avatar ? (
            <img className="bp-portrait" src={avatar} alt={`${displayName}的职业头像`} />
          ) : (
            <span className="bp-portrait bp-portrait-fallback" aria-label={`${displayName}的姓名缩写`}>
              {initials(displayName)}
            </span>
          )}
          <div>
            <div className="bp-name-line">
              <h1>{displayName}</h1>
              <b className={!isPublished ? "bp-template-badge" : undefined}>
                {isBlankTemplate ? "空白模板" : isPublished ? <><SealCheckIcon size={17} weight="fill" /> 已发布</> : "本地展示"}
              </b>
            </div>
            <p>{title}</p>
            {isStandaloneCard ? (
              officialCompanyHref ? (
                <a className="bp-affiliation" href={officialCompanyHref}>
                  <BuildingsIcon size={18} weight="fill" /> {companyName} <Arrow />
                </a>
              ) : (
                <span className="bp-affiliation bp-affiliation-disabled">
                  <BuildingsIcon size={18} weight="fill" /> {companyName}<small>企业名片暂未发布</small>
                </span>
              )
            ) : (
              <button className="bp-affiliation" type="button" onClick={() => go("company")}>
                <BuildingsIcon size={18} weight="fill" /> {companyName} <Arrow />
              </button>
            )}
            <div className="bp-tags">
              {tags.map((tag) => <span key={tag}>{tag}</span>)}
            </div>
          </div>
        </div>

        <section className="bp-card-intro">
          <div className="bp-card-panel-title"><h2>业务介绍</h2></div>
          <div className="bp-intro">
            {isBlankTemplate ? (
              <div className="bp-template-empty">
                <strong>尚未录入企业资料</strong>
                <p>导入甲方主体、品牌、业务、案例和联系资料后，此处会自动生成可审核的企业介绍。</p>
                <a href={onboardingHref}>进入后台开始配置 <Arrow /></a>
              </div>
            ) : (
              <>
                {introParagraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                <button type="button" className="bp-text-button" onClick={() => go(isStandaloneCard ? "square" : "company")}>
                  {isStandaloneCard ? "查看全部业务" : "查看企业详情"} <Arrow />
                </button>
              </>
            )}
          </div>
        </section>

        {representativeCase ? (
          <button
            type="button"
            className="bp-case bp-card-case"
            onClick={() => openDetail({ kind: "case", item: representativeCase })}
          >
            <div className="bp-case-copy">
              <small>代表案例</small>
              <strong>{representativeCase.title}</strong>
              <span>{representativeCase.result}</span>
            </div>
            <i><span>▰</span></i><em>查看案例 <Arrow /></em>
          </button>
        ) : representativeProduct ? (
          <button
            type="button"
            className="bp-case bp-card-case"
            onClick={() => openDetail({ kind: "product", item: representativeProduct })}
          >
            <div className="bp-case-copy">
              <small>核心业务</small>
              <strong>{representativeProduct.name}</strong>
              <span>{representativeProduct.summary}</span>
            </div>
            <i><span>▰</span></i><em>查看详情 <Arrow /></em>
          </button>
        ) : null}

        <section className="bp-ai-card">
          <div><i>AI</i><span><strong>{assistantName}</strong><small>{assistantAvailable ? isPublished ? "基于已发布资料" : "基于本地展示资料" : "暂未开放"}</small></span></div>
          <p>{isBlankTemplate ? "上传并审核企业知识资料后，AI 才会基于已发布内容回答，不会使用模板猜测企业事实。" : assistantAvailable ? (card?.ai_assistant.disclosure || "回答会引用企业已发布知识，重要事项请与企业进一步确认。") : "企业尚未开放 AI 问答，请先通过合作需求与企业联系。"}</p>
          {assistantAvailable && suggestedQuestions.map((question, index) => (
            <button type="button" key={question} onClick={() => onAssistant(question)}>
              {index === 0 ? <SparkleIcon size={18} weight="fill" /> : <span aria-hidden="true">●</span>}
              {question} <Arrow />
            </button>
          ))}
          {assistantAvailable && !suggestedQuestions.length && (
            <button type="button" onClick={() => onAssistant()}>
              <ChatCircleDotsIcon size={18} /> 开始咨询 <Arrow />
            </button>
          )}
          {isBlankTemplate && <a className="bp-template-link" href={onboardingHref}>配置企业知识库 <Arrow /></a>}
        </section>
        {isStandaloneCard && (
          <div className="bp-standalone-utilities">
            <button type="button" onClick={toggleSaved}>{saved ? "取消保存" : "保存名片"}</button>
            <button type="button" onClick={onPrivacy}>隐私与个人信息</button>
          </div>
        )}
      </main>
      {isStandaloneCard ? <div className="bp-sticky-actions bp-standalone-action-bar" aria-label="名片主要操作">
        <button className="primary" type="button" disabled={!assistantAvailable} onClick={() => onAssistant()}>问 AI</button>
        <button type="button" onClick={onLead}>发起合作</button>
      </div> : <div className="bp-sticky-actions bp-card-actions">
        {isBlankTemplate ? <>
          <button type="button" onClick={onShare}><ShareNetworkIcon size={22} /> 分享模板</button>
          <a className="primary" href={onboardingHref}>开始配置企业</a>
        </> : <>
          <button type="button" onClick={toggleSaved} aria-pressed={saved}>
            <BookmarkSimpleIcon size={22} weight={saved ? "fill" : "regular"} />
            {saved ? "本机已保存" : "保存到本机"}
          </button>
          <button className="primary" type="button" onClick={onLead}>
            <HandshakeIcon size={22} /> 发起合作
          </button>
        </>}
      </div>}
      {!isStandaloneCard && bottom}
    </>
  );

  const companyPage = (
    <>
      <AppHeader
        back={isStandaloneCard ? (employeeReturnHref ? returnToEmployeeCard : undefined) : returnFromCompany}
        title={isStandaloneCard ? "企业官方名片" : `来自${displayName}的名片`}
        onShare={onShare}
      />
      <main className="bp-page bp-company-page">
        <div className="bp-company-head">
          {companyLogo ? <img src={companyLogo} alt={`${companyName}标识`} /> : <i>◈</i>}
          <div>
            <div className="bp-name-line"><h1>{companyName}</h1><b>{isBlankTemplate ? "待配置" : isPublished ? "✓ 资料已发布" : "本地展示"}</b></div>
            <p>{companySummary}</p>
            <small className="bp-company-meta">
              {[card?.company.industry, card?.company.region].filter(Boolean).join(" · ") || tenant.brand.headerDescriptor}
            </small>
            <div className="bp-tags">{tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
          </div>
        </div>

        <section className="bp-company-position">
          <small>{isBlankTemplate ? "配置提示" : "我们能帮助你"}</small>
          <strong>{isBlankTemplate ? "录入品牌定位和核心价值后，此处会生成企业对外主张。" : tenant.hero.summary}</strong>
        </section>

        <Section title="企业介绍">
          {isBlankTemplate ? <div className="bp-empty-state bp-inline-empty"><strong>企业介绍待录入</strong><p>支持从企业简介、官网文本或审核后的文档生成。</p><a href={onboardingHref}>录入企业资料</a></div> : <div className="bp-intro"><p>{companySummary}</p></div>}
        </Section>

        <Section title="核心业务">
          {catalog.status === "loading" ? <LoadingRows label="业务资料" /> : (
            products.length || tenantBusinesses.length ? <div className="bp-list">
              {(products.length ? products.slice(0, 4) : tenantBusinesses.slice(0, 4)).map((item) => {
                const isProduct = "slug" in item;
                const titleText = isProduct ? item.name : item.title;
                const description = isProduct ? item.summary : item.description;
                return (
                  <button
                    type="button"
                    key={titleText}
                    disabled={!isProduct && !assistantAvailable}
                    onClick={() => isProduct ? openDetail({ kind: "product", item }) : onAssistant(`请介绍${titleText}`)}
                  >
                    <i>◇</i><span><strong>{titleText}</strong><small>{description}</small></span><Arrow />
                  </button>
                );
              })}
            </div> : <div className="bp-empty-state bp-inline-empty"><strong>产品与服务待录入</strong><p>添加业务名称、适用客户、价值说明和服务边界后即可展示。</p><a href={onboardingHref}>添加业务资料</a></div>
          )}
        </Section>

        {representativeCase && (
          <Section title="代表案例">
            <button
              type="button"
              className="bp-case bp-company-case"
              onClick={() => openDetail({ kind: "case", item: representativeCase })}
            >
              <span><small>{representativeCase.industry || "公开案例"}</small><strong>{representativeCase.title}</strong><em>{representativeCase.result}</em></span><i>▦</i><Arrow />
            </button>
          </Section>
        )}

        <Section title="企业资料">
          {isBlankTemplate ? <div className="bp-empty-state bp-inline-empty"><strong>可信资料待审核</strong><p>主体信息、资质、案例授权和公开范围须确认后才会显示。</p><a href={onboardingHref}>进入资料审核</a></div> : <div className="bp-trust">
            <span>✓ 企业公开资料</span><span>✓ AI 引用可追溯</span>
            {(card?.company.industry || card?.company.region) && <span>{[card.company.industry, card.company.region].filter(Boolean).join(" · ")}</span>}
            {websiteHref && <a className="bp-trust-link" href={websiteHref} target="_blank" rel="noreferrer">访问企业官网 <Arrow /></a>}
          </div>}
        </Section>

        {!isStandaloneCard && <Section title="可以为你对接的人">
          {isBlankTemplate ? <div className="bp-empty-state bp-inline-empty"><strong>名片持有人待录入</strong><p>添加姓名、职务、头像和经授权的联系渠道。</p><a href={onboardingHref}>配置名片成员</a></div> : <div className="bp-people">
            <button type="button" onClick={() => go("card")}>
              <Avatar small label={displayName} src={avatar} />
              <span><strong>{displayName}　{title}</strong><small>{companyName}</small></span><Arrow />
            </button>
          </div>}
        </Section>}

        {card?.faq_items.length ? (
          <Section title="常见问题">
            <div className="bp-faq-list">
              {card.faq_items.map((faq) => (
                <article className={openFaq === faq.id ? "open" : ""} key={faq.id}>
                  <button type="button" aria-expanded={openFaq === faq.id} onClick={() => setOpenFaq(openFaq === faq.id ? null : faq.id)}>
                    <strong>{faq.question}</strong><span>{openFaq === faq.id ? "−" : "+"}</span>
                  </button>
                  {openFaq === faq.id && <div><p>{faq.answer}</p><small>资料来源：{faq.source_label}</small>{assistantAvailable && <button type="button" onClick={() => onAssistant(faq.question)}>继续问 AI <Arrow /></button>}</div>}
                </article>
              ))}
            </div>
          </Section>
        ) : null}

        <section className="bp-ai-card bp-company-ai">
          <div><i>AI</i><span><strong>{assistantName}</strong><small>{assistantAvailable ? isPublished ? "基于已发布资料" : "基于本地展示资料" : "暂未开放"}</small></span></div>
          <p>{isBlankTemplate ? "知识资料尚未录入；完成解析、预览和发布后才会开放问答。" : assistantAvailable ? (card?.ai_assistant.welcome_message || "我可以介绍企业能力、解释常见问题，并帮助整理合作需求。") : "企业尚未开放 AI 问答，可提交合作需求等待人工联系。"}</p>
          {assistantAvailable && <button type="button" onClick={() => onAssistant()}>咨询适合我们的解决方案 <Arrow /></button>}
          {isBlankTemplate && <a className="bp-template-link" href={onboardingHref}>配置企业知识库 <Arrow /></a>}
        </section>
        {isStandaloneCard && (
          <div className="bp-standalone-utilities">
            <button type="button" onClick={toggleSaved}>{saved ? "取消保存" : "保存企业名片"}</button>
            <button type="button" onClick={onPrivacy}>隐私与个人信息</button>
          </div>
        )}
      </main>
      {isStandaloneCard ? <div className="bp-sticky-actions bp-standalone-action-bar" aria-label="企业名片主要操作">
        <button className="primary" type="button" disabled={!assistantAvailable} onClick={() => onAssistant()}>咨询 AI</button>
        <button type="button" onClick={onLead}>提交合作需求</button>
      </div> : <div className="bp-sticky-actions bp-company-actions">
        {isBlankTemplate ? <>
          <button type="button" onClick={onShare}>分享空白模板</button>
          <a className="primary" href={onboardingHref}>开始配置企业</a>
        </> : <>
          <button type="button" onClick={toggleSaved}>{saved ? "✓ 本机已保存企业名片" : "⌑ 保存到本机"}</button>
          <button className="primary" type="button" onClick={onLead}>⌁ 发起合作</button>
        </>}
      </div>}
      {!isStandaloneCard && bottom}
    </>
  );

  const squarePage = (
    <>
      <AppHeader back={isStandaloneCard ? () => replaceWithView(standaloneRoot) : undefined} title="业务广场" onShare={onShare} />
      <main className="bp-page">
        <div className="bp-square-hero">
          <p>真实公开资料</p><h1>从产品、案例和业务方向开始</h1>
          <small>所有内容均来自企业当前已发布资料；不会展示未公开内容。</small>
          <label className="bp-search">⌕ <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="搜索产品、案例或业务方向" placeholder="搜索产品、案例或业务方向" /></label>
        </div>
        <Section title="内容类型">
          <div className="bp-filter">
            {(["全部", "产品", "案例"] as SquareFilter[]).map((item) => <button className={filter === item ? "active" : ""} type="button" key={item} onClick={() => setFilter(item)}>{item}</button>)}
          </div>
        </Section>

        {catalog.status === "loading" ? <LoadingRows label="公开内容" /> : catalog.status === "idle" ? (
          <div className="bp-empty-state"><strong>{isBlankTemplate ? "产品与案例尚未录入" : "暂无已发布的业务内容"}</strong><p>{isBlankTemplate ? "导入甲方产品、服务与获授权案例后，这里会形成可检索的业务广场。" : "当前静态页面尚未连接企业业务目录。"}</p>{isBlankTemplate && <a href={onboardingHref}>添加企业业务资料</a>}</div>
        ) : catalog.status === "error" ? (
          <div className="bp-empty-state" role="alert"><strong>暂时无法读取业务资料</strong><p>{catalog.message}</p>{assistantAvailable && <button type="button" onClick={() => onAssistant("请介绍目前已发布的业务资料")}>改为向 AI 了解</button>}</div>
        ) : (
          <>
            {visibleProducts.length > 0 && <Section title="产品与服务"><div className="bp-list">{visibleProducts.map((product) => <button type="button" key={product.slug} onClick={() => openDetail({ kind: "product", item: product })}><i>◇</i><span><strong>{product.name}</strong><small>{product.category || "产品与服务"} · {product.summary}</small></span><Arrow /></button>)}</div></Section>}
            {visibleCases.length > 0 && <Section title="公开案例"><div className="bp-list">{visibleCases.map((item) => <button type="button" key={item.slug} onClick={() => openDetail({ kind: "case", item })}><i>▦</i><span><strong>{item.title}</strong><small>{item.industry || "公开案例"} · {item.result}</small></span><Arrow /></button>)}</div></Section>}
            {!visibleProducts.length && !visibleCases.length && <div className="bp-empty-state"><strong>没有找到匹配内容</strong><p>{assistantAvailable ? "可以换一个关键词，或直接向 AI 助手提问。" : "可以换一个关键词，或提交合作需求等待人工联系。"}</p>{assistantAvailable && <button type="button" onClick={() => onAssistant(query || "请介绍企业当前业务")}>向 AI 提问</button>}</div>}
          </>
        )}

        {recommendations.length > 0 && <Section title="可解释推荐"><div className="bp-list">{recommendations.map((item) => {
          const target = recommendationTarget(item);
          const route = recommendationRoute(item);
          const canOpen = Boolean(target || route);
          return <button type="button" key={`${item.resourceType}-${item.resourceId}`} disabled={!canOpen && !assistantAvailable} onClick={() => target ? openDetail(target) : route ? openDetailRoute(route) : onAssistant(`请介绍${item.title}`)}><span><strong>{item.title}</strong><small>{item.reason} · 依据：{item.evidence.excerpt} · {canOpen ? "打开已发布详情" : "向 AI 了解"}</small></span><Arrow /></button>;
        })}</div></Section>}
      </main>
      {!isStandaloneCard && bottom}
    </>
  );

  const mePage = (
    <>
      <AppHeader title="我的名片关系" onShare={onShare} />
      <main className="bp-page">
        <div className="bp-me-head"><Avatar label={isBlankTemplate ? "＋" : displayName} src={avatar} /><div><h1>{isBlankTemplate ? "空白企业模板" : saved ? "已保存这张名片" : "尚未保存名片"}</h1><p>{isBlankTemplate ? "等待装入甲方企业资料" : `${companyName} · ${displayName}`}</p></div></div>
        <Section title="名片操作"><div className="bp-list">
          {!isBlankTemplate && <button type="button" onClick={toggleSaved}><span className="bp-list-icon"><BookmarkSimpleIcon size={19} weight={saved ? "fill" : "regular"} /></span><span><strong>{saved ? "取消保存" : "保存到本设备"}</strong><small>仅保存在当前浏览器，不会上传通讯录</small></span><Arrow /></button>}
          <button type="button" onClick={onShare}><span className="bp-list-icon"><ShareNetworkIcon size={19} /></span><span><strong>分享名片</strong><small>生成二维码或复制当前公开链接</small></span><Arrow /></button>
          {isBlankTemplate ? <a className="bp-list-link" href={onboardingHref}><span className="bp-list-icon"><BuildingsIcon size={19} /></span><span><strong>开始配置企业</strong><small>录入甲方资料并生成可审核预览</small></span><Arrow /></a> : <button type="button" onClick={onLead}><span className="bp-list-icon"><PaperPlaneTiltIcon size={19} /></span><span><strong>提交合作需求</strong><small>提交前会单独征得联系授权</small></span><Arrow /></button>}
        </div></Section>

        <Section title="官方联系方式"><div className="bp-list">
          {websiteHref && <a className="bp-list-link" href={websiteHref} target="_blank" rel="noreferrer"><span className="bp-list-icon"><BuildingsIcon size={19} /></span><span><strong>{websiteLabel}</strong><small>{websiteHref}</small></span><Arrow /></a>}
          {contactFields.map((field, index) => {
            const href = safeContactHref(field);
            const key = `${field.label}-${index}`;
            const feedback = copyFeedback?.key === key
              ? copyFeedback.status === "copied" ? "已复制" : "复制失败，请长按内容复制"
              : field.value;
            const content = <><span className="bp-list-icon"><ChatCircleDotsIcon size={19} /></span><span><strong>{field.label}</strong><small aria-live="polite">{feedback}</small></span><Arrow /></>;
            return href ? <a className="bp-list-link" href={href} key={key}>{content}</a> : <button type="button" key={key} onClick={() => void copyContact(key, field.value)}>{content}</button>;
          })}
          {!websiteHref && !contactFields.length && <p className="bp-page-note">企业暂未发布直接联系方式，可以提交合作需求等待联系。</p>}
        </div></Section>

        {card ? <Section title="隐私与授权"><div className="bp-list">
          <button type="button" onClick={onProfile}><span className="bp-list-icon"><IdentificationCardIcon size={19} /></span><span><strong>长期访客画像授权</strong><small>自主开启或撤回个性化关联</small></span><Arrow /></button>
          <button type="button" onClick={onPrivacy}><span className="bp-list-icon"><UserCircleIcon size={19} /></span><span><strong>个人信息权利</strong><small>访问、更正、删除数据或撤回授权</small></span><Arrow /></button>
        </div></Section> : !isBlankTemplate ? <Section title="隐私与授权"><p className="bp-page-note">当前为离线展示，公开名片服务恢复后可管理画像授权与个人信息权利。</p></Section> : null}

        <Section title="企业入口"><a className="bp-company-reco" href={isBlankTemplate ? onboardingHref : adminHref}>{companyLogo ? <img src={companyLogo} alt="" /> : <i aria-hidden="true">＋</i>}<span><strong>{isBlankTemplate ? "进入资料辅助建企" : "进入企业管理后台"}</strong><small>{isBlankTemplate ? "录入并审核甲方企业资料" : "仅企业员工和管理员可以登录"}</small></span><Arrow /></a></Section>
      </main>
      {bottom}
    </>
  );

  const detailPage = detail ? (
    <>
      <AppHeader back={returnFromDetail} title={detail.kind === "product" ? "产品与服务" : "公开案例"} onShare={onShare} />
      <main className="bp-page bp-detail-page">
        <p className="bp-detail-eyebrow">{detail.kind === "product" ? detail.item.category || "产品与服务" : detail.item.industry || "公开案例"}</p>
        <h1>{detail.kind === "product" ? detail.item.name : detail.item.title}</h1>
        {detail.item.imageUrl && <img className="bp-detail-image" src={detail.item.imageUrl} alt="" />}
        {detail.kind === "product" ? <>
          <Section title="业务简介"><p>{detail.item.summary}</p></Section>
          <Section title="详细说明"><p>{detail.item.detail}</p></Section>
          {detail.item.audience && <Section title="适用对象"><p>{detail.item.audience}</p></Section>}
          {detail.item.priceBoundary && <Section title="服务边界"><p>{detail.item.priceBoundary}</p></Section>}
        </> : <>
          <Section title="项目背景"><p>{detail.item.background}</p></Section>
          <Section title="解决方案"><p>{detail.item.solution}</p></Section>
          <Section title="项目结果"><p>{detail.item.result}</p></Section>
        </>}
        {assistantAvailable && <section className="bp-ai-card"><div><i>AI</i><span><strong>{assistantName}</strong><small>继续了解</small></span></div><button type="button" onClick={() => onAssistant(`请详细介绍${detail.kind === "product" ? detail.item.name : detail.item.title}`)}>向 AI 继续提问 <Arrow /></button></section>}
      </main>
      <div className="bp-sticky-actions bp-detail-actions"><button type="button" onClick={returnFromDetail}>返回</button><button className="primary" type="button" onClick={onLead}>留下合作需求</button></div>
    </>
  ) : requestedDetail ? (
    <>
      <AppHeader
        back={returnFromDetail}
        title={requestedDetail.kind === "product" ? "产品与服务" : "公开案例"}
        onShare={onShare}
      />
      <main className="bp-page bp-detail-page">
        {catalog.status === "loading" || (catalog.status === "ready" && (detailLookup.status === "idle" || detailLookup.status === "loading")) ? (
          <LoadingRows label="详情" />
        ) : catalog.status === "error" ? (
          <div className="bp-empty-state" role="alert">
            <strong>详情暂时无法加载</strong>
            <p>{catalog.message}</p>
            <button type="button" onClick={() => replaceWithView("square")}>返回业务广场</button>
          </div>
        ) : detailLookup.status === "error" ? (
          <div className="bp-empty-state" role="alert">
            <strong>详情暂时无法加载</strong>
            <p>{detailLookup.message}</p>
            <button type="button" onClick={() => replaceWithView("square")}>返回业务广场</button>
          </div>
        ) : catalog.status === "ready" && detailLookup.status === "missing" ? (
          <div className="bp-empty-state" role="alert">
            <strong>该内容不存在或已下线</strong>
            <p>链接对应的公开内容已更新，请返回业务广场查看当前已发布资料。</p>
            <button type="button" onClick={() => replaceWithView("square")}>返回业务广场</button>
          </div>
        ) : (
          <div className="bp-empty-state" role="alert">
            <strong>当前无法读取详情</strong>
            <p>公开业务目录尚未连接，请稍后重试或返回名片首页。</p>
            <button type="button" onClick={() => replaceWithView("card")}>返回名片</button>
          </div>
        )}
      </main>
    </>
  ) : null;

  const page = view === "card" ? cardPage : view === "company" ? companyPage : view === "square" ? squarePage : view === "me" ? mePage : detailPage ?? squarePage;

  return <div className={`bp-app bp-live-app bp-view-${view}${isStandaloneCard ? " bp-standalone-card" : ""}`}><div className="bp-phone-frame">{page}</div></div>;
}

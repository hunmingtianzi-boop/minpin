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
import { useEffect, useMemo, useState, type ReactNode } from "react";

import type { EnterpriseCardConfig } from "../domain/card";
import type { PublicCardData } from "../lib/publicCardApi";
import {
  fetchPublicCatalog,
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
type SquareFilter = "全部" | "产品" | "案例";
type DetailTarget =
  | { kind: "product"; item: PublicProduct; from: View }
  | { kind: "case"; item: PublicCaseStudy; from: View };
type DetailInput =
  | { kind: "product"; item: PublicProduct }
  | { kind: "case"; item: PublicCaseStudy };

type CatalogState =
  | { status: "idle" | "loading" }
  | { status: "ready"; data: PublicCatalog }
  | { status: "error"; message: string };

const publicViews: View[] = ["card", "company", "square", "me"];

function initialView(): View {
  const candidate = new URLSearchParams(window.location.search).get("view");
  return publicViews.includes(candidate as View) ? (candidate as View) : "card";
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
  const [view, setView] = useState<View>(initialView);
  const [detail, setDetail] = useState<DetailTarget | null>(null);
  const [catalog, setCatalog] = useState<CatalogState>({ status: "idle" });
  const [recommendations, setRecommendations] = useState<PublicRecommendation[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<SquareFilter>("全部");
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
  const companyName = card?.company.name ?? tenant.brand.name;
  const companySummary = card?.company.summary || tenant.hero.summary;
  const displayName = card?.display_name ?? tenant.brand.shortName;
  const title = card?.title ?? tenant.brand.headerDescriptor;
  const avatar = card?.avatar_url || undefined;
  const companyLogo = card?.company.logo_url || tenant.brand.logo.src;
  const assistantName = card?.ai_assistant.display_name ?? tenant.assistant.title;
  const assistantAvailable = card?.ai_assistant.available ?? true;
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
  const websiteHref = card?.company.website
    ? safeContactHref({ href: card.company.website })
    : safeContactHref({ href: tenant.brand.officialAction.target });
  const websiteLabel = card?.company.website
    ? `${companyName}官网`
    : tenant.brand.officialAction.label;
  const adminHref =
    import.meta.env.VITE_ADMIN_BASE_URL?.trim() || `${import.meta.env.BASE_URL}admin/`;

  const go = (next: View) => {
    setDetail(null);
    setView(next);
    const url = new URL(window.location.href);
    if (next === "card") url.searchParams.delete("view");
    else url.searchParams.set("view", next);
    window.history.replaceState({}, "", url);
    const frame = document.querySelector<HTMLElement>(".bp-phone-frame");
    if (typeof frame?.scrollTo === "function") {
      frame.scrollTo({ top: 0, behavior: "smooth" });
    }
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  };

  const openDetail = (target: DetailInput) => {
    if (target.kind === "product") {
      setDetail({ kind: "product", item: target.item, from: view });
    } else {
      setDetail({ kind: "case", item: target.item, from: view });
    }
    setView("detail");
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

  const bottom = (
    <nav className="bp-bottom-nav" aria-label="名片导航">
      {([
        ["名片", "card"],
        ["业务", "square"],
        ["企业", "company"],
        ["我的", "me"],
      ] as Array<[string, View]>).map(([label, target]) => (
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
              <b><SealCheckIcon size={17} weight="fill" /> 已发布</b>
            </div>
            <p>{title}</p>
            <button className="bp-affiliation" type="button" onClick={() => go("company")}>
              <BuildingsIcon size={18} weight="fill" /> {companyName} <Arrow />
            </button>
            <div className="bp-tags">
              {tags.map((tag) => <span key={tag}>{tag}</span>)}
            </div>
          </div>
        </div>

        <section className="bp-card-intro">
          <div className="bp-card-panel-title"><h2>业务介绍</h2></div>
          <div className="bp-intro">
            {introParagraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
            <button type="button" className="bp-text-button" onClick={() => go("company")}>
              查看企业详情 <Arrow />
            </button>
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
          <div><i>AI</i><span><strong>{assistantName}</strong><small>{assistantAvailable ? "基于已发布资料" : "暂未开放"}</small></span></div>
          <p>{assistantAvailable ? (card?.ai_assistant.disclosure || "回答会引用企业已发布知识，重要事项请与企业进一步确认。") : "企业尚未开放 AI 问答，请先通过合作需求与企业联系。"}</p>
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
        </section>
      </main>
      <div className="bp-sticky-actions bp-card-actions">
        <button type="button" onClick={toggleSaved} aria-pressed={saved}>
          <BookmarkSimpleIcon size={22} weight={saved ? "fill" : "regular"} />
          {saved ? "已保存" : "保存名片"}
        </button>
        <button className="primary" type="button" onClick={onLead}>
          <HandshakeIcon size={22} /> 发起合作
        </button>
      </div>
    </>
  );

  const companyPage = (
    <>
      <AppHeader back={() => go("card")} title={`来自${displayName}的名片`} onShare={onShare} />
      <main className="bp-page bp-company-page">
        <div className="bp-company-head">
          {companyLogo ? <img src={companyLogo} alt={`${companyName}标识`} /> : <i>◈</i>}
          <div>
            <div className="bp-name-line"><h1>{companyName}</h1><b>✓ 资料已发布</b></div>
            <p>{companySummary}</p>
            <small className="bp-company-meta">
              {[card?.company.industry, card?.company.region].filter(Boolean).join(" · ") || tenant.brand.headerDescriptor}
            </small>
            <div className="bp-tags">{tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
          </div>
        </div>

        <section className="bp-company-position">
          <small>我们能帮助你</small>
          <strong>{tenant.hero.summary}</strong>
        </section>

        <Section title="企业介绍"><div className="bp-intro"><p>{companySummary}</p></div></Section>

        <Section title="核心业务">
          {catalog.status === "loading" ? <LoadingRows label="业务资料" /> : (
            <div className="bp-list">
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
            </div>
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
          <div className="bp-trust">
            <span>✓ 企业公开资料</span><span>✓ AI 引用可追溯</span>
            {(card?.company.industry || card?.company.region) && <span>{[card.company.industry, card.company.region].filter(Boolean).join(" · ")}</span>}
            {websiteHref && <a className="bp-trust-link" href={websiteHref} target="_blank" rel="noreferrer">访问企业官网 <Arrow /></a>}
          </div>
        </Section>

        <Section title="可以为你对接的人">
          <div className="bp-people">
            <button type="button" onClick={() => go("card")}>
              <Avatar small label={displayName} src={avatar} />
              <span><strong>{displayName}　{title}</strong><small>{companyName}</small></span><Arrow />
            </button>
          </div>
        </Section>

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
          <div><i>AI</i><span><strong>{assistantName}</strong><small>{assistantAvailable ? "基于已发布资料" : "暂未开放"}</small></span></div>
          <p>{assistantAvailable ? (card?.ai_assistant.welcome_message || "我可以介绍企业能力、解释常见问题，并帮助整理合作需求。") : "企业尚未开放 AI 问答，可提交合作需求等待人工联系。"}</p>
          {assistantAvailable && <button type="button" onClick={() => onAssistant()}>咨询适合我们的解决方案 <Arrow /></button>}
        </section>
      </main>
      <div className="bp-sticky-actions bp-company-actions">
        <button type="button" onClick={toggleSaved}>{saved ? "✓ 已保存企业名片" : "⌑ 保存企业名片"}</button>
        <button className="primary" type="button" onClick={onLead}>⌁ 发起合作</button>
      </div>
      {bottom}
    </>
  );

  const squarePage = (
    <>
      <AppHeader title="业务广场" onShare={onShare} />
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

        {catalog.status === "loading" || catalog.status === "idle" ? <LoadingRows label="公开内容" /> : catalog.status === "error" ? (
          <div className="bp-empty-state" role="alert"><strong>暂时无法读取业务资料</strong><p>{catalog.message}</p>{assistantAvailable && <button type="button" onClick={() => onAssistant("请介绍目前已发布的业务资料")}>改为向 AI 了解</button>}</div>
        ) : (
          <>
            {visibleProducts.length > 0 && <Section title="产品与服务"><div className="bp-list">{visibleProducts.map((product) => <button type="button" key={product.slug} onClick={() => openDetail({ kind: "product", item: product })}><i>◇</i><span><strong>{product.name}</strong><small>{product.category || "产品与服务"} · {product.summary}</small></span><Arrow /></button>)}</div></Section>}
            {visibleCases.length > 0 && <Section title="公开案例"><div className="bp-list">{visibleCases.map((item) => <button type="button" key={item.slug} onClick={() => openDetail({ kind: "case", item })}><i>▦</i><span><strong>{item.title}</strong><small>{item.industry || "公开案例"} · {item.result}</small></span><Arrow /></button>)}</div></Section>}
            {!visibleProducts.length && !visibleCases.length && <div className="bp-empty-state"><strong>没有找到匹配内容</strong><p>{assistantAvailable ? "可以换一个关键词，或直接向 AI 助手提问。" : "可以换一个关键词，或提交合作需求等待人工联系。"}</p>{assistantAvailable && <button type="button" onClick={() => onAssistant(query || "请介绍企业当前业务")}>向 AI 提问</button>}</div>}
          </>
        )}

        {recommendations.length > 0 && <Section title="可解释推荐"><div className="bp-list">{recommendations.map((item) => <button type="button" key={`${item.resourceType}-${item.resourceId}`} disabled={!assistantAvailable} onClick={() => onAssistant(`请介绍${item.title}`)}><span><strong>{item.title}</strong><small>{item.reason} · 依据：{item.evidence.excerpt}</small></span><Arrow /></button>)}</div></Section>}
      </main>
      {bottom}
    </>
  );

  const mePage = (
    <>
      <AppHeader title="我的名片关系" onShare={onShare} />
      <main className="bp-page">
        <div className="bp-me-head"><Avatar label={displayName} src={avatar} /><div><h1>{saved ? "已保存这张名片" : "尚未保存名片"}</h1><p>{companyName} · {displayName}</p></div></div>
        <Section title="名片操作"><div className="bp-list">
          <button type="button" onClick={toggleSaved}><span className="bp-list-icon"><BookmarkSimpleIcon size={19} weight={saved ? "fill" : "regular"} /></span><span><strong>{saved ? "取消保存" : "保存到本设备"}</strong><small>仅保存在当前浏览器，不会上传通讯录</small></span><Arrow /></button>
          <button type="button" onClick={onShare}><span className="bp-list-icon"><ShareNetworkIcon size={19} /></span><span><strong>分享名片</strong><small>生成二维码或复制当前公开链接</small></span><Arrow /></button>
          <button type="button" onClick={onLead}><span className="bp-list-icon"><PaperPlaneTiltIcon size={19} /></span><span><strong>提交合作需求</strong><small>提交前会单独征得联系授权</small></span><Arrow /></button>
        </div></Section>

        <Section title="官方联系方式"><div className="bp-list">
          {websiteHref && <a className="bp-list-link" href={websiteHref} target="_blank" rel="noreferrer"><span className="bp-list-icon"><BuildingsIcon size={19} /></span><span><strong>{websiteLabel}</strong><small>{websiteHref}</small></span><Arrow /></a>}
          {contactFields.map((field, index) => {
            const href = safeContactHref(field);
            const content = <><span className="bp-list-icon"><ChatCircleDotsIcon size={19} /></span><span><strong>{field.label}</strong><small>{field.value}</small></span><Arrow /></>;
            return href ? <a className="bp-list-link" href={href} key={`${field.label}-${index}`}>{content}</a> : <button type="button" key={`${field.label}-${index}`} onClick={() => void navigator.clipboard?.writeText(field.value)}>{content}</button>;
          })}
          {!websiteHref && !contactFields.length && <p className="bp-page-note">企业暂未发布直接联系方式，可以提交合作需求等待联系。</p>}
        </div></Section>

        <Section title="隐私与授权"><div className="bp-list">
          <button type="button" onClick={onProfile}><span className="bp-list-icon"><IdentificationCardIcon size={19} /></span><span><strong>长期访客画像授权</strong><small>自主开启或撤回个性化关联</small></span><Arrow /></button>
          <button type="button" onClick={onPrivacy}><span className="bp-list-icon"><UserCircleIcon size={19} /></span><span><strong>个人信息权利</strong><small>访问、更正、删除数据或撤回授权</small></span><Arrow /></button>
        </div></Section>

        <Section title="企业入口"><a className="bp-company-reco" href={adminHref}><img src={companyLogo} alt="" /><span><strong>进入企业管理后台</strong><small>仅企业员工和管理员可以登录</small></span><Arrow /></a></Section>
      </main>
      {bottom}
    </>
  );

  const detailPage = detail ? (
    <>
      <AppHeader back={() => go(detail.from === "detail" ? "square" : detail.from)} title={detail.kind === "product" ? "产品与服务" : "公开案例"} onShare={onShare} />
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
      <div className="bp-sticky-actions"><button type="button" onClick={() => go(detail.from)}>返回</button><button className="primary" type="button" onClick={onLead}>留下合作需求</button></div>
    </>
  ) : null;

  const page = view === "card" ? cardPage : view === "company" ? companyPage : view === "square" ? squarePage : view === "me" ? mePage : detailPage;

  return <div className="bp-app bp-live-app"><div className="bp-phone-frame">{page}</div></div>;
}

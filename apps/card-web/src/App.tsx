import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  BookOpenText,
  Buildings,
  CalendarDots,
  CheckCircle,
  CirclesThreePlus,
  Code,
  GlobeHemisphereEast,
  Handshake,
  List,
  Path,
  RocketLaunch,
  Student,
  Target,
  UsersThree,
  X,
} from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import { type PropsWithChildren, useEffect, useMemo, useRef, useState } from "react";

import {
  AIAssistant,
  type AIAssistantHandle,
} from "./components/AIAssistant";
import { ThemeControl } from "./components/ThemeControl";
import type {
  BaseSection,
  CardAction,
  EnterpriseCardConfig,
  EnterpriseCardSection,
} from "./domain/card";

import "./styles.css";

const iconMap = {
  globe: GlobeHemisphereEast,
  path: Path,
  rocket: RocketLaunch,
  calendar: CalendarDots,
  book: BookOpenText,
  code: Code,
  student: Student,
  buildings: Buildings,
  users: UsersThree,
};

function getIcon(token: string) {
  return iconMap[token as keyof typeof iconMap] ?? CirclesThreePlus;
}

function Reveal({
  children,
  className = "",
  delay = 0,
}: PropsWithChildren<{ className?: string; delay?: number }>) {
  const shouldReduceMotion = useReducedMotion();

  return (
    <motion.div
      className={className}
      initial={shouldReduceMotion ? false : { opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.18 }}
      transition={{ duration: 0.56, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

function SectionHeading({
  section,
  headingId,
}: {
  section: Pick<BaseSection, "eyebrow" | "heading" | "description">;
  headingId: string;
}) {
  return (
    <div className="section-heading">
      {section.eyebrow && <p className="section-eyebrow">{section.eyebrow}</p>}
      <h2 id={headingId}>{section.heading}</h2>
      {section.description && <p className="section-description">{section.description}</p>}
    </div>
  );
}

function ActionControl({
  action,
  className,
  onAssistant,
  icon = "right",
}: {
  action: CardAction;
  className: string;
  onAssistant: (target: string) => void;
  icon?: "down" | "right" | "up";
}) {
  const Icon = icon === "down" ? ArrowDownRight : icon === "up" ? ArrowUpRight : ArrowRight;
  const content = (
    <>
      {action.label}
      <Icon size={18} weight="bold" aria-hidden="true" />
    </>
  );

  if (action.kind === "assistant") {
    return (
      <button className={className} type="button" onClick={() => onAssistant(action.target)}>
        {content}
      </button>
    );
  }

  return (
    <a
      className={className}
      href={action.target}
      target={action.kind === "external" ? "_blank" : undefined}
      rel={action.kind === "external" ? "noreferrer" : undefined}
    >
      {content}
    </a>
  );
}

function Header({
  tenant,
  navItems,
}: {
  tenant: EnterpriseCardConfig;
  navItems: EnterpriseCardSection[];
}) {
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!mobileOpen) return undefined;

    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [mobileOpen]);

  return (
    <header className="site-header">
      <div className="header-inner">
        <a
          className="brand-lockup"
          href={`#${tenant.hero.id}`}
          aria-label={tenant.brand.homeAriaLabel}
        >
          <img
            src={tenant.brand.logo.src}
            alt={tenant.brand.logo.alt}
            width="42"
            height="42"
          />
          <span>
            <strong className="brand-name-full">{tenant.brand.name}</strong>
            <strong className="brand-name-short">{tenant.brand.shortName}</strong>
            <small>{tenant.brand.headerDescriptor}</small>
          </span>
        </a>

        <nav className="desktop-nav" aria-label="主导航">
          {navItems.map((item) => (
            <a href={`#${item.id}`} key={item.id}>
              {item.navLabel}
            </a>
          ))}
        </nav>

        <div className="header-actions">
          <ThemeControl
            storageKey={`cf-card-theme:${tenant.id}`}
            defaultMode={tenant.theme.defaultMode}
            lightThemeColor={tenant.theme.light.background}
            darkThemeColor={tenant.theme.dark.background}
          />
          <a
            className="official-link"
            href={tenant.brand.officialAction.target}
            target="_blank"
            rel="noreferrer"
          >
            {tenant.brand.officialAction.label}
            <ArrowUpRight size={15} weight="bold" aria-hidden="true" />
          </a>
          <button
            className="mobile-menu-button"
            type="button"
            onClick={() => setMobileOpen((current) => !current)}
            aria-expanded={mobileOpen}
            aria-controls="mobile-navigation"
            aria-label={mobileOpen ? "关闭导航" : "打开导航"}
          >
            {mobileOpen ? <X size={21} /> : <List size={22} />}
          </button>
        </div>
      </div>

      {mobileOpen && (
        <>
          <button
            className="mobile-nav-backdrop"
            type="button"
            aria-label="关闭导航"
            onClick={() => setMobileOpen(false)}
          />
          <nav id="mobile-navigation" className="mobile-nav" aria-label="移动端导航">
            {navItems.map((item) => (
              <a href={`#${item.id}`} key={item.id} onClick={() => setMobileOpen(false)}>
                {item.navLabel}
                <ArrowDownRight size={17} aria-hidden="true" />
              </a>
            ))}
          </nav>
        </>
      )}
    </header>
  );
}

function CardSection({
  section,
  tenant,
  onAssistant,
}: {
  section: EnterpriseCardSection;
  tenant: EnterpriseCardConfig;
  onAssistant: (target: string) => void;
}) {
  const headingId = `${section.id}-title`;

  switch (section.type) {
    case "feature-grid":
      return (
        <section
          className="section feature-section"
          id={section.id}
          aria-labelledby={headingId}
        >
          <div className="page-width">
            <Reveal>
              <SectionHeading section={section} headingId={headingId} />
            </Reveal>

            <div className={`feature-grid feature-count-${section.businesses.length}`}>
              {section.businesses.map((business, index) => {
                const Icon = getIcon(business.icon);
                return (
                  <Reveal
                    className={`feature-card feature-card-${index + 1}`}
                    delay={index * 0.08}
                    key={`${business.title}-${index}`}
                  >
                    <div className="feature-card-top">
                      <span className="feature-icon" aria-hidden="true">
                        <Icon size={24} weight="duotone" />
                      </span>
                    </div>
                    <p className="feature-eyebrow">{business.eyebrow}</p>
                    <h3>{business.title}</h3>
                    <p className="feature-description">{business.description}</p>
                    <ul>
                      {business.points.map((point) => (
                        <li key={point}>{point}</li>
                      ))}
                    </ul>
                    <div className="feature-status">
                      <CheckCircle size={16} weight="fill" aria-hidden="true" />
                      {business.status}
                    </div>
                  </Reveal>
                );
              })}
            </div>
          </div>
        </section>
      );

    case "media-showcase":
      return (
        <section
          className="section showcase-section"
          id={section.id}
          aria-labelledby={headingId}
        >
          <div className="page-width showcase-layout">
            <Reveal className="showcase-copy">
              <SectionHeading section={section} headingId={headingId} />
              <div className="capability-list">
                {section.capabilities.map((capability) => {
                  const Icon = getIcon(capability.icon);
                  return (
                    <div key={capability.title}>
                      <Icon size={22} weight="duotone" aria-hidden="true" />
                      <span>
                        <strong>{capability.title}</strong>
                        <small>{capability.description}</small>
                      </span>
                    </div>
                  );
                })}
              </div>
              <ActionControl
                action={section.action}
                className="text-link"
                onAssistant={onAssistant}
                icon="up"
              />
            </Reveal>

            <Reveal className="showcase-visual" delay={0.12}>
              <div className="visual-label">
                <strong>{section.visualTitle}</strong>
                <span>{section.visualLabel}</span>
              </div>
              <figure>
                <img
                  src={section.visual.src}
                  alt={section.visual.alt}
                  width={section.visual.width}
                  height={section.visual.height}
                  loading="lazy"
                  decoding="async"
                />
                {section.visual.caption && (
                  <figcaption>{section.visual.caption}</figcaption>
                )}
              </figure>
            </Reveal>
          </div>
        </section>
      );

    case "process":
      return (
        <section
          className="section process-section"
          id={section.id}
          aria-labelledby={headingId}
        >
          <div className="page-width">
            <Reveal>
              <SectionHeading section={section} headingId={headingId} />
            </Reveal>

            <Reveal className="process-track" delay={0.08}>
              {section.steps.map((step, index) => (
                <article key={`${step.title}-${index}`}>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </article>
              ))}
            </Reveal>

            {section.audiences.length > 0 && (
              <Reveal className="audience-ledger" delay={0.1}>
                <div className="ledger-intro">
                  <h3>{section.audienceHeading}</h3>
                </div>
                {section.audiences.map((audience) => {
                  const Icon = getIcon(audience.icon);
                  return (
                    <div className="ledger-row" key={audience.title}>
                      <Icon size={24} weight="duotone" aria-hidden="true" />
                      <strong>{audience.title}</strong>
                      <p>{audience.description}</p>
                    </div>
                  );
                })}
              </Reveal>
            )}
          </div>
        </section>
      );

    case "evidence":
      return (
        <section
          className="section evidence-section"
          id={section.id}
          aria-labelledby={headingId}
        >
          <div className="page-width">
            <div className="evidence-layout">
              <Reveal className="evidence-visual">
                <figure>
                  <img
                    src={section.visual.src}
                    alt={section.visual.alt}
                    width={section.visual.width}
                    height={section.visual.height}
                    loading="lazy"
                    decoding="async"
                  />
                  {section.visual.caption && (
                    <figcaption>{section.visual.caption}</figcaption>
                  )}
                </figure>
                <div className="evidence-metric">
                  <strong>{section.headlineMetric}</strong>
                  <span>{section.metricDescription}</span>
                </div>
              </Reveal>

              <Reveal className="evidence-copy" delay={0.12}>
                <SectionHeading section={section} headingId={headingId} />
                <div className="theme-lines" aria-label={section.themesAriaLabel}>
                  {section.themes.map((theme) => (
                    <span key={theme}>{theme}</span>
                  ))}
                </div>
                <p className="content-caveat">
                  <Target size={19} weight="duotone" aria-hidden="true" />
                  {section.caveat}
                </p>
              </Reveal>
            </div>

            {section.supportNames.length > 0 && (
              <Reveal className="support-strip" delay={0.08}>
                <div>
                  <p>{section.supportHeading}</p>
                  <small>{section.supportNote}</small>
                </div>
                <ul>
                  {section.supportNames.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
              </Reveal>
            )}
          </div>
        </section>
      );

    case "engagement":
      return (
        <section
          className="engagement-section"
          id={section.id}
          aria-labelledby={headingId}
        >
          <div className="page-width">
            <Reveal>
              <SectionHeading section={section} headingId={headingId} />
            </Reveal>

            <Reveal className="engagement-flow" delay={0.08}>
              {section.steps.map((step, index) => (
                <article key={`${step.title}-${index}`}>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </article>
              ))}
            </Reveal>

            <Reveal className="engagement-cta" delay={0.12}>
              <div>
                <Handshake size={31} weight="duotone" aria-hidden="true" />
                <span>
                  <strong>{section.cta.title}</strong>
                  <small>{section.cta.description}</small>
                </span>
              </div>
              <ActionControl
                action={section.cta.action}
                className="button button-primary"
                onAssistant={onAssistant}
              />
            </Reveal>
          </div>
        </section>
      );

    case "faq": {
      const faqItems = section.itemIds
        .map((id) => tenant.assistant.knowledgeBase.find((item) => item.id === id))
        .filter((item) => item !== undefined);

      return (
        <section
          className="section faq-section"
          id={section.id}
          aria-labelledby={headingId}
        >
          <div className="page-width faq-layout">
            <Reveal className="faq-intro">
              <SectionHeading section={section} headingId={headingId} />
              {section.action && (
                <ActionControl
                  action={section.action}
                  className="button button-secondary"
                  onAssistant={onAssistant}
                />
              )}
            </Reveal>

            <Reveal className="faq-list" delay={0.08}>
              {faqItems.map((item, index) => (
                <details key={item.id} open={index === 0}>
                  <summary>
                    {item.question}
                    <i aria-hidden="true" />
                  </summary>
                  <div>
                    <p>{item.answer}</p>
                    <small>
                      {tenant.assistant.labels.sourcePrefix}
                      {item.source}
                    </small>
                  </div>
                </details>
              ))}
            </Reveal>
          </div>
        </section>
      );
    }

    case "closing":
      return (
        <section
          className="closing-section"
          id={section.id}
          aria-labelledby={headingId}
        >
          <div className="closing-art" aria-hidden="true">
            <img
              src={section.art.src}
              alt=""
              width={section.art.width}
              height={section.art.height}
              loading="lazy"
              decoding="async"
            />
          </div>
          <div className="page-width closing-content">
            <Reveal>
              <h2 id={headingId}>{section.heading}</h2>
              {section.description && <p>{section.description}</p>}
              <div className="closing-actions">
                {section.actions.map((action, index) => (
                  <ActionControl
                    key={`${action.kind}-${action.label}`}
                    action={action}
                    className={`button ${index === 0 ? "button-primary" : "button-secondary"}`}
                    onAssistant={onAssistant}
                    icon={action.kind === "external" ? "up" : "right"}
                  />
                ))}
              </div>
            </Reveal>
          </div>
        </section>
      );
  }
}

export default function App({ tenant }: { tenant: EnterpriseCardConfig }) {
  const assistantRef = useRef<AIAssistantHandle>(null);
  const shouldReduceMotion = useReducedMotion();

  const navItems = useMemo(
    () => tenant.sections.filter((section) => section.showInNav),
    [tenant.sections],
  );

  const openAssistant = (target: string) => {
    if (target === "open") assistantRef.current?.open();
    else assistantRef.current?.openWithQuestion(target);
  };

  return (
    <div className="app-shell" data-tenant={tenant.id}>
      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
      <Header tenant={tenant} navItems={navItems} />

      <main id="main-content">
        <section
          className="hero"
          id={tenant.hero.id}
          aria-labelledby="hero-title"
        >
          <div className="hero-art" aria-hidden="true">
            <img
              src={tenant.hero.art.src}
              alt=""
              width={tenant.hero.art.width}
              height={tenant.hero.art.height}
              fetchPriority="high"
              decoding="async"
            />
          </div>
          <div className="hero-inner page-width">
            <motion.div
              className="hero-copy"
              initial={shouldReduceMotion ? false : { opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            >
              <p className="hero-kicker">{tenant.hero.kicker}</p>
              <h1 id="hero-title">
                {tenant.hero.titleLines.map((line, index) => (
                  <span key={line}>
                    {line}
                    {index < tenant.hero.titleLines.length - 1 && <br />}
                  </span>
                ))}
              </h1>
              <p className="hero-summary">{tenant.hero.summary}</p>
              <div className="hero-actions">
                {tenant.hero.actions.map((action, index) => (
                  <ActionControl
                    key={`${action.kind}-${action.label}`}
                    action={action}
                    className={`button ${index === 0 ? "button-primary" : "button-ghost"}`}
                    onAssistant={openAssistant}
                    icon={index === 0 ? "down" : "right"}
                  />
                ))}
              </div>
            </motion.div>

            {tenant.hero.metrics.length > 0 && (
              <motion.dl
                className="hero-metrics"
                initial={shouldReduceMotion ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.8, delay: 0.25 }}
              >
                {tenant.hero.metrics.map((metric) => (
                  <div key={metric.label}>
                    <dt>{metric.label}</dt>
                    <dd>{metric.value}</dd>
                    <small>{metric.note}</small>
                  </div>
                ))}
              </motion.dl>
            )}
          </div>
        </section>

        {tenant.sections.map((section) => (
          <CardSection
            key={section.id}
            section={section}
            tenant={tenant}
            onAssistant={openAssistant}
          />
        ))}
      </main>

      <footer className="site-footer">
        <div className="page-width footer-inner">
          <div className="footer-brand">
            <img
              src={tenant.brand.logo.src}
              alt=""
              width="44"
              height="44"
              loading="lazy"
              decoding="async"
            />
            <span>
              <strong>{tenant.brand.name}</strong>
              <small>{tenant.footer.brandNote}</small>
            </span>
          </div>
          <p>{tenant.footer.disclaimer}</p>
          <ActionControl
            action={tenant.footer.backToTopAction}
            className="footer-top-link"
            onAssistant={openAssistant}
            icon="up"
          />
        </div>
      </footer>

      <AIAssistant
        key={tenant.id}
        ref={assistantRef}
        config={tenant.assistant}
        cardSlug={tenant.id}
      />
    </div>
  );
}

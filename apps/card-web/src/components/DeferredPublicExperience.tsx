import { PaperPlaneTilt, ShareNetwork } from "@phosphor-icons/react";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

import type { PublicCardData } from "../lib/publicCardApi";
import type { PublicExperienceHandle } from "./PublicExperience";

type PublicExperienceComponent =
  typeof import("./PublicExperience").PublicExperience;
type PendingAction = "lead" | "privacy" | "profile" | "share";

let publicExperienceModulePromise: Promise<PublicExperienceComponent> | undefined;

function loadPublicExperienceModule() {
  publicExperienceModulePromise ??= import("./PublicExperience")
    .then((module) => module.PublicExperience)
    .catch((error: unknown) => {
      publicExperienceModulePromise = undefined;
      throw error;
    });
  return publicExperienceModulePromise;
}

export type { PublicExperienceHandle };

export const DeferredPublicExperience = forwardRef<
  PublicExperienceHandle,
  {
    card: PublicCardData;
    controllerOnly?: boolean;
    onAssistant: (question: string) => void;
  }
>(function DeferredPublicExperience({ card, controllerOnly = false, onAssistant }, ref) {
  const [Component, setComponent] = useState<PublicExperienceComponent | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const sentinelRef = useRef<HTMLElement>(null);
  const innerRef = useRef<PublicExperienceHandle>(null);
  const pendingAction = useRef<PendingAction | null>(null);
  const mounted = useRef(true);
  const autoLoadAttempted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const activate = useCallback(async () => {
    if (Component || isLoading) return;
    setIsLoading(true);
    setLoadFailed(false);
    try {
      const loaded = await loadPublicExperienceModule();
      if (mounted.current) setComponent(() => loaded);
    } catch {
      if (mounted.current) setLoadFailed(true);
    } finally {
      if (mounted.current) setIsLoading(false);
    }
  }, [Component, isLoading]);

  useEffect(() => {
    if (controllerOnly) {
      if (autoLoadAttempted.current || Component) return undefined;
      autoLoadAttempted.current = true;
      void activate();
      return undefined;
    }
    const sentinel = sentinelRef.current;
    if (!sentinel || Component || autoLoadAttempted.current) return undefined;
    if (typeof IntersectionObserver === "undefined") {
      const timer = window.setTimeout(() => {
        autoLoadAttempted.current = true;
        void activate();
      }, 1200);
      return () => window.clearTimeout(timer);
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        observer.disconnect();
        autoLoadAttempted.current = true;
        void activate();
      },
      { rootMargin: "700px 0px", threshold: 0 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [Component, activate, controllerOnly]);

  const queueAction = useCallback(
    (action: PendingAction) => {
      pendingAction.current = action;
      if (innerRef.current) {
        if (action === "lead") innerRef.current.openLead();
        else if (action === "privacy") innerRef.current.openPrivacy();
        else if (action === "profile") innerRef.current.openProfile();
        else innerRef.current.openShare();
        pendingAction.current = null;
        return;
      }
      void activate();
    },
    [activate],
  );

  useEffect(() => {
    if (!Component || !innerRef.current || !pendingAction.current) return;
    const action = pendingAction.current;
    pendingAction.current = null;
    if (action === "lead") innerRef.current.openLead();
    else if (action === "privacy") innerRef.current.openPrivacy();
    else if (action === "profile") innerRef.current.openProfile();
    else innerRef.current.openShare();
  }, [Component]);

  useImperativeHandle(
    ref,
    () => ({
      openLead: () => queueAction("lead"),
      openPrivacy: () => queueAction("privacy"),
      openProfile: () => queueAction("profile"),
      openShare: () => queueAction("share"),
    }),
    [queueAction],
  );

  if (Component) {
    return (
      <Component
        ref={innerRef}
        card={card}
        controllerOnly={controllerOnly}
        onAssistant={onAssistant}
      />
    );
  }

  if (controllerOnly) {
    return loadFailed ? (
      <div className="public-controller-error" role="alert">
        <span>互动功能加载失败</span>
        <button type="button" onClick={() => void activate()}>
          重新加载
        </button>
      </div>
    ) : (
      <span ref={sentinelRef} hidden aria-hidden="true" />
    );
  }

  return (
    <section
      ref={sentinelRef}
      className="section public-experience public-experience-placeholder"
      id="catalog"
      aria-labelledby="catalog-title"
      aria-busy={isLoading || undefined}
    >
      <div className="page-width">
        <div className="public-experience-heading">
          <div className="section-heading">
            <p className="section-eyebrow">已发布业务资料</p>
            <h2 id="catalog-title">
              产品、案例与<br className="catalog-title-break" />下一步合作
            </h2>
            <p className="section-description">
              查看企业当前公开内容，也可以直接咨询、分享或提交合作需求。
            </p>
          </div>
          <div className="public-quick-actions">
            <button
              className="button button-secondary"
              type="button"
              onClick={() => queueAction("share")}
            >
              <ShareNetwork size={18} aria-hidden="true" />
              分享名片
            </button>
            <button
              className="button button-primary"
              type="button"
              onClick={() => queueAction("lead")}
            >
              <PaperPlaneTilt size={18} aria-hidden="true" />
              留下需求
            </button>
          </div>
        </div>
        <div className="deferred-catalog-state" role={loadFailed ? "alert" : "status"}>
          <span aria-hidden="true" />
          <span aria-hidden="true" />
          <span aria-hidden="true" />
          <p>
            {loadFailed
              ? "业务资料组件加载失败，请重试。"
              : isLoading
                ? "正在加载产品与案例"
                : "继续浏览后加载产品与案例"}
          </p>
          {loadFailed && (
            <button type="button" onClick={() => void activate()}>
              重新加载
            </button>
          )}
        </div>
      </div>
    </section>
  );
});

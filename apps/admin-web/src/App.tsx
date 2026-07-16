import { Button } from "@fluentui/react-components";
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { ApiError } from "./api/client";
import { platformApi } from "./api/platformApi";
import type {
  ConfirmPlatformOnboardingInput,
  PlatformLlmProfile as ApiPlatformLlmProfile,
  PlatformOnboardingSession,
  StartPlatformOnboardingInput,
} from "./api/types";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import {
  adminWorkspaceForUser,
  canAccessAdminWorkspace,
} from "./auth/permissions";
import { AppShell } from "./components/AppShell";
import { BootScreen } from "./components/BootScreen";
import { ResourceState } from "./components/ResourceState";
import { LoginPage } from "./pages/LoginPage";
import type {
  PlatformLlmConnectionResult,
  PlatformLlmCurrentConfig,
  PlatformLlmProfile,
  PlatformLlmProfileInput,
  PlatformLlmReadiness,
} from "./pages/PlatformLlmSettingsPage";
import {
  adminWorkspaceForPath,
  APP_PATHS,
  navigate,
  type AppPath,
  usePathname,
} from "./routing";

const OverviewPage = lazy(() =>
  import("./pages/OverviewPage").then((module) => ({
    default: module.OverviewPage,
  })),
);
const VisitsPage = lazy(() =>
  import("./pages/VisitsPage").then((module) => ({
    default: module.VisitsPage,
  })),
);
const VisitorProfilesPage = lazy(() =>
  import("./pages/VisitorProfilesPage").then((module) => ({
    default: module.VisitorProfilesPage,
  })),
);
const ConversationsPage = lazy(() =>
  import("./pages/ConversationsPage").then((module) => ({
    default: module.ConversationsPage,
  })),
);
const OpportunitiesPage = lazy(() =>
  import("./pages/OpportunitiesPage").then((module) => ({
    default: module.OpportunitiesPage,
  })),
);
const LeadsPage = lazy(() =>
  import("./pages/LeadsPage").then((module) => ({
    default: module.LeadsPage,
  })),
);
const ExportsPage = lazy(() =>
  import("./pages/ExportsPage").then((module) => ({
    default: module.ExportsPage,
  })),
);
const KnowledgeGapsPage = lazy(() =>
  import("./pages/KnowledgeGapsPage").then((module) => ({
    default: module.KnowledgeGapsPage,
  })),
);
const NotificationsPage = lazy(() =>
  import("./pages/NotificationsPage").then((module) => ({
    default: module.NotificationsPage,
  })),
);
const PrivacyRequestsPage = lazy(() =>
  import("./pages/PrivacyRequestsPage").then((module) => ({
    default: module.PrivacyRequestsPage,
  })),
);
const CompanyProfilePage = lazy(() =>
  import("./pages/CompanyProfilePage").then((module) => ({
    default: module.CompanyProfilePage,
  })),
);
const CardSettingsPage = lazy(() =>
  import("./pages/CardSettingsPage").then((module) => ({
    default: module.CardSettingsPage,
  })),
);
const KnowledgePage = lazy(() =>
  import("./pages/KnowledgePage").then((module) => ({
    default: module.KnowledgePage,
  })),
);
const CardsPage = lazy(() =>
  import("./pages/CardsPage").then((module) => ({
    default: module.CardsPage,
  })),
);
const ProductsPage = lazy(() =>
  import("./pages/CatalogPage").then((module) => ({
    default: module.ProductsPage,
  })),
);
const CaseStudiesPage = lazy(() =>
  import("./pages/CatalogPage").then((module) => ({
    default: module.CaseStudiesPage,
  })),
);
const ForbiddenTopicsPage = lazy(() =>
  import("./pages/ForbiddenTopicsPage").then((module) => ({
    default: module.ForbiddenTopicsPage,
  })),
);
const PlatformEnterprisesPage = lazy(() =>
  import("./pages/PlatformEnterprisesPage").then((module) => ({
    default: module.PlatformEnterprisesPage,
  })),
);
const PlatformOverviewPage = lazy(() =>
  import("./pages/PlatformOverviewPage").then((module) => ({
    default: module.PlatformOverviewPage,
  })),
);
const PlatformLlmSettingsPage = lazy(() =>
  import("./pages/PlatformLlmSettingsPage").then((module) => ({
    default: module.PlatformLlmSettingsPage,
  })),
);
const PlatformOnboardingPage = lazy(() =>
  import("./pages/PlatformOnboardingPage").then((module) => ({
    default: module.PlatformOnboardingPage,
  })),
);
const PlatformEmployeesPage = lazy(() =>
  import("./pages/PlatformGovernancePages").then((module) => ({
    default: module.PlatformEmployeesPage,
  })),
);
const PlatformVisitorsPage = lazy(() =>
  import("./pages/PlatformGovernancePages").then((module) => ({
    default: module.PlatformVisitorsPage,
  })),
);
const PlatformTasksPage = lazy(() =>
  import("./pages/PlatformGovernancePages").then((module) => ({
    default: module.PlatformTasksPage,
  })),
);
const PlatformAuditPage = lazy(() =>
  import("./pages/PlatformGovernancePages").then((module) => ({
    default: module.PlatformAuditPage,
  })),
);
const PlatformHealthPage = lazy(() =>
  import("./pages/PlatformGovernancePages").then((module) => ({
    default: module.PlatformHealthPage,
  })),
);
const MembersPage = lazy(() =>
  import("./pages/MembersPage").then((module) => ({
    default: module.MembersPage,
  })),
);

function toPageProfile(profile: ApiPlatformLlmProfile): PlatformLlmProfile {
  return {
    id: profile.id,
    name: profile.name,
    provider: profile.provider,
    model: profile.model,
    baseUrl: profile.baseUrl,
    keyConfigured: profile.keyConfigured,
    keyHint: profile.keyHint,
    enabled: profile.enabled,
    thinkingMode: profile.thinking,
    reasoningEffort: profile.reasoningEffort,
    timeoutSeconds: profile.timeoutSeconds,
    maxRetries: profile.maxRetries,
    dailyBudgetCny: profile.dailyBudgetCny,
    updatedAt: profile.updatedAt,
    version: profile.version,
  };
}

function llmReadiness(
  profiles: ApiPlatformLlmProfile[],
): PlatformLlmReadiness {
  const active = profiles.find((profile) => profile.isActive);
  if (!active) {
    return {
      status: profiles.length === 0 ? "unconfigured" : "partial",
      message:
        profiles.length === 0
          ? "还没有保存 LLM 配置。"
          : "已有配置，但尚未选择当前主配置。",
      capabilities: [
        { id: "chat_main", label: "名片 AI 问答", status: "unconfigured" },
      ],
    };
  }

  const status = !active.enabled
    ? "disabled"
    : !active.keyConfigured
      ? "unconfigured"
      : active.lastTestStatus === "failed"
        ? "failed"
        : active.lastTestStatus === "untested"
          ? "unconfigured"
          : "ready";
  return {
    status:
      status === "ready" ? "ready" : status === "failed" ? "failed" : "partial",
    message:
      status === "ready"
        ? "当前主配置已通过连接测试，可供名片 AI 问答使用。"
        : status === "failed"
          ? "当前主配置最近一次连接测试失败，请检查后重新测试。"
          : status === "disabled"
            ? "当前主配置已停用，名片 AI 问答暂不可用。"
            : active.keyConfigured
              ? "当前主配置尚未通过连接测试。"
              : "当前主配置尚未写入 API Key。",
    capabilities: [
      {
        id: "chat_main",
        label: "名片 AI 问答",
        status,
        profileName: active.name,
      },
    ],
  };
}

function llmCurrent(
  profiles: ApiPlatformLlmProfile[],
): PlatformLlmCurrentConfig {
  const active = profiles.find((profile) => profile.isActive);
  if (!active) return { source: "unconfigured" };
  return {
    source: "database",
    profileId: active.id,
    profileName: active.name,
    provider: active.provider,
    model: active.model,
    baseUrl: active.baseUrl,
    keyConfigured: active.keyConfigured,
    updatedAt: active.updatedAt,
  };
}

export function PlatformLlmSettingsRoute() {
  const [profiles, setProfiles] = useState<ApiPlatformLlmProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<ApiError>();

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(undefined);
    try {
      setProfiles(await platformApi.listLlmProfiles());
    } catch (caught) {
      const error =
        caught instanceof ApiError
          ? caught
          : new ApiError("LLM 配置加载失败。", { code: "UNKNOWN_ERROR" });
      setLoadError(error);
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

  const pageProfiles = useMemo(() => profiles.map(toPageProfile), [profiles]);
  const current = useMemo(() => llmCurrent(profiles), [profiles]);
  const readiness = useMemo(() => llmReadiness(profiles), [profiles]);

  const save = async (
    input: PlatformLlmProfileInput,
    profile?: PlatformLlmProfile,
  ) => {
    if (profile) {
      const expectedVersion = profile.version;
      if (!expectedVersion) {
        throw new ApiError("配置版本缺失，请刷新后重试。", {
          code: "INVALID_PROFILE_VERSION",
        });
      }
      await platformApi.updateLlmProfile(profile.id, {
        expectedVersion,
        name: input.name,
        provider: input.provider,
        baseUrl: input.baseUrl,
        model: input.model,
        apiKey: input.apiKey || undefined,
        thinking: input.thinkingMode,
        reasoningEffort: input.reasoningEffort,
        timeoutSeconds: input.timeoutSeconds,
        maxRetries: input.maxRetries,
        dailyBudgetCny: input.dailyBudgetCny,
        enabled: input.enabled,
      });
    } else {
      await platformApi.createLlmProfile({
        name: input.name,
        provider: input.provider,
        baseUrl: input.baseUrl,
        model: input.model,
        apiKey: input.apiKey,
        thinking: input.thinkingMode,
        reasoningEffort: input.reasoningEffort,
        timeoutSeconds: input.timeoutSeconds,
        maxRetries: input.maxRetries,
        dailyBudgetCny: input.dailyBudgetCny,
        enabled: input.enabled,
      });
    }
    await refresh();
  };

  const test = async (
    input: PlatformLlmProfileInput,
    profile?: PlatformLlmProfile,
  ): Promise<PlatformLlmConnectionResult> => {
    if (!profile) {
      throw new ApiError("请先保存配置，再执行连接测试。", {
        code: "PROFILE_REQUIRED",
      });
    }
    const result = await platformApi.testLlmProfile(
      profile.id,
      input.apiKey || undefined,
    );
    await refresh();
    return {
      ok: result.status === "succeeded",
      provider: result.provider,
      model: result.model,
      latencyMs: result.latencyMs,
      errorCode: result.errorCode,
    };
  };

  const activate = async (profile: PlatformLlmProfile) => {
    const expectedVersion = profile.version;
    if (!expectedVersion) {
      throw new ApiError("配置版本缺失，请刷新后重试。", {
        code: "INVALID_PROFILE_VERSION",
      });
    }
    await platformApi.activateLlmProfile(profile.id, {
      expectedVersion,
      expectedActiveProfileId: profiles.find((value) => value.isActive)?.id,
    });
    await refresh();
  };

  if (loadError && profiles.length === 0) {
    return (
      <main className="page-stack">
        <section className="content-panel">
          <ResourceState
            status="error"
            title="LLM 配置加载失败"
            description={loadError.message}
            errorCode={loadError.code}
            requestId={loadError.requestId}
            onRetry={() => void refresh().catch(() => undefined)}
          />
        </section>
      </main>
    );
  }

  return (
    <PlatformLlmSettingsPage
      profiles={pageProfiles}
      current={current}
      readiness={readiness}
      loading={loading}
      onSave={save}
      onTest={test}
      onActivate={activate}
      onRefresh={() => void refresh().catch(() => undefined)}
    />
  );
}

const ONBOARDING_SESSION_KEY = "cf-platform-onboarding-session";

export function PlatformOnboardingRoute() {
  const [session, setSession] = useState<PlatformOnboardingSession>();
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<ApiError>();
  const [llmAvailability, setLlmAvailability] = useState<
    "ready" | "unavailable" | "failed"
  >("unavailable");
  const [adminSummary, setAdminSummary] = useState<{
    account: string;
    displayName: string;
  }>();
  const [initialReview, setInitialReview] = useState<{
    tenantName?: string;
    companyName?: string;
    initialCardDisplayName?: string;
  }>();

  const loadSession = useCallback(async (sessionId?: string) => {
    const stored =
      sessionId ??
      (typeof window === "undefined"
        ? undefined
        : window.sessionStorage.getItem(ONBOARDING_SESSION_KEY) ?? undefined);
    if (!stored) return;
    setLoading(true);
    setLoadError(undefined);
    try {
      setSession(await platformApi.getOnboarding(stored));
    } catch (caught) {
      setLoadError(
        caught instanceof ApiError
          ? caught
          : new ApiError("开通会话加载失败。", { code: "UNKNOWN_ERROR" }),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSession();
    void platformApi
      .listLlmProfiles()
      .then((profiles) => {
        const active = profiles.find((profile) => profile.isActive);
        setLlmAvailability(
          active?.enabled &&
            active.keyConfigured &&
            active.lastTestStatus === "succeeded"
            ? "ready"
            : "unavailable",
        );
      })
      .catch(() => setLlmAvailability("failed"));
  }, [loadSession]);

  const replaceSession = (value: PlatformOnboardingSession) => {
    setSession(value);
    window.sessionStorage.setItem(ONBOARDING_SESSION_KEY, value.id);
  };

  return (
    <PlatformOnboardingPage
      session={session}
      adminSummary={adminSummary}
      initialReview={initialReview}
      llmAvailability={llmAvailability}
      resourceStatus={loading ? "loading" : loadError ? "error" : "ready"}
      resourceError={loadError}
      onStart={async (input: StartPlatformOnboardingInput) => {
        const created = await platformApi.startOnboarding(input);
        setAdminSummary({
          account: input.adminAccount,
          displayName: input.adminDisplayName,
        });
        setInitialReview({
          tenantName: input.tenantName,
          companyName: input.tenantName,
          initialCardDisplayName: input.adminDisplayName,
        });
        replaceSession(created);
      }}
      onUpload={async (sessionId: string, files: File[]) => {
        replaceSession(await platformApi.uploadOnboardingDocuments(sessionId, files));
      }}
      onGenerate={async (sessionId: string, expectedVersion: number) => {
        replaceSession(
          await platformApi.generateOnboardingSuggestions(sessionId, expectedVersion),
        );
      }}
      onConfirm={async (
        sessionId: string,
        input: ConfirmPlatformOnboardingInput,
      ) => {
        replaceSession(await platformApi.confirmOnboarding(sessionId, input));
      }}
      onCancel={async (
        sessionId: string,
        reason: string,
        expectedVersion: number,
      ) => {
        replaceSession(
          await platformApi.cancelOnboarding(sessionId, reason, expectedVersion),
        );
      }}
      onRefresh={() => void loadSession(session?.id)}
      onStartAnother={() => {
        window.sessionStorage.removeItem(ONBOARDING_SESSION_KEY);
        setSession(undefined);
        setAdminSummary(undefined);
        setInitialReview(undefined);
        setLoadError(undefined);
      }}
      onOpenEnterprises={() => navigate(APP_PATHS.platformEnterprises)}
    />
  );
}

function RouteRedirect({ path }: { path: AppPath }) {
  useEffect(() => navigate(path), [path]);
  return (
    <main className="page-stack">
      <section className="content-panel">
        <ResourceState status="loading" />
      </section>
    </main>
  );
}

function WorkspaceForbidden({ destination }: { destination: AppPath }) {
  return (
    <main className="page-stack">
      <section className="content-panel">
        <ResourceState
          status="permission"
          title="无法访问此工作区"
          description="当前账号与该控制台不匹配（403）。请返回当前账号所属工作区。"
        />
        <Button appearance="primary" onClick={() => navigate(destination)}>
          返回当前工作区
        </Button>
      </section>
    </main>
  );
}

export function CurrentPage() {
  const pathname = usePathname();
  const auth = useAuth();
  const userWorkspace = adminWorkspaceForUser(auth.user);
  if (pathname === APP_PATHS.overview && userWorkspace === "platform") {
    return <RouteRedirect path={APP_PATHS.platformOverview} />;
  }
  const routeWorkspace = adminWorkspaceForPath(pathname);
  if (
    routeWorkspace &&
    !canAccessAdminWorkspace(auth.user, routeWorkspace) &&
    userWorkspace
  ) {
    return (
      <WorkspaceForbidden
        destination={
          userWorkspace === "platform"
            ? APP_PATHS.platformOverview
            : APP_PATHS.overview
        }
      />
    );
  }
  if (pathname === APP_PATHS.platformOverview) return <PlatformOverviewPage />;
  if (pathname === APP_PATHS.platformLlmSettings) {
    return <PlatformLlmSettingsRoute />;
  }
  if (pathname === APP_PATHS.platformOnboarding) {
    return <RouteRedirect path={APP_PATHS.platformEnterprises} />;
  }
  if (pathname === APP_PATHS.platformEmployees) return <PlatformEmployeesPage />;
  if (pathname === APP_PATHS.platformVisitors) return <PlatformVisitorsPage />;
  if (pathname === APP_PATHS.platformTasks) return <PlatformTasksPage />;
  if (pathname === APP_PATHS.platformAudit) return <PlatformAuditPage />;
  if (pathname === APP_PATHS.platformHealth) return <PlatformHealthPage />;
  if (pathname === APP_PATHS.visits) return <VisitsPage />;
  if (pathname === APP_PATHS.visitorProfiles) return <VisitorProfilesPage />;
  if (pathname === APP_PATHS.conversations) return <ConversationsPage />;
  if (pathname === APP_PATHS.opportunities) return <OpportunitiesPage />;
  if (pathname === APP_PATHS.leads) return <LeadsPage />;
  if (pathname === APP_PATHS.exports) return <ExportsPage />;
  if (pathname === APP_PATHS.knowledgeGaps) return <KnowledgeGapsPage />;
  if (pathname === APP_PATHS.notifications) return <NotificationsPage />;
  if (pathname === APP_PATHS.privacyRequests) return <PrivacyRequestsPage />;
  if (pathname === APP_PATHS.company) return <CompanyProfilePage />;
  if (pathname === APP_PATHS.members) return <MembersPage />;
  if (pathname === APP_PATHS.card) return <CardSettingsPage />;
  if (pathname === APP_PATHS.cards) return <CardsPage />;
  if (pathname === APP_PATHS.products) return <ProductsPage />;
  if (pathname === APP_PATHS.cases) return <CaseStudiesPage />;
  if (pathname === APP_PATHS.forbiddenTopics) return <ForbiddenTopicsPage />;
  if (pathname === APP_PATHS.knowledge) return <KnowledgePage />;
  if (pathname === APP_PATHS.platformEnterprises) return <PlatformEnterprisesPage />;
  if (pathname === APP_PATHS.overview) {
    return <OverviewPage />;
  }

  return (
    <main className="page-stack">
      <section className="content-panel">
        <ResourceState
          status="empty"
          title="页面不存在"
          description="当前地址不属于企业管理工作台。"
          emptyAction={
            <Button appearance="primary" onClick={() => navigate(APP_PATHS.overview)}>
              返回概览
            </Button>
          }
        />
      </section>
    </main>
  );
}

function AuthenticatedApplication() {
  return (
    <AppShell>
      <Suspense
        fallback={
          <main className="page-stack">
            <section className="content-panel">
              <ResourceState status="loading" />
            </section>
          </main>
        }
      >
        <CurrentPage />
      </Suspense>
    </AppShell>
  );
}

export function SessionGate() {
  const auth = useAuth();
  const pathname = usePathname();
  const workspace = adminWorkspaceForUser(auth.user);
  const landingPath =
    workspace === "platform" ? APP_PATHS.platformOverview : APP_PATHS.overview;

  useEffect(() => {
    if (auth.status === "authenticated" && pathname === "/login" && workspace) {
      navigate(landingPath);
    }
  }, [auth.status, landingPath, pathname, workspace]);

  if (auth.status === "bootstrapping") return <BootScreen />;
  if (auth.status === "unauthenticated") return <LoginPage />;
  if (pathname === "/login" && workspace) return <BootScreen />;
  return <AuthenticatedApplication />;
}

export function App() {
  return (
    <AuthProvider>
      <SessionGate />
    </AuthProvider>
  );
}

import { Button } from "@fluentui/react-components";
import { lazy, Suspense } from "react";

import { AuthProvider, useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { BootScreen } from "./components/BootScreen";
import { ResourceState } from "./components/ResourceState";
import { LoginPage } from "./pages/LoginPage";
import { APP_PATHS, navigate, usePathname } from "./routing";

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
const ConversationsPage = lazy(() =>
  import("./pages/ConversationsPage").then((module) => ({
    default: module.ConversationsPage,
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
const MembersPage = lazy(() =>
  import("./pages/MembersPage").then((module) => ({
    default: module.MembersPage,
  })),
);

function CurrentPage() {
  const pathname = usePathname();
  if (pathname === APP_PATHS.visits) return <VisitsPage />;
  if (pathname === APP_PATHS.conversations) return <ConversationsPage />;
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
  if (pathname === APP_PATHS.overview) return <OverviewPage />;

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

function SessionGate() {
  const auth = useAuth();
  if (auth.status === "bootstrapping") return <BootScreen />;
  if (auth.status === "unauthenticated") return <LoginPage />;
  return <AuthenticatedApplication />;
}

export function App() {
  return (
    <AuthProvider>
      <SessionGate />
    </AuthProvider>
  );
}

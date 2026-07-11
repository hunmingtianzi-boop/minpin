import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { TenantLoading } from "./components/TenantLoading";
import { TenantNotFound } from "./components/TenantNotFound";
import type { EnterpriseCardConfig } from "./domain/card";
import {
  fetchPublicCard,
  type PublicCardData,
} from "./lib/publicCardApi";
import { applyTenantRuntime } from "./lib/tenantRuntime";
import { validateTenantConfig } from "./lib/validateTenantConfig";
import { loadTenant, resolveTenantSlug } from "./tenants";

const tenantSlug = resolveTenantSlug(window.location);
const root = createRoot(document.getElementById("root")!);

function renderTenant(tenant: EnterpriseCardConfig, publishedCard?: PublicCardData) {
  const validation = validateTenantConfig(tenant);
  if (!validation.valid) {
    console.error("Tenant config validation failed", validation.errors);
    root.render(
      <StrictMode>
        <TenantNotFound kind="invalid" onRetry={() => window.location.reload()} />
      </StrictMode>,
    );
    return false;
  }

  applyTenantRuntime(tenant);
  root.render(
    <StrictMode>
      <AppErrorBoundary>
        <App tenant={tenant} publishedCard={publishedCard} />
      </AppErrorBoundary>
    </StrictMode>,
  );
  return true;
}

if (tenantSlug) {
  root.render(
    <StrictMode>
      <TenantLoading />
    </StrictMode>,
  );
} else {
  root.render(
    <StrictMode>
      <TenantNotFound />
    </StrictMode>,
  );
}

async function bootstrapTenant() {
  if (!tenantSlug) return;
  const publishedCardPromise = fetchPublicCard(tenantSlug)
    .then((card) => ({ card, error: undefined }))
    .catch((error: unknown) => ({ card: undefined, error }));
  let registeredTenant: EnterpriseCardConfig | undefined;
  try {
    registeredTenant = await loadTenant(tenantSlug);
    if (registeredTenant) renderTenant(registeredTenant);

    const publishedResult = await publishedCardPromise;
    if (publishedResult.error) throw publishedResult.error;
    const publishedCard = publishedResult.card;
    if (publishedCard) {
      const { mergePublishedCard } = await import("./lib/publicCard");
      const fallbackTenant = registeredTenant ?? (await loadTenant("template"));
      if (!fallbackTenant) throw new Error("Generic tenant template is unavailable");
      renderTenant(
        mergePublishedCard(publishedCard, registeredTenant, fallbackTenant),
        publishedCard,
      );
      return;
    }
    if (!registeredTenant) {
      root.render(
        <StrictMode>
          <TenantNotFound />
        </StrictMode>,
      );
    }
  } catch (error) {
    console.error("Published tenant loading failed", {
      errorType: error instanceof Error ? error.name : typeof error,
    });
    if (!registeredTenant) {
      root.render(
        <StrictMode>
          <TenantNotFound kind="runtime" onRetry={() => window.location.reload()} />
        </StrictMode>,
      );
    }
  }
}

void bootstrapTenant();

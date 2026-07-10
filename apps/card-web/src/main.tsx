import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { TenantNotFound } from "./components/TenantNotFound";
import { applyTenantRuntime } from "./lib/tenantRuntime";
import { validateTenantConfig } from "./lib/validateTenantConfig";
import { getTenant, resolveTenantSlug } from "./tenants";

const tenantSlug = resolveTenantSlug(window.location);
const tenant = getTenant(tenantSlug);
const validation = tenant ? validateTenantConfig(tenant) : undefined;
const validTenant = tenant && validation?.valid ? tenant : undefined;

if (validTenant) applyTenantRuntime(validTenant);
if (tenant && validation && !validation.valid) {
  console.error("Tenant config validation failed", validation.errors);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {validTenant ? (
      <AppErrorBoundary>
        <App tenant={validTenant} />
      </AppErrorBoundary>
    ) : tenant ? (
      <TenantNotFound kind="invalid" onRetry={() => window.location.reload()} />
    ) : (
      <TenantNotFound />
    )}
  </StrictMode>,
);

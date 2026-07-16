import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { platformApi } from "./api/platformApi";
import type { AdminUser, PlatformLlmProfile } from "./api/types";
import { CurrentPage, SessionGate } from "./App";
import { AuthContext, type AuthContextValue } from "./auth/AuthContext";
import { APP_PATHS, appHref } from "./routing";

function user(role: string): AdminUser {
  return {
    id: "user-1",
    displayName: role === "platform_admin" ? "平台管理员" : "企业管理员",
    membershipId: "membership-1",
    tenantId: "tenant-1",
    companyId: "company-1",
    role,
    permissions: [],
  };
}

function authValue(role: string): AuthContextValue {
  return {
    status: "authenticated",
    user: user(role),
    loginPending: false,
    apiConfigured: true,
    login: vi.fn(),
    logout: vi.fn(),
  };
}

function renderCurrentPage(role: string) {
  return render(
    <FluentProvider theme={webLightTheme}>
      <AuthContext.Provider value={authValue(role)}>
        <CurrentPage />
      </AuthContext.Provider>
    </FluentProvider>,
  );
}

function profile(): PlatformLlmProfile {
  return {
    id: "profile-1",
    name: "DeepSeek 主模型",
    purpose: "chat_main",
    provider: "deepseek",
    baseUrl: "https://api.deepseek.com",
    model: "deepseek-chat",
    thinking: "disabled",
    timeoutSeconds: 30,
    maxRetries: 2,
    maxConcurrency: 20,
    maxOutputTokens: 1000,
    temperature: 0.1,
    dailyBudgetCny: 100,
    inputPriceCnyPerMillion: 1,
    outputPriceCnyPerMillion: 2,
    keyConfigured: true,
    keyHint: "sk-***1234",
    enabled: true,
    isActive: true,
    version: 4,
    lastTestStatus: "succeeded",
    lastTestLatencyMs: 82,
    lastTestedAt: "2026-07-15T12:00:00Z",
    createdAt: "2026-07-15T10:00:00Z",
    updatedAt: "2026-07-15T12:00:00Z",
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", appHref(APP_PATHS.overview));
});

describe("CurrentPage workspace routing", () => {
  it.each([
    ["company_admin", APP_PATHS.overview],
    ["platform_admin", APP_PATHS.platformOverview],
  ])("leaves the login URL for %s after authentication", async (role, destination) => {
    window.history.replaceState({}, "", appHref("/login"));

    render(
      <FluentProvider theme={webLightTheme}>
        <AuthContext.Provider value={authValue(role)}>
          <SessionGate />
        </AuthContext.Provider>
      </FluentProvider>,
    );

    await waitFor(() => {
      expect(window.location.pathname).toBe(appHref(destination));
    });
  });

  it("returns a 403 surface before an enterprise account can mount platform data", () => {
    const listProfiles = vi.spyOn(platformApi, "listLlmProfiles");
    window.history.replaceState(
      {},
      "",
      appHref(APP_PATHS.platformLlmSettings),
    );

    renderCurrentPage("company_admin");

    expect(screen.getByText("无法访问此工作区")).toBeInTheDocument();
    expect(screen.getByText(/403/)).toBeInTheDocument();
    expect(listProfiles).not.toHaveBeenCalled();
  });

  it("redirects a platform account from the enterprise root to platform overview", async () => {
    window.history.replaceState({}, "", appHref(APP_PATHS.overview));

    renderCurrentPage("platform_admin");

    await waitFor(() => {
      expect(window.location.pathname).toBe(appHref(APP_PATHS.platformOverview));
    });
  });

  it("redirects the hidden onboarding route to enterprise management", async () => {
    window.history.replaceState(
      {},
      "",
      appHref(APP_PATHS.platformOnboarding),
    );

    renderCurrentPage("platform_admin");

    await waitFor(() => {
      expect(window.location.pathname).toBe(
        appHref(APP_PATHS.platformEnterprises),
      );
    });
  });

  it("loads the real LLM route for a platform account", async () => {
    vi.spyOn(platformApi, "listLlmProfiles").mockResolvedValue([profile()]);
    window.history.replaceState(
      {},
      "",
      appHref(APP_PATHS.platformLlmSettings),
    );

    renderCurrentPage("platform_admin");

    expect(await screen.findAllByText("DeepSeek 主模型")).not.toHaveLength(0);
    expect(platformApi.listLlmProfiles).toHaveBeenCalledTimes(1);
    expect(screen.getByText("当前主配置已通过连接测试，可供名片 AI 问答使用。")).toBeInTheDocument();
  });
});

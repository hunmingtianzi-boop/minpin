import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  PlatformLlmSettingsPage,
  type PlatformLlmProfile,
  type PlatformLlmSettingsPageProps,
} from "./PlatformLlmSettingsPage";

const readyProfile: PlatformLlmProfile = {
  id: "profile-1",
  name: "DeepSeek 主模型",
  provider: "deepseek",
  model: "deepseek-chat",
  baseUrl: "https://api.deepseek.com",
  keyConfigured: true,
  keyHint: "sk-***9a",
  enabled: true,
  timeoutSeconds: 30,
  maxRetries: 2,
  dailyBudgetCny: 100,
};

function props(overrides: Partial<PlatformLlmSettingsPageProps> = {}): PlatformLlmSettingsPageProps {
  return {
    profiles: [readyProfile],
    current: {
      source: "database",
      profileId: readyProfile.id,
      profileName: readyProfile.name,
      provider: readyProfile.provider,
      model: readyProfile.model,
      keyConfigured: true,
    },
    readiness: {
      status: "ready",
      capabilities: [
        { id: "chat", label: "名片问答", status: "ready", profileName: readyProfile.name },
        { id: "extract", label: "文档提取", status: "ready", profileName: readyProfile.name },
      ],
    },
    onSave: vi.fn().mockResolvedValue(undefined),
    onTest: vi.fn().mockResolvedValue({
      ok: true,
      provider: "deepseek",
      model: "deepseek-chat",
      latencyMs: 84,
    }),
    onActivate: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

describe("PlatformLlmSettingsPage", () => {
  it("shows an actionable unconfigured state", () => {
    render(
      <PlatformLlmSettingsPage
        {...props({
          profiles: [],
          current: { source: "unconfigured", keyConfigured: false },
          readiness: {
            status: "unconfigured",
            capabilities: [
              { id: "chat", label: "名片问答", status: "unconfigured" },
            ],
          },
        })}
      />,
    );

    expect(screen.getAllByText("未配置").length).toBeGreaterThan(0);
    expect(screen.getByText("还没有可用配置")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建配置" })).toBeEnabled();
  });

  it("keeps test and save as separate operations and clears the secret after save", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onTest = vi.fn().mockResolvedValue({
      ok: true,
      provider: "deepseek",
      model: "deepseek-chat",
      latencyMs: 52,
    });
    render(<PlatformLlmSettingsPage {...props({ onSave, onTest })} />);

    await user.click(screen.getByRole("button", { name: "编辑" }));
    const dialog = screen.getByRole("dialog", { name: "编辑配置" });
    const secret = within(dialog).getByLabelText("API Key（留空保留）");
    expect(secret).toHaveValue("");
    await user.type(secret, "replacement-secret");
    await user.click(within(dialog).getByRole("button", { name: "测试当前填写值" }));

    await waitFor(() => expect(onTest).toHaveBeenCalledTimes(1));
    expect(onSave).not.toHaveBeenCalled();
    expect(await within(dialog).findByText("连接测试通过")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "保存配置" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave.mock.calls[0][0].apiKey).toBe("replacement-secret");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "编辑" }));
    expect(screen.getByLabelText("API Key（留空保留）")).toHaveValue("");
  });

  it("explains a 409 conflict without closing the editor", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue({ status: 409, code: "VERSION_CONFLICT" });
    render(<PlatformLlmSettingsPage {...props({ onSave })} />);

    await user.click(screen.getByRole("button", { name: "编辑" }));
    await user.click(screen.getByRole("button", { name: "保存配置" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("配置已发生变化")).toBeInTheDocument();
    expect(screen.getByText(/请刷新后重新编辑/)).toBeInTheDocument();
    expect(screen.getByText("错误码：VERSION_CONFLICT")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "编辑配置" })).toBeInTheDocument();
  });

  it("turns a 403 activation error into a permission message", async () => {
    const user = userEvent.setup();
    const secondProfile = { ...readyProfile, id: "profile-2", name: "备用模型" };
    const onActivate = vi.fn().mockRejectedValue({ status: 403, code: "FORBIDDEN" });
    render(
      <PlatformLlmSettingsPage
        {...props({ profiles: [readyProfile, secondProfile], onActivate })}
      />,
    );

    const profileRow = screen.getByText("备用模型").closest("li");
    expect(profileRow).not.toBeNull();
    await user.click(within(profileRow as HTMLElement).getByRole("button", { name: "设为主配置" }));

    expect(await screen.findByText("没有配置权限")).toBeInTheDocument();
    expect(screen.getByText("错误码：FORBIDDEN")).toBeInTheDocument();
  });
});

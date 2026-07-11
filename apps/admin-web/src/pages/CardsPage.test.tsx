import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "../api/adminApi";
import type { ManagedCard } from "../api/types";
import { adminLightTheme } from "../theme";
import { CardsPage } from "./CardsPage";

const draftCard: ManagedCard = {
  id: "card-1",
  ownerUserId: "user-1",
  slug: "c-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  displayName: "林顾问",
  title: "解决方案顾问",
  avatarUrl: "",
  assistantName: "企业助手",
  welcomeMessage: "欢迎咨询",
  suggestedQuestions: ["你们提供什么服务？"],
  policyVersions: {
    privacy: "privacy-v1",
    chatNotice: "chat-v1",
    leadConsent: "lead-v1",
  },
  status: "draft",
  version: 6,
  shareUrl: "https://cards.example.test/c/card-1",
  qrUrl: "https://cards.example.test/c/card-1",
  updatedAt: "2026-07-11T00:00:00Z",
};

function renderPage() {
  return render(
    <FluentProvider theme={adminLightTheme}>
      <CardsPage />
    </FluentProvider>,
  );
}

describe("CardsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("publishes a draft card with its current version", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([draftCard]);
    const publish = vi
      .spyOn(adminApi, "publishManagedCard")
      .mockResolvedValue({ ...draftCard, status: "published", version: 7 });
    renderPage();

    await screen.findByText("林顾问");
    await user.click(screen.getByRole("button", { name: "发布" }));
    await user.click(screen.getByRole("button", { name: "确认发布" }));

    await waitFor(() => expect(publish).toHaveBeenCalledWith("card-1", 6));
  });

  it("copies the server share value", async () => {
    const user = userEvent.setup();
    const publishedCard = { ...draftCard, status: "published", version: 7 };
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([publishedCard]);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    renderPage();

    await screen.findByText("林顾问");
    await user.click(screen.getByRole("button", { name: "分享" }));
    await user.click(screen.getByRole("button", { name: "复制分享链接" }));
    expect(writeText).toHaveBeenCalledWith(publishedCard.shareUrl);
    expect(await screen.findByText("分享链接已复制。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "分享名片" })).not.toBeInTheDocument(),
    );
  });

  it("confirms deactivation before invalidating a public card", async () => {
    const user = userEvent.setup();
    const publishedCard = { ...draftCard, status: "published", version: 7 };
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([publishedCard]);
    const deactivate = vi
      .spyOn(adminApi, "deactivateManagedCard")
      .mockResolvedValue({ ...publishedCard, status: "archived", version: 8 });
    renderPage();

    await screen.findByText("林顾问");
    await user.click(screen.getByRole("button", { name: "停用" }));
    expect(deactivate).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "确认停用" }));
    await waitFor(() => expect(deactivate).toHaveBeenCalledWith("card-1", 7));
  });

  it("creates a card without allowing the browser to choose a slug", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminApi, "listManagedCards").mockResolvedValue([]);
    const create = vi.spyOn(adminApi, "createManagedCard").mockResolvedValue(draftCard);
    renderPage();

    await screen.findByText("尚未创建名片");
    await user.click(screen.getAllByRole("button", { name: "新建名片" })[0]);
    fireEvent.change(screen.getByRole("textbox", { name: /展示姓名/ }), {
      target: { value: "林顾问" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /职务或头衔/ }), {
      target: { value: "解决方案顾问" },
    });
    expect(screen.queryByRole("textbox", { name: /公开标识/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存名片" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0]).not.toHaveProperty("slug");
  });
});

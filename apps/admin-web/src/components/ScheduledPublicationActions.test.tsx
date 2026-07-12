import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { scheduledPublicationsApi } from "../api/scheduledPublicationsApi";
import { adminLightTheme } from "../theme";
import { ScheduledPublicationActions } from "./ScheduledPublicationActions";

describe("ScheduledPublicationActions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a future schedule using the target version", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(scheduledPublicationsApi, "create").mockResolvedValue({
      id: "schedule-1",
      resourceType: "product",
      resourceId: "product-1",
      targetVersion: 4,
      scheduledBy: "user-1",
      scheduledAt: "2099-01-01T01:00:00Z",
      status: "pending",
      attempts: 0,
      maxAttempts: 5,
      nextAttemptAt: "2099-01-01T01:00:00Z",
      version: 4,
    });
    const changed = vi.fn();
    render(
      <FluentProvider theme={adminLightTheme}>
        <ScheduledPublicationActions
          targetType="product"
          targetId="product-1"
          targetVersion={4}
          targetLabel="企业 AI 助手"
          onChanged={changed}
        />
      </FluentProvider>,
    );

    await user.click(screen.getByRole("button", { name: "定时发布" }));
    fireEvent.change(screen.getByLabelText(/发布时间/), {
      target: { value: "2099-01-01T09:00" },
    });
    await user.click(screen.getByRole("button", { name: "确认定时发布" }));

    await waitFor(() => expect(create).toHaveBeenCalledWith(expect.objectContaining({
      targetId: "product-1",
      targetType: "product",
      version: 4,
    })));
    expect(changed).toHaveBeenCalledWith("已为“企业 AI 助手”设置定时发布。");
  });

  it("cancels an active schedule with optimistic concurrency", async () => {
    const user = userEvent.setup();
    const cancel = vi.spyOn(scheduledPublicationsApi, "cancel").mockResolvedValue(undefined);
    render(
      <FluentProvider theme={adminLightTheme}>
        <ScheduledPublicationActions
          targetType="knowledge_document"
          targetId="knowledge-1"
          targetVersion={2}
          targetLabel="企业知识"
          current={{
            id: "schedule-2",
            resourceType: "knowledge_document",
            resourceId: "knowledge-1",
            targetVersion: 2,
            scheduledBy: "user-1",
            scheduledAt: "2099-01-01T01:00:00Z",
            status: "pending",
            attempts: 0,
            maxAttempts: 5,
            nextAttemptAt: "2099-01-01T01:00:00Z",
            version: 7,
          }}
          onChanged={vi.fn()}
        />
      </FluentProvider>,
    );

    await user.click(screen.getByRole("button", { name: "取消定时" }));
    await user.click(screen.getByRole("button", { name: "确认取消定时" }));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith("schedule-2", 7));
  });
});

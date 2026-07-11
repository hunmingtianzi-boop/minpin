import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AssistantStreamEvent } from "../lib/assistantApi";
import { templateTenant } from "../tenants/template/tenant";
import { AIAssistant } from "./AIAssistant";

const streamMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/assistantApi", async () => {
  const actual = await vi.importActual<typeof import("../lib/assistantApi")>(
    "../lib/assistantApi",
  );
  return {
    ...actual,
    isAssistantApiConfigured: () => true,
    createAssistantIdempotencyKey: () => "message-key-0001",
    streamAssistantMessage: streamMock,
  };
});

describe("AIAssistant lead handoff", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    );
    streamMock.mockReset().mockImplementation(async ({ onEvent }: {
      onEvent: (event: AssistantStreamEvent) => void;
    }) => {
      onEvent({
        type: "completed",
        messageId: "message-1",
        finishReason: "stop",
        leadPrompt: true,
      });
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("closes the assistant before opening the lead form requested by the stream", async () => {
    const onLeadPrompt = vi.fn();
    render(
      <AIAssistant
        config={templateTenant.assistant}
        cardSlug="tenant-a"
        onLeadPrompt={onLeadPrompt}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: templateTenant.assistant.launcherAriaLabel }),
    );
    fireEvent.change(screen.getByLabelText(templateTenant.assistant.labels.input), {
      target: { value: "请联系我" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: templateTenant.assistant.labels.send }),
    );

    await waitFor(() => expect(onLeadPrompt).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

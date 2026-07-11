import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { adminLightTheme } from "../theme";
import { OperationFeedback } from "./OperationFeedback";

describe("OperationFeedback", () => {
  it("explains optimistic conflicts and preserves a retry action", () => {
    const retry = vi.fn();
    render(
      <FluentProvider theme={adminLightTheme}>
        <OperationFeedback
          error={
            new ApiError("线索已被其他管理员更新。", {
              code: "VERSION_CONFLICT",
              status: 409,
              requestId: "request-409",
            })
          }
          onRetry={retry}
        />
      </FluentProvider>,
    );

    expect(screen.getByText("数据状态已变更")).toBeInTheDocument();
    expect(screen.getByText(/VERSION_CONFLICT/)).toBeInTheDocument();
    expect(screen.getByText(/刷新最新数据后重试/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});

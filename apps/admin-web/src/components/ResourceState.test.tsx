import { FluentProvider } from "@fluentui/react-components";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { adminLightTheme } from "../theme";
import { ResourceState } from "./ResourceState";

function renderState(node: React.ReactNode) {
  return render(<FluentProvider theme={adminLightTheme}>{node}</FluentProvider>);
}

describe("ResourceState", () => {
  it("renders a layout-shaped loading state", () => {
    renderState(<ResourceState status="loading" />);
    expect(screen.getByRole("status", { name: "正在加载" })).toBeInTheDocument();
  });

  it("renders an empty state with a real action", () => {
    renderState(
      <ResourceState
        status="empty"
        title="暂无 FAQ"
        emptyAction={<button type="button">新建 FAQ</button>}
      />,
    );
    expect(screen.getByText("暂无 FAQ")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建 FAQ" })).toBeEnabled();
  });

  it("renders permission guidance", () => {
    renderState(<ResourceState status="permission" />);
    expect(screen.getByText("没有访问权限")).toBeInTheDocument();
  });

  it("shows error references and invokes retry", () => {
    const retry = vi.fn();
    renderState(
      <ResourceState
        status="error"
        description="接口未接通。"
        errorCode="HTTP_404"
        requestId="request-1"
        onRetry={retry}
      />,
    );
    expect(screen.getByText("接口未接通。")).toBeInTheDocument();
    expect(screen.getByText(/HTTP_404/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});

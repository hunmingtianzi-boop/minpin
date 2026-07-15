import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MobileActionBar } from "./App";

describe("MobileActionBar", () => {
  it("keeps the four primary phone actions reachable", () => {
    const onAssistant = vi.fn();
    const onLead = vi.fn();

    render(
      <MobileActionBar
        heroId="top"
        businessId="catalog"
        contactId="cooperation"
        onAssistant={onAssistant}
        onLead={onLead}
      />,
    );

    expect(screen.getByRole("navigation", { name: "手机快捷操作" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回名片首页" })).toHaveAttribute(
      "href",
      "#top",
    );
    expect(screen.getByRole("link", { name: "查看企业业务" })).toHaveAttribute(
      "href",
      "#catalog",
    );

    fireEvent.click(screen.getByRole("button", { name: "问 AI" }));
    fireEvent.click(screen.getByRole("button", { name: "联系" }));

    expect(onAssistant).toHaveBeenCalledOnce();
    expect(onLead).toHaveBeenCalledOnce();
  });

  it("falls back to an in-page contact link without a published card", () => {
    render(
      <MobileActionBar
        heroId="top"
        businessId="ecosystem"
        contactId="cooperation"
        onAssistant={vi.fn()}
      />,
    );

    expect(screen.getByRole("link", { name: "查看联系与合作方式" })).toHaveAttribute(
      "href",
      "#cooperation",
    );
  });
});

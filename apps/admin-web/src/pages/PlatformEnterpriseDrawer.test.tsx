import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { platformApi } from "../api/platformApi";
import type { PlatformEnterpriseDetail } from "../api/types";
import { PlatformEnterpriseDrawer } from "./PlatformEnterpriseDrawer";

const detail: PlatformEnterpriseDetail = {
  tenantId: "tenant-1",
  tenantSlug: "acme",
  tenantName: "Acme Tenant",
  companyId: "company-1",
  companyName: "Acme 商务",
  status: "active",
  createdAt: "2026-07-11T00:00:00Z",
  updatedAt: "2026-07-15T12:00:00Z",
  version: 3,
  onboardingStatus: "completed",
  profileCompletion: 80,
  employeeCount: 4,
  cardCount: 2,
  publishedCardCount: 1,
  visits30d: 120,
  conversations30d: 43,
  leads30d: 9,
  businessProfile: [
    {
      field: "business_positioning",
      value: "面向制造企业的智能化解决方案服务商",
      confidence: 0.9,
      generationVersion: 1,
      sources: [{ importItemId: "item-1", fileName: "企业介绍.pdf" }],
    },
  ],
  cards: [
    {
      id: "card-1",
      cardKind: "enterprise",
      displayName: "Acme 商务",
      title: "企业数字化服务",
      status: "published",
      updatedAt: "2026-07-15T11:00:00Z",
      shareUrl: "https://cards.example/c/card-1",
    },
    {
      id: "card-2",
      cardKind: "employee",
      displayName: "李顾问",
      title: "顾问",
      status: "draft",
      updatedAt: "2026-07-14T11:00:00Z",
    },
  ],
};

function Harness() {
  const [open, setOpen] = useState(true);
  const triggerRef = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={triggerRef}>查看 Acme 商务</button>
      {open && (
        <PlatformEnterpriseDrawer
          companyId={detail.companyId}
          returnFocusRef={triggerRef}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

describe("PlatformEnterpriseDrawer", () => {
  it("renders only aggregate fields and makes only server-published card tiles direct links", async () => {
    vi.spyOn(platformApi, "getEnterpriseDetail").mockResolvedValue({
      ...detail,
      email: "private@example.com",
      conversationBody: "private conversation",
    } as PlatformEnterpriseDetail);

    render(<Harness />);
    const drawer = await screen.findByRole("dialog");

    expect(
      within(drawer).getByRole("heading", { name: "Acme 商务", level: 2 }),
    ).toBeInTheDocument();
    expect(within(drawer).getByText("80%")) .toBeInTheDocument();
    expect(within(drawer).getByText("120")).toBeInTheDocument();
    expect(within(drawer).getByText("面向制造企业的智能化解决方案服务商")).toBeInTheDocument();
    expect(within(drawer).getByText("来源：企业介绍.pdf")).toBeInTheDocument();
    expect(within(drawer).getByText("企业官方名片")).toBeInTheDocument();
    expect(within(drawer).getByText("员工名片")).toBeInTheDocument();
    expect(
      within(drawer).getByRole("link", { name: "打开Acme 商务企业名片" }),
    ).toHaveAttribute(
      "href",
      "https://cards.example/c/card-1",
    );
    expect(
      within(drawer).getByRole("link", { name: "打开Acme 商务企业名片" }),
    ).toHaveAttribute("target", "_blank");
    expect(within(drawer).queryByRole("link", { name: /李顾问/ })).not.toBeInTheDocument();
    expect(drawer).not.toHaveTextContent("private@example.com");
    expect(drawer).not.toHaveTextContent("private conversation");
  });

  it("returns focus to the enterprise trigger after closing", async () => {
    const user = userEvent.setup();
    vi.spyOn(platformApi, "getEnterpriseDetail").mockResolvedValue(detail);
    render(<Harness />);

    await screen.findByRole("heading", { name: "Acme 商务", level: 2 });
    await user.click(screen.getByRole("button", { name: "关闭企业详情" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "查看 Acme 商务" })).toHaveFocus();
    });
  });

  it("requires a reason and submits an optimistic lifecycle transition", async () => {
    const user = userEvent.setup();
    vi.spyOn(platformApi, "getEnterpriseDetail").mockResolvedValue(detail);
    const transition = vi.spyOn(platformApi, "transitionEnterprise").mockResolvedValue({
      tenantId: detail.tenantId,
      companyId: detail.companyId,
      previousStatus: "active",
      status: "suspended",
      version: 4,
      changed: true,
      updatedAt: "2026-07-15T13:00:00Z",
    });
    render(<Harness />);

    await user.click(await screen.findByRole("button", { name: "暂停企业" }));
    const confirm = screen.getByRole("button", { name: "确认暂停企业" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "操作原因" }), "合同到期");
    await user.click(confirm);

    await waitFor(() => {
      expect(transition).toHaveBeenCalledWith("company-1", {
        expectedVersion: 3,
        targetStatus: "suspended",
        reason: "合同到期",
      });
    });
  });
});

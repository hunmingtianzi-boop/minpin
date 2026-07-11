import { FluentProvider } from "@fluentui/react-components";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { adminLightTheme } from "../theme";
import { KnowledgeEditorForm } from "./KnowledgeEditor";

describe("KnowledgeEditorForm", () => {
  it("submits trimmed FAQ content", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <FluentProvider theme={adminLightTheme}>
        <KnowledgeEditorForm
          saving={false}
          onSubmit={onSubmit}
          onCancel={() => undefined}
        />
      </FluentProvider>,
    );

    await user.type(screen.getByRole("textbox", { name: /FAQ 问题/ }), "  项目多久交付？  ");
    await user.type(screen.getByRole("textbox", { name: /标准答案/ }), "  请联系顾问确认排期。  ");
    await user.click(screen.getByRole("button", { name: "保存草稿" }));

    expect(onSubmit).toHaveBeenCalledWith({
      title: "项目多久交付？",
      answer: "请联系顾问确认排期。",
      visibility: "public",
      metadata: { source_label: "企业后台" },
    });
  });

  it("loads existing content for editing", () => {
    render(
      <FluentProvider theme={adminLightTheme}>
        <KnowledgeEditorForm
          initial={{
            title: "付款方式",
            answer: "以合同约定为准。",
            visibility: "internal",
            metadata: { source_label: "内部手册" },
          }}
          saving={false}
          onSubmit={async () => undefined}
          onCancel={() => undefined}
        />
      </FluentProvider>,
    );

    expect(screen.getByDisplayValue("付款方式")).toBeInTheDocument();
    expect(screen.getByDisplayValue("以合同约定为准。")).toBeInTheDocument();
    expect(screen.getByDisplayValue("内部手册")).toBeInTheDocument();
  });
});

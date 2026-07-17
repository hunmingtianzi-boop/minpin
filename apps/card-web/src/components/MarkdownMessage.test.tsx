import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarkdownMessage } from "./MarkdownMessage";

describe("MarkdownMessage", () => {
  it("renders normal model formatting as semantic text", () => {
    render(
      <MarkdownMessage
        content={"**重点**\n\n1. 第一项\n2. 第二项\n\n> 这是引用\n\n`示例代码`"}
      />,
    );

    expect(screen.getByText("重点").tagName).toBe("STRONG");
    expect(screen.getByRole("list")).toHaveTextContent("第一项");
    expect(screen.getByText("这是引用").closest("blockquote")).not.toBeNull();
    expect(screen.getByText("示例代码").tagName).toBe("CODE");
  });

  it("keeps links safe and does not turn model HTML into elements", () => {
    const { container } = render(
      <MarkdownMessage content={'[官网](https://example.com) <img src=x onerror="alert(1)" />'} />,
    );

    const link = screen.getByRole("link", { name: "官网" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
    expect(container.querySelector("img")).toBeNull();
  });
});

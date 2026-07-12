import { expect, test } from "@playwright/test";

const API = "http://127.0.0.1:8000/api/v1";

test("tuotu real runtime serves readable content and a grounded AI answer", async ({
  page,
  request,
}) => {
  const readiness = await request.get(`${API}/health/ready`);
  expect(readiness.ok(), "local API readiness must pass before runtime E2E").toBe(true);

  await page.goto("http://127.0.0.1:4173/c/tuotu");
  await expect(page).toHaveTitle(/拓浙 AI 集团/);
  await expect(
    page.getByText("企业可以怎样与拓浙 AI 集团合作？", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("body")).not.toContainText("ä¼");

  await page
    .getByRole("button", { name: "打开拓浙 AI 集团 AI 助手", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "拓浙 AI 集团 AI 助手" });
  await dialog.getByLabel("向资料助手提问").fill("拓浙 AI 集团主要做什么？");
  await dialog.getByRole("button", { name: "发送问题", exact: true }).click();

  const assistantMessages = dialog.locator(".message-assistant");
  await expect(assistantMessages.last()).toContainText("拓浙 AI 集团", {
    timeout: 20_000,
  });
  await expect(assistantMessages.last()).not.toContainText("知识检索暂时不可用");
  await expect(assistantMessages.last().locator("small").first()).toBeVisible();
});

import { describe, expect, it } from "vitest";

import { tuotuTenant } from "../tenants/tuotu/tenant";
import { findKnowledge } from "./knowledge";

const { knowledgeBase, fallback } = tuotuTenant.assistant;

describe("findKnowledge", () => {
  it("matches cooperation questions to the curated answer", () => {
    const result = findKnowledge("企业可以怎么合作和共建赛题？", knowledgeBase, fallback);

    expect(result.matched).toBe(true);
    expect(result.item?.id).toBe("cooperation");
    expect(result.answer).toContain("知识产权");
  });

  it("keeps uncertain questions inside the source boundary", () => {
    const result = findKnowledge("你们公司去年营收和融资是多少？", knowledgeBase, fallback);

    expect(result.matched).toBe(false);
    expect(result.answer).toContain("不能根据猜测");
    expect(result.source).toBe("资料边界规则");
  });

  it("does not invent an answer for empty input", () => {
    const result = findKnowledge("   ", knowledgeBase, fallback);

    expect(result.matched).toBe(false);
    expect(result.source).toBe("交互提示");
  });
});

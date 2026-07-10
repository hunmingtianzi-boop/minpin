import type { KnowledgeFallback, KnowledgeItem } from "../domain/card";

export type KnowledgeResult = {
  matched: boolean;
  item?: KnowledgeItem;
  answer: string;
  source: string;
};

const normalize = (value: string) =>
  value.toLocaleLowerCase("zh-CN").replace(/[\s，。！？、,.!?：:；;（）()]/g, "");

export function findKnowledge(
  query: string,
  knowledgeBase: KnowledgeItem[],
  fallback: KnowledgeFallback,
): KnowledgeResult {
  const normalizedQuery = normalize(query);

  if (!normalizedQuery) {
    return {
      matched: false,
      answer: "请先输入一个问题。你也可以直接选择下方的常见问题。",
      source: "交互提示",
    };
  }

  const ranked = knowledgeBase
    .map((item) => {
      const question = normalize(item.question);
      const score = item.keywords.reduce((total, keyword) => {
        const normalizedKeyword = normalize(keyword);
        return total + (normalizedQuery.includes(normalizedKeyword) ? 2 : 0);
      }, question.includes(normalizedQuery) || normalizedQuery.includes(question) ? 4 : 0);

      return { item, score };
    })
    .sort((a, b) => b.score - a.score);

  const best = ranked[0];
  if (!best || best.score === 0) {
    return {
      matched: false,
      ...fallback,
    };
  }

  return {
    matched: true,
    item: best.item,
    answer: best.item.answer,
    source: best.item.source,
  };
}

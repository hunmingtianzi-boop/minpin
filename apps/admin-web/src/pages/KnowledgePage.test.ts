import { describe, expect, it } from "vitest";

import type { KnowledgeDocument } from "../api/types";
import { hasPublishableDraft } from "./KnowledgePage";

function documentWith(
  status: string,
  reviewStatus?: string,
): KnowledgeDocument {
  return {
    id: "knowledge-1",
    title: "企业知识",
    status,
    latestVersion: reviewStatus
      ? {
          id: "version-1",
          versionNumber: 2,
          reviewStatus,
          chunkCount: 1,
          indexedChunkCount: 0,
        }
      : undefined,
  };
}

describe("hasPublishableDraft", () => {
  it("allows a new draft to be published", () => {
    expect(hasPublishableDraft(documentWith("draft", "draft"))).toBe(true);
  });

  it("allows a pending draft on an already published document", () => {
    expect(hasPublishableDraft(documentWith("published", "draft"))).toBe(true);
  });

  it("does not offer publication without a draft version", () => {
    expect(hasPublishableDraft(documentWith("draft"))).toBe(false);
    expect(hasPublishableDraft(documentWith("published", "approved"))).toBe(false);
  });
});

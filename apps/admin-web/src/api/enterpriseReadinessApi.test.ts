import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "./client";
import { createEnterpriseReadinessApi } from "./enterpriseReadinessApi";

describe("enterpriseReadinessApi", () => {
  it("normalizes only enterprise-safe readiness fields", async () => {
    const client = {
      get: vi.fn().mockResolvedValue({
        data: {
          generated_at: "2026-07-15T12:00:00Z",
          llm_ready: true,
          unpublished_card_count: 2,
          processing_import_batch_count: 1,
          failed_import_batch_count: 0,
          api_key: "must-not-enter-state",
          provider_base_url: "must-not-enter-state",
        },
      }),
    } as unknown as ApiClient;

    const value = await createEnterpriseReadinessApi(client).get();

    expect(value).toEqual({
      generatedAt: "2026-07-15T12:00:00Z",
      llmReady: true,
      unpublishedCardCount: 2,
      processingImportBatchCount: 1,
      failedImportBatchCount: 0,
    });
    expect(JSON.stringify(value)).not.toContain("api_key");
    expect(client.get).toHaveBeenCalledWith("/admin/readiness");
  });
});

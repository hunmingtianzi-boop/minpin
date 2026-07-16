import { apiClient, ApiClient, ApiError, unwrapData } from "./client";
import type { EnterpriseReadiness } from "./types";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonNegativeInteger(value: unknown, field: string): number {
  if (!Number.isInteger(value) || (value as number) < 0) {
    throw new ApiError(`企业就绪状态缺少 ${field}。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value as number;
}

function normalizeReadiness(value: unknown): EnterpriseReadiness {
  if (!isRecord(value) || typeof value.generated_at !== "string") {
    throw new ApiError("企业就绪状态接口返回无法识别。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  if (typeof value.llm_ready !== "boolean") {
    throw new ApiError("企业就绪状态缺少 llm_ready。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  return {
    generatedAt: value.generated_at,
    llmReady: value.llm_ready,
    unpublishedCardCount: nonNegativeInteger(
      value.unpublished_card_count,
      "unpublished_card_count",
    ),
    processingImportBatchCount: nonNegativeInteger(
      value.processing_import_batch_count,
      "processing_import_batch_count",
    ),
    failedImportBatchCount: nonNegativeInteger(
      value.failed_import_batch_count,
      "failed_import_batch_count",
    ),
  };
}

export function createEnterpriseReadinessApi(client: ApiClient = apiClient) {
  return {
    async get(): Promise<EnterpriseReadiness> {
      return normalizeReadiness(unwrapData(await client.get("/admin/readiness")));
    },
  };
}

export const enterpriseReadinessApi = createEnterpriseReadinessApi();

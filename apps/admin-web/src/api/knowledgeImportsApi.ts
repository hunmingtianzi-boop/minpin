import { apiClient, ApiClient, ApiError, unwrapData } from "./client";

type JsonRecord = Record<string, unknown>;

export type KnowledgeImportBatchStatus =
  | "pending"
  | "processing"
  | "completed"
  | "completed_with_errors"
  | "failed"
  | "dead_letter";
export type KnowledgeImportItemStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "dead_letter";

export type KnowledgeImportSourceType =
  | "pdf"
  | "docx"
  | "pptx"
  | "xlsx"
  | "csv"
  | "txt"
  | "md"
  | "html"
  | "htm"
  | "png"
  | "jpg"
  | "jpeg"
  | "webp"
  | "tiff"
  | "bmp";

/**
 * Individual pipeline stages are deliberately optional for compatibility with
 * the original import endpoint. Once available they distinguish extraction,
 * indexing and publication rather than treating a completed worker job as a
 * published knowledge item.
 */
export type KnowledgeImportStageStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "skipped";

export type KnowledgeImportItem = {
  id: string;
  fileName: string;
  sourceType: KnowledgeImportSourceType;
  status: KnowledgeImportItemStatus;
  rowNumber?: number;
  documentId?: string;
  versionId?: string;
  errorCode?: string;
  parseStatus?: KnowledgeImportStageStatus;
  indexStatus?: KnowledgeImportStageStatus;
  publishStatus?: KnowledgeImportStageStatus;
  publishedAt?: string;
  createdAt: string;
  completedAt?: string;
};

export type KnowledgeImportBatch = {
  id: string;
  status: KnowledgeImportBatchStatus;
  totalItems: number;
  pendingItems: number;
  succeededItems: number;
  failedItems: number;
  autoPublish: boolean;
  createdAt: string;
  completedAt?: string;
  items: KnowledgeImportItem[];
};

export type KnowledgeImportList = {
  items: KnowledgeImportBatch[];
  total: number;
  limit: number;
  offset: number;
};

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value) {
    throw new ApiError(`知识导入接口响应缺少 ${field}。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value;
}

function requiredCount(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new ApiError(`知识导入接口响应缺少 ${field}。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

const batchStatuses = new Set<KnowledgeImportBatchStatus>([
  "pending", "processing", "completed", "completed_with_errors", "failed", "dead_letter",
]);
const itemStatuses = new Set<KnowledgeImportItemStatus>([
  "pending", "processing", "completed", "failed", "dead_letter",
]);
const sourceTypes = new Set<KnowledgeImportSourceType>([
  "pdf", "docx", "pptx", "xlsx", "csv", "txt", "md", "html", "htm",
  "png", "jpg", "jpeg", "webp", "tiff", "bmp",
]);
const stageStatuses = new Set<KnowledgeImportStageStatus>([
  "pending", "processing", "completed", "failed", "skipped",
]);

function optionalStageStatus(value: unknown): KnowledgeImportStageStatus | undefined {
  return typeof value === "string" && stageStatuses.has(value as KnowledgeImportStageStatus)
    ? value as KnowledgeImportStageStatus
    : undefined;
}

function normalizeItem(value: unknown): KnowledgeImportItem {
  if (!isRecord(value)) {
    throw new ApiError("知识导入文件结果无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  const status = requiredString(value.status, "item.status") as KnowledgeImportItemStatus;
  const sourceType = requiredString(value.source_type, "item.source_type");
  if (!itemStatuses.has(status) || !sourceTypes.has(sourceType as KnowledgeImportSourceType)) {
    throw new ApiError("知识导入文件状态或类型无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    id: requiredString(value.id, "item.id"),
    fileName: requiredString(value.file_name, "item.file_name"),
    sourceType: sourceType as KnowledgeImportSourceType,
    status,
    rowNumber: typeof value.row_number === "number" ? value.row_number : undefined,
    documentId: optionalString(value.document_id),
    versionId: optionalString(value.version_id),
    errorCode: optionalString(value.error_code),
    parseStatus: optionalStageStatus(value.parse_status),
    indexStatus: optionalStageStatus(value.index_status),
    publishStatus: optionalStageStatus(value.publish_status),
    publishedAt: optionalString(value.published_at),
    createdAt: requiredString(value.created_at, "item.created_at"),
    completedAt: optionalString(value.completed_at),
  };
}

function normalizeBatch(value: unknown): KnowledgeImportBatch {
  if (!isRecord(value)) {
    throw new ApiError("知识导入批次响应无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  const status = requiredString(value.status, "status") as KnowledgeImportBatchStatus;
  if (!batchStatuses.has(status)) {
    throw new ApiError("知识导入批次状态无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  if (value.items !== undefined && !Array.isArray(value.items)) {
    throw new ApiError("知识导入文件列表无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    id: requiredString(value.id, "id"),
    status,
    totalItems: requiredCount(value.total_items, "total_items"),
    pendingItems: requiredCount(value.pending_items, "pending_items"),
    succeededItems: requiredCount(value.succeeded_items, "succeeded_items"),
    failedItems: requiredCount(value.failed_items, "failed_items"),
    autoPublish: value.auto_publish === true,
    createdAt: requiredString(value.created_at, "created_at"),
    completedAt: optionalString(value.completed_at),
    items: (value.items ?? []).map(normalizeItem),
  };
}

export function createKnowledgeImportsApi(client: ApiClient = apiClient) {
  return {
    async create(
      files: File[],
      options: { autoPublish?: boolean } = {},
    ): Promise<KnowledgeImportBatch> {
      const body = new FormData();
      files.forEach((file) => body.append("files", file, file.name));
      // Omit the default so older API deployments remain usable while the
      // server-side setting is rolling out. The server must still enforce that
      // only an enterprise administrator may enable it.
      if (options.autoPublish) body.append("auto_publish", "true");
      return normalizeBatch(unwrapData(await client.postForm("/admin/knowledge/imports", body)));
    },

    async list(options: { limit?: number; offset?: number } = {}): Promise<KnowledgeImportList> {
      const limit = options.limit ?? 20;
      const offset = options.offset ?? 0;
      const payload = await client.get(`/admin/knowledge/imports?limit=${limit}&offset=${offset}`);
      if (!isRecord(payload) || !Array.isArray(payload.data)) {
        throw new ApiError("知识导入批次列表无法识别。", { code: "INVALID_API_RESPONSE" });
      }
      return {
        items: payload.data.map(normalizeBatch),
        total: requiredCount(payload.total, "total"),
        limit: requiredCount(payload.limit, "limit"),
        offset: requiredCount(payload.offset, "offset"),
      };
    },

    async get(id: string): Promise<KnowledgeImportBatch> {
      return normalizeBatch(
        unwrapData(await client.get(`/admin/knowledge/imports/${encodeURIComponent(id)}`)),
      );
    },
  };
}

export const knowledgeImportsApi = createKnowledgeImportsApi();

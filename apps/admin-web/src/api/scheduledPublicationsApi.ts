import { apiClient, ApiClient, ApiError, unwrapData } from "./client";

export type ScheduledPublicationTargetType =
  | "product"
  | "case_study"
  | "knowledge_document";

export type ScheduledPublicationStatus =
  | "pending"
  | "processing"
  | "completed"
  | "cancelled"
  | "failed"
  | "dead_letter";

export type ScheduledPublication = {
  id: string;
  resourceType: ScheduledPublicationTargetType;
  resourceId: string;
  targetVersion: number;
  knowledgeVersionId?: string;
  scheduledBy: string;
  scheduledAt: string;
  status: ScheduledPublicationStatus;
  attempts: number;
  maxAttempts: number;
  nextAttemptAt: string;
  completedAt?: string;
  cancelledAt?: string;
  errorCode?: string;
  version: number;
  createdAt?: string;
  updatedAt?: string;
};

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value) {
    throw new ApiError(`定时发布接口响应缺少 ${field}。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

function normalizeScheduledPublication(value: unknown): ScheduledPublication {
  if (!isRecord(value)) {
    throw new ApiError("定时发布接口返回了无法识别的数据。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  const targetType = requiredString(value.resource_type, "resource_type");
  const status = requiredString(value.status, "status");
  if (!["product", "case_study", "knowledge_document"].includes(targetType)) {
    throw new ApiError("定时发布目标类型无法识别。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  if (!["pending", "processing", "completed", "cancelled", "failed", "dead_letter"].includes(status)) {
    throw new ApiError("定时发布状态无法识别。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  if (typeof value.version !== "number" || !Number.isFinite(value.version)) {
    throw new ApiError("定时发布接口响应缺少 version。", {
      code: "INVALID_API_RESPONSE",
    });
  }
  return {
    id: requiredString(value.id, "id"),
    resourceType: targetType as ScheduledPublicationTargetType,
    resourceId: requiredString(value.resource_id, "resource_id"),
    targetVersion: typeof value.target_version === "number" ? value.target_version : 1,
    knowledgeVersionId: optionalString(value.knowledge_version_id),
    scheduledBy: requiredString(value.scheduled_by, "scheduled_by"),
    scheduledAt: requiredString(value.scheduled_at, "scheduled_at"),
    status: status as ScheduledPublicationStatus,
    attempts: typeof value.attempts === "number" ? value.attempts : 0,
    maxAttempts: typeof value.max_attempts === "number" ? value.max_attempts : 1,
    nextAttemptAt: requiredString(value.next_attempt_at, "next_attempt_at"),
    completedAt: optionalString(value.completed_at),
    cancelledAt: optionalString(value.cancelled_at),
    errorCode: optionalString(value.error_code),
    version: value.version,
    createdAt: optionalString(value.created_at),
    updatedAt: optionalString(value.updated_at),
  };
}

export function createScheduledPublicationsApi(client: ApiClient = apiClient) {
  return {
    async list(targetType?: ScheduledPublicationTargetType): Promise<ScheduledPublication[]> {
      const payload = unwrapData(await client.get("/admin/scheduled-publishes?limit=100&offset=0"));
      const items = Array.isArray(payload)
        ? payload
        : isRecord(payload) && Array.isArray(payload.items)
          ? payload.items
          : undefined;
      if (!items) {
        throw new ApiError("定时发布列表接口返回了无法识别的数据。", {
          code: "INVALID_API_RESPONSE",
        });
      }
      const normalized = items.map(normalizeScheduledPublication);
      return targetType
        ? normalized.filter((item) => item.resourceType === targetType)
        : normalized;
    },

    async create(input: {
      targetType: ScheduledPublicationTargetType;
      targetId: string;
      scheduledFor: string;
      version: number;
      knowledgeVersionId?: string;
    }): Promise<ScheduledPublication> {
      const path =
        input.targetType === "product"
          ? `/admin/products/${encodeURIComponent(input.targetId)}:schedule-publish`
          : input.targetType === "case_study"
            ? `/admin/case-studies/${encodeURIComponent(input.targetId)}:schedule-publish`
            : `/admin/knowledge/documents/${encodeURIComponent(input.targetId)}:schedule-publish`;
      return normalizeScheduledPublication(
        unwrapData(
          await client.post(
            path,
            {
              scheduled_at: input.scheduledFor,
              version_id: input.knowledgeVersionId ?? null,
            },
            { version: input.version },
          ),
        ),
      );
    },

    async cancel(id: string, version: number): Promise<void> {
      await client.post(
        `/admin/scheduled-publishes/${encodeURIComponent(id)}:cancel`,
        {},
        { version },
      );
    },
  };
}

export const scheduledPublicationsApi = createScheduledPublicationsApi();

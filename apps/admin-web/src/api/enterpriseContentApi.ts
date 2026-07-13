import { apiClient, ApiClient, ApiError, unwrapData } from "./client";

export type EnterpriseResourceType = "product" | "case_study" | "knowledge_document";
export type ContentOverrideMode = "inherit" | "hidden" | "custom";

export type EnterpriseDistribution = {
  id: string;
  resourceType: EnterpriseResourceType;
  resourceId: string;
  isDefaultVisible: boolean;
  version: number;
  createdAt?: string;
  updatedAt?: string;
};

export type CustomContentDisplay = {
  title?: string;
  summary?: string;
  imageUrl?: string;
  sortOrder?: number;
};

export type CardContentOverride = {
  id: string;
  cardId: string;
  resourceType: EnterpriseResourceType;
  resourceId: string;
  mode: ContentOverrideMode;
  customDisplay: CustomContentDisplay;
  sourceVersion: number;
  version: number;
  createdAt?: string;
  updatedAt?: string;
};

export type CardContentOverrideRevision = Pick<
  CardContentOverride,
  "mode" | "customDisplay" | "sourceVersion"
> & {
  version: number;
  createdAt?: string;
};

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function record(value: unknown, label: string): JsonRecord {
  const data = unwrapData(value);
  if (!isRecord(data)) {
    throw new ApiError(`${label}接口返回了无法识别的数据。`, { code: "INVALID_API_RESPONSE" });
  }
  return data;
}

function nonEmpty(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ApiError(`${label}缺少有效值。`, { code: "INVALID_API_RESPONSE" });
  }
  return value.trim();
}

function number(value: unknown, label: string, minimum = 0): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum) {
    throw new ApiError(`${label}缺少有效版本。`, { code: "INVALID_API_RESPONSE" });
  }
  return value;
}

function resourceType(value: unknown): EnterpriseResourceType {
  if (value === "product" || value === "case_study" || value === "knowledge_document") {
    return value;
  }
  throw new ApiError("内容策略返回了无法识别的资源类型。", { code: "INVALID_API_RESPONSE" });
}

function overrideMode(value: unknown): ContentOverrideMode {
  if (value === "inherit" || value === "hidden" || value === "custom") return value;
  throw new ApiError("名片覆盖返回了无法识别的模式。", { code: "INVALID_API_RESPONSE" });
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function normalizeCustomDisplay(value: unknown): CustomContentDisplay {
  if (!isRecord(value)) return {};
  const sortOrder = typeof value.sort_order === "number" ? value.sort_order : value.sortOrder;
  return {
    title: optionalString(value.title),
    summary: optionalString(value.summary),
    imageUrl: optionalString(value.image_url ?? value.imageUrl),
    sortOrder: typeof sortOrder === "number" && Number.isFinite(sortOrder) ? sortOrder : undefined,
  };
}

function normalizeDistribution(value: unknown): EnterpriseDistribution {
  const data = record(value, "内容分发策略");
  return {
    id: nonEmpty(data.id, "策略 id"),
    resourceType: resourceType(data.resource_type ?? data.resourceType),
    resourceId: nonEmpty(data.resource_id ?? data.resourceId, "资源 id"),
    isDefaultVisible: Boolean(data.is_default_visible ?? data.isDefaultVisible),
    version: number(data.version, "策略 version"),
    createdAt: optionalString(data.created_at ?? data.createdAt),
    updatedAt: optionalString(data.updated_at ?? data.updatedAt),
  };
}

function normalizeOverride(value: unknown): CardContentOverride {
  const data = record(value, "名片内容覆盖");
  return {
    id: nonEmpty(data.id, "覆盖 id"),
    cardId: nonEmpty(data.card_id ?? data.cardId, "名片 id"),
    resourceType: resourceType(data.resource_type ?? data.resourceType),
    resourceId: nonEmpty(data.resource_id ?? data.resourceId, "资源 id"),
    mode: overrideMode(data.mode),
    customDisplay: normalizeCustomDisplay(data.custom_display ?? data.customDisplay),
    sourceVersion: number(data.source_version ?? data.sourceVersion, "来源版本", 1),
    version: number(data.version, "覆盖 version", 1),
    createdAt: optionalString(data.created_at ?? data.createdAt),
    updatedAt: optionalString(data.updated_at ?? data.updatedAt),
  };
}

function normalizeRevisions(value: unknown): CardContentOverrideRevision[] {
  const data = unwrapData(value);
  if (!Array.isArray(data)) {
    throw new ApiError("覆盖历史接口返回了无法识别的数据。", { code: "INVALID_API_RESPONSE" });
  }
  return data.map((item) => {
    if (!isRecord(item)) throw new ApiError("覆盖历史包含无效数据。", { code: "INVALID_API_RESPONSE" });
    return {
      mode: overrideMode(item.mode),
      customDisplay: normalizeCustomDisplay(item.custom_display ?? item.customDisplay),
      sourceVersion: number(item.source_version ?? item.sourceVersion, "来源版本", 1),
      version: number(item.version, "历史版本", 1),
      createdAt: optionalString(item.created_at ?? item.createdAt),
    };
  });
}

function pathPart(value: string) {
  return encodeURIComponent(value);
}

export function createEnterpriseContentApi(client: ApiClient) {
  return {
    async getDistribution(resourceType: EnterpriseResourceType, resourceId: string) {
      return normalizeDistribution(
        await client.get(`/admin/content-distributions/${pathPart(resourceType)}/${pathPart(resourceId)}`),
      );
    },

    async setDistribution(
      resourceType: EnterpriseResourceType,
      resourceId: string,
      version: number,
      isDefaultVisible: boolean,
    ) {
      return normalizeDistribution(
        await client.put(
          `/admin/content-distributions/${pathPart(resourceType)}/${pathPart(resourceId)}`,
          { is_default_visible: isDefaultVisible },
          { version },
        ),
      );
    },

    async listOverrides(cardId: string) {
      const envelope = record(
        await client.get(`/admin/cards/${pathPart(cardId)}/content-overrides?limit=100&offset=0`),
        "名片内容覆盖列表",
      );
      if (!Array.isArray(envelope.data)) {
        throw new ApiError("名片内容覆盖列表返回了无法识别的数据。", { code: "INVALID_API_RESPONSE" });
      }
      return envelope.data.map(normalizeOverride);
    },

    async setOverride(
      cardId: string,
      resourceType: EnterpriseResourceType,
      resourceId: string,
      version: number,
      mode: ContentOverrideMode,
      customDisplay?: CustomContentDisplay,
    ) {
      const custom_display = customDisplay
        ? {
            title: customDisplay.title,
            summary: customDisplay.summary,
            image_url: customDisplay.imageUrl,
            sort_order: customDisplay.sortOrder,
          }
        : undefined;
      return normalizeOverride(
        await client.put(
          `/admin/cards/${pathPart(cardId)}/content-overrides/${pathPart(resourceType)}/${pathPart(resourceId)}`,
          { mode, custom_display },
          { version },
        ),
      );
    },

    async deleteOverride(
      cardId: string,
      resourceType: EnterpriseResourceType,
      resourceId: string,
      version: number,
    ) {
      await client.delete(
        `/admin/cards/${pathPart(cardId)}/content-overrides/${pathPart(resourceType)}/${pathPart(resourceId)}`,
        { version },
      );
    },

    async listOverrideRevisions(cardId: string, resourceType: EnterpriseResourceType, resourceId: string) {
      return normalizeRevisions(
        await client.get(
          `/admin/cards/${pathPart(cardId)}/content-overrides/${pathPart(resourceType)}/${pathPart(resourceId)}/revisions`,
        ),
      );
    },

    async rollbackOverride(
      cardId: string,
      resourceType: EnterpriseResourceType,
      resourceId: string,
      version: number,
      revisionVersion: number,
    ) {
      return normalizeOverride(
        await client.post(
          `/admin/cards/${pathPart(cardId)}/content-overrides/${pathPart(resourceType)}/${pathPart(resourceId)}/rollback`,
          { revision_version: revisionVersion },
          { version },
        ),
      );
    },
  };
}

export const enterpriseContentApi = createEnterpriseContentApi(apiClient);

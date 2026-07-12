import { apiClient, ApiClient, ApiError, unwrapData } from "./client";

type JsonRecord = Record<string, unknown>;

export type VisitorProfileKind = "interest" | "intent";

export type VisitorProfileSignalPreview = {
  label: string;
  strength: number;
  confidence: number;
  lastSeenAt: string;
};

export type VisitorProfileListItem = {
  visitorId: string;
  firstSeenAt: string;
  lastSeenAt: string;
  signalCount: number;
  topInterests: VisitorProfileSignalPreview[];
};

export type VisitorProfileList = {
  items: VisitorProfileListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type VisitorProfileSource = {
  id: string;
  visitId?: string;
  conversationId?: string;
  summaryId?: string;
  messageId?: string;
  contribution: number;
  confidence: number;
  observedAt: string;
};

export type VisitorProfileSignal = {
  id: string;
  kind: VisitorProfileKind;
  label: string;
  strength: number;
  confidence: number;
  firstSeenAt: string;
  lastSeenAt: string;
  evidenceCount: number;
  retentionExpiresAt: string;
  sources: VisitorProfileSource[];
};

export type VisitorProfileDetail = {
  visitorId: string;
  firstSeenAt: string;
  lastSeenAt: string;
  signals: VisitorProfileSignal[];
};

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ApiError(`访客画像接口响应缺少 ${field}。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function finiteNumber(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ApiError(`访客画像接口响应缺少 ${field}。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value;
}

function nonNegativeInteger(value: unknown, field: string): number {
  const parsed = finiteNumber(value, field);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new ApiError(`访客画像接口的 ${field} 无效。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return parsed;
}

function arrayField(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new ApiError(`访客画像接口响应缺少 ${field}。`, {
      code: "INVALID_API_RESPONSE",
    });
  }
  return value;
}

function normalizePreview(value: unknown): VisitorProfileSignalPreview {
  if (!isRecord(value)) {
    throw new ApiError("访客画像兴趣数据无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    label: requiredString(value.label, "top_interests.label"),
    strength: finiteNumber(value.strength, "top_interests.strength"),
    confidence: finiteNumber(value.confidence, "top_interests.confidence"),
    lastSeenAt: requiredString(value.last_seen_at, "top_interests.last_seen_at"),
  };
}

function normalizeListItem(value: unknown): VisitorProfileListItem {
  if (!isRecord(value)) {
    throw new ApiError("访客画像列表数据无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    visitorId: requiredString(value.visitor_id, "visitor_id"),
    firstSeenAt: requiredString(value.first_seen_at, "first_seen_at"),
    lastSeenAt: requiredString(value.last_seen_at, "last_seen_at"),
    signalCount: nonNegativeInteger(value.signal_count, "signal_count"),
    topInterests: arrayField(value.top_interests, "top_interests").map(normalizePreview),
  };
}

function normalizeSource(value: unknown): VisitorProfileSource {
  if (!isRecord(value)) {
    throw new ApiError("访客画像证据数据无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    id: requiredString(value.id, "sources.id"),
    visitId: optionalString(value.visit_id),
    conversationId: optionalString(value.conversation_id),
    summaryId: optionalString(value.summary_id),
    messageId: optionalString(value.message_id),
    contribution: finiteNumber(value.contribution, "sources.contribution"),
    confidence: finiteNumber(value.confidence, "sources.confidence"),
    observedAt: requiredString(value.observed_at, "sources.observed_at"),
  };
}

function normalizeSignal(value: unknown): VisitorProfileSignal {
  if (!isRecord(value)) {
    throw new ApiError("访客画像信号数据无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  const kind = requiredString(value.kind, "signals.kind");
  if (kind !== "interest" && kind !== "intent") {
    throw new ApiError("访客画像信号类型无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    id: requiredString(value.id, "signals.id"),
    kind,
    label: requiredString(value.label, "signals.label"),
    strength: finiteNumber(value.strength, "signals.strength"),
    confidence: finiteNumber(value.confidence, "signals.confidence"),
    firstSeenAt: requiredString(value.first_seen_at, "signals.first_seen_at"),
    lastSeenAt: requiredString(value.last_seen_at, "signals.last_seen_at"),
    evidenceCount: nonNegativeInteger(value.evidence_count, "signals.evidence_count"),
    retentionExpiresAt: requiredString(
      value.retention_expires_at,
      "signals.retention_expires_at",
    ),
    sources: arrayField(value.sources, "signals.sources").map(normalizeSource),
  };
}

function normalizeDetail(value: unknown): VisitorProfileDetail {
  if (!isRecord(value)) {
    throw new ApiError("访客画像详情数据无法识别。", { code: "INVALID_API_RESPONSE" });
  }
  return {
    visitorId: requiredString(value.visitor_id, "visitor_id"),
    firstSeenAt: requiredString(value.first_seen_at, "first_seen_at"),
    lastSeenAt: requiredString(value.last_seen_at, "last_seen_at"),
    signals: arrayField(value.signals, "signals").map(normalizeSignal),
  };
}

export function createVisitorProfilesApi(client: ApiClient = apiClient) {
  return {
    async list(options: { limit?: number; offset?: number } = {}): Promise<VisitorProfileList> {
      const limit = options.limit ?? 20;
      const offset = options.offset ?? 0;
      const payload = await client.get(`/admin/visitor-profiles?offset=${offset}&limit=${limit}`);
      if (!isRecord(payload) || !Array.isArray(payload.data) || !isRecord(payload.meta)) {
        throw new ApiError("访客画像列表接口返回了无法识别的数据。", {
          code: "INVALID_API_RESPONSE",
        });
      }
      return {
        items: payload.data.map(normalizeListItem),
        total: nonNegativeInteger(payload.meta.total, "meta.total"),
        offset: nonNegativeInteger(payload.meta.offset, "meta.offset"),
        limit: nonNegativeInteger(payload.meta.limit, "meta.limit"),
      };
    },

    async get(visitorId: string): Promise<VisitorProfileDetail> {
      const payload = unwrapData(
        await client.get(`/admin/visitor-profiles/${encodeURIComponent(visitorId)}`),
      );
      return normalizeDetail(payload);
    },
  };
}

export const visitorProfilesApi = createVisitorProfilesApi();

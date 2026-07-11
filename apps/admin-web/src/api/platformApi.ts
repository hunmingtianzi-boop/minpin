import { apiClient, ApiClient, ApiError } from "./client";
import type {
  CreatePlatformEnterpriseInput,
  CreatedPlatformEnterprise,
  PlatformEnterprise,
} from "./types";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function invalid(label: string): never {
  throw new ApiError(`${label}接口返回了无法识别的数据。`, {
    code: "INVALID_API_RESPONSE",
  });
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) invalid(label);
  return value;
}

function unwrapData(value: unknown, label: string): unknown {
  if (!isRecord(value) || !("data" in value)) invalid(label);
  return value.data;
}

function enterprise(value: unknown): PlatformEnterprise {
  if (!isRecord(value)) invalid("企业");
  return {
    tenantId: requiredString(value.tenant_id, "tenant_id"),
    tenantSlug: requiredString(value.tenant_slug, "tenant_slug"),
    tenantName: requiredString(value.tenant_name, "tenant_name"),
    companyId: requiredString(value.company_id, "company_id"),
    companyName: requiredString(value.company_name, "company_name"),
    status: requiredString(value.status ?? value.company_status, "status"),
    createdAt: requiredString(value.created_at, "created_at"),
  };
}

function createdEnterprise(value: unknown): CreatedPlatformEnterprise {
  if (!isRecord(value)) invalid("新建企业");
  return {
    ...enterprise(value),
    adminUserId: requiredString(value.admin_user_id, "admin_user_id"),
    adminMembershipId: requiredString(
      value.admin_membership_id,
      "admin_membership_id",
    ),
    initialCardId: requiredString(value.initial_card_id, "initial_card_id"),
    initialCardSlug: requiredString(value.initial_card_slug, "initial_card_slug"),
  };
}

export function createPlatformApi(client: ApiClient) {
  return {
    async listEnterprises(limit = 50, offset = 0): Promise<PlatformEnterprise[]> {
      const payload = await client.get(
        `/platform/enterprises?limit=${limit}&offset=${offset}`,
      );
      const values = unwrapData(payload, "企业列表");
      if (!Array.isArray(values)) invalid("企业列表");
      return values.map(enterprise);
    },

    async createEnterprise(
      input: CreatePlatformEnterpriseInput,
    ): Promise<CreatedPlatformEnterprise> {
      const payload = await client.post("/platform/enterprises", {
        tenant_slug: input.tenantSlug.trim(),
        tenant_name: input.tenantName.trim(),
        company_name: input.companyName.trim(),
        industry: input.industry?.trim() || null,
        admin_account: input.adminAccount.trim(),
        admin_display_name: input.adminDisplayName.trim(),
        admin_password: input.adminPassword,
        initial_card_title: input.initialCardTitle?.trim() || null,
      });
      return createdEnterprise(unwrapData(payload, "新建企业"));
    },
  };
}

export const platformApi = createPlatformApi(apiClient);

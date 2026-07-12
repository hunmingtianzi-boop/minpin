import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "./client";
import { createScheduledPublicationsApi } from "./scheduledPublicationsApi";

const row = {
  id: "schedule-1",
  resource_type: "product",
  resource_id: "product-1",
  target_version: 3,
  knowledge_version_id: null,
  scheduled_by: "11111111-1111-1111-1111-111111111111",
  scheduled_at: "2026-07-13T01:00:00Z",
  status: "pending",
  attempts: 0,
  max_attempts: 5,
  next_attempt_at: "2026-07-13T01:00:00Z",
  completed_at: null,
  cancelled_at: null,
  error_code: null,
  version: 3,
  created_at: "2026-07-12T01:00:00Z",
  updated_at: "2026-07-12T01:00:00Z",
};

async function authenticatedClient(fetcher: ReturnType<typeof vi.fn<typeof fetch>>) {
  const client = new ApiClient({ baseUrl: "https://api.example.test", fetcher });
  await client.login("admin", "password");
  return client;
}

describe("scheduledPublicationsApi", () => {
  it("lists, creates and cancels a normalized schedule", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        access_token: "access", csrf_token: "csrf",
      } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: [row] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: row }), { status: 201 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const api = createScheduledPublicationsApi(await authenticatedClient(fetcher));

    await expect(api.list("product")).resolves.toEqual([
      expect.objectContaining({ id: "schedule-1", resourceType: "product", status: "pending" }),
    ]);
    await api.create({
      targetType: "product",
      targetId: "product-1",
      scheduledFor: "2026-07-13T01:00:00Z",
      version: 3,
    });
    await api.cancel("schedule-1", 3);

    expect(fetcher.mock.calls[1][0]).toBe(
      "https://api.example.test/admin/scheduled-publishes?limit=100&offset=0",
    );
    expect(JSON.parse(String(fetcher.mock.calls[2][1]?.body))).toEqual({
      scheduled_at: "2026-07-13T01:00:00Z",
      version_id: null,
    });
    expect(fetcher.mock.calls[2][0]).toBe(
      "https://api.example.test/admin/products/product-1:schedule-publish",
    );
    expect((fetcher.mock.calls[2][1]?.headers as Headers).get("If-Match")).toBe("3");
    expect(fetcher.mock.calls[3][0]).toBe(
      "https://api.example.test/admin/scheduled-publishes/schedule-1:cancel",
    );
    expect((fetcher.mock.calls[3][1]?.headers as Headers).get("If-Match")).toBe("3");
  });

  it("rejects unknown target types from the server", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        access_token: "access", csrf_token: "csrf",
      } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        data: [{ ...row, resource_type: "card" }],
      }), { status: 200 }));
    const api = createScheduledPublicationsApi(await authenticatedClient(fetcher));

    await expect(api.list()).rejects.toMatchObject({ code: "INVALID_API_RESPONSE" });
  });
});

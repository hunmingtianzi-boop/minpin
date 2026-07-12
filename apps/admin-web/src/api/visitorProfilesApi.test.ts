import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError } from "./client";
import { createVisitorProfilesApi } from "./visitorProfilesApi";

async function authenticatedClient(fetcher: ReturnType<typeof vi.fn<typeof fetch>>) {
  const client = new ApiClient({ baseUrl: "https://api.example.test", fetcher });
  await client.login("admin", "password");
  return client;
}

const preview = {
  label: "智能名片",
  strength: 0.8,
  confidence: 0.9,
  last_seen_at: "2026-07-12T02:00:00Z",
};

describe("visitorProfilesApi", () => {
  it("normalizes the paginated list and encoded detail request", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        access_token: "access", csrf_token: "csrf",
      } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        data: [{
          visitor_id: "visitor/1", first_seen_at: "2026-07-10T00:00:00Z",
          last_seen_at: "2026-07-12T02:00:00Z", signal_count: 2,
          top_interests: [preview], ignored_message_content: "不得进入前端模型",
        }],
        meta: { total: 21, offset: 20, limit: 20 },
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        visitor_id: "visitor/1", first_seen_at: "2026-07-10T00:00:00Z",
        last_seen_at: "2026-07-12T02:00:00Z",
        signals: [{
          id: "signal-1", kind: "intent", label: "咨询合作", strength: 0.7,
          confidence: 0.85, first_seen_at: "2026-07-11T00:00:00Z",
          last_seen_at: "2026-07-12T02:00:00Z", evidence_count: 1,
          retention_expires_at: "2026-10-12T02:00:00Z",
          sources: [{
            id: "source-1", visit_id: "visit-1", conversation_id: "conversation-1",
            summary_id: "summary-1", message_id: "message-1", contribution: 0.7,
            confidence: 0.85, observed_at: "2026-07-12T02:00:00Z",
            message_content: "不得解析原始正文",
          }],
        }],
      } }), { status: 200 }));
    const api = createVisitorProfilesApi(await authenticatedClient(fetcher));

    const list = await api.list({ offset: 20, limit: 20 });
    expect(list).toEqual({
      items: [{
        visitorId: "visitor/1", firstSeenAt: "2026-07-10T00:00:00Z",
        lastSeenAt: "2026-07-12T02:00:00Z", signalCount: 2,
        topInterests: [{ ...preview, lastSeenAt: preview.last_seen_at, last_seen_at: undefined }],
      }],
      total: 21, offset: 20, limit: 20,
    });
    const detail = await api.get("visitor/1");
    expect(detail.signals[0]).toMatchObject({
      kind: "intent", label: "咨询合作", sources: [{ visitId: "visit-1", messageId: "message-1" }],
    });
    expect(detail).not.toHaveProperty("message_content");
    expect(fetcher.mock.calls[1][0]).toBe(
      "https://api.example.test/admin/visitor-profiles?offset=20&limit=20",
    );
    expect(fetcher.mock.calls[2][0]).toBe(
      "https://api.example.test/admin/visitor-profiles/visitor%2F1",
    );
  });

  it("rejects malformed or unknown signal data", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        access_token: "access", csrf_token: "csrf",
      } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: {
        visitor_id: "visitor-1", first_seen_at: "2026-07-10T00:00:00Z",
        last_seen_at: "2026-07-12T02:00:00Z", signals: [{ kind: "private_note" }],
      } }), { status: 200 }));
    const api = createVisitorProfilesApi(await authenticatedClient(fetcher));

    await expect(api.get("visitor-1")).rejects.toBeInstanceOf(ApiError);
  });
});

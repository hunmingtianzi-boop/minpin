import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "./client";
import { createKnowledgeImportsApi } from "./knowledgeImportsApi";

const item = {
  id: "item-1", file_name: "knowledge.pdf", source_type: "pdf", status: "completed",
  row_number: null, document_id: "document-1", version_id: "version-1", error_code: null,
  created_at: "2026-07-12T00:00:00Z", completed_at: "2026-07-12T00:01:00Z",
};
const batch = {
  id: "batch-1", status: "completed", total_items: 1, pending_items: 0,
  succeeded_items: 1, failed_items: 0, created_at: "2026-07-12T00:00:00Z",
  completed_at: "2026-07-12T00:01:00Z", items: [item],
};

function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

describe("knowledgeImportsApi", () => {
  it("uploads repeated multipart files without forcing a JSON content type", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ data: { access_token: "access", csrf_token: "csrf" } }))
      .mockResolvedValueOnce(response({ data: batch }, 202));
    const client = new ApiClient({ baseUrl: "https://api.example.test", fetcher });
    await client.login("admin", "password");
    const api = createKnowledgeImportsApi(client);

    await expect(api.create([
      new File(["pdf"], "knowledge.pdf", { type: "application/pdf" }),
      new File(["raw_text,title\nanswer,FAQ"], "faq.csv", { type: "text/csv" }),
    ])).resolves.toMatchObject({ id: "batch-1", succeededItems: 1 });

    const request = fetcher.mock.calls[1][1];
    expect(request?.body).toBeInstanceOf(FormData);
    expect((request?.body as FormData).getAll("files")).toHaveLength(2);
    expect((request?.headers as Headers).has("Content-Type")).toBe(false);
  });

  it("sends automatic publication only when the enterprise admin opts in", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ data: { access_token: "access", csrf_token: "csrf" } }))
      .mockResolvedValueOnce(response({ data: { ...batch, auto_publish: true } }, 202));
    const client = new ApiClient({ baseUrl: "https://api.example.test", fetcher });
    await client.login("admin", "password");
    const api = createKnowledgeImportsApi(client);

    await api.create([new File(["pdf"], "knowledge.pdf", { type: "application/pdf" })], {
      autoPublish: true,
    });

    const form = fetcher.mock.calls[1][1]?.body as FormData;
    expect(form.get("auto_publish")).toBe("true");
  });

  it("normalizes list and detail responses", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ data: { access_token: "access", csrf_token: "csrf" } }))
      .mockResolvedValueOnce(response({ data: [{ ...batch, items: [] }], total: 1, limit: 20, offset: 0 }))
      .mockResolvedValueOnce(response({ data: batch }));
    const client = new ApiClient({ baseUrl: "https://api.example.test", fetcher });
    await client.login("admin", "password");
    const api = createKnowledgeImportsApi(client);

    await expect(api.list()).resolves.toMatchObject({ total: 1, items: [{ id: "batch-1" }] });
    await expect(api.get("batch-1")).resolves.toMatchObject({
      items: [{ fileName: "knowledge.pdf", documentId: "document-1" }],
    });
  });

  it("deletes a settled import batch", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ data: { access_token: "access", csrf_token: "csrf" } }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = new ApiClient({ baseUrl: "https://api.example.test", fetcher });
    await client.login("admin", "password");

    await createKnowledgeImportsApi(client).deleteBatch("batch/1");

    expect(fetcher.mock.calls[1][0]).toBe("https://api.example.test/admin/knowledge/imports/batch%2F1");
    expect(fetcher.mock.calls[1][1]?.method).toBe("DELETE");
  });
});

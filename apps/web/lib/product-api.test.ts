import { afterEach, describe, expect, it, vi } from "vitest";

import { ProductApiError, getEventDetail, getEvents } from "./product-api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json"
    }
  });
}

describe("Product API client", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("loads event cards from GET /events without requiring source_refs", async () => {
    vi.stubEnv("AI_WORLD_RADAR_API_BASE_URL", "http://api.test");
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        items: [
          {
            id: "pub_1",
            slug: "hn-openai-coding-agents",
            title: "开发者社区讨论 OpenAI 式编码 Agent",
            card_summary: "讨论焦点从工具能力转向团队协作和代码审查。",
            detail_summary: "详情摘要",
            category: "Agent 与开发",
            signal_label: "高热讨论",
            cover_image_url: null,
            homepage_rank: 1,
            source_hint: "Hacker News 等 2 源",
            source_count: 2,
            published_at: "2026-06-23T02:40:00Z"
          }
        ],
        limit: 20,
        offset: 0
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await getEvents();

    expect(fetchMock).toHaveBeenCalledWith("http://api.test/events?offset=0", { cache: "no-store" });
    expect(result.items[0]).toMatchObject({
      slug: "hn-openai-coding-agents",
      source_hint: "Hacker News 等 2 源",
      source_count: 2,
      cover_image_url: null
    });
    expect("source_refs" in result.items[0]).toBe(false);
  });

  it("passes an explicit event limit only when the caller asks for one", async () => {
    vi.stubEnv("AI_WORLD_RADAR_API_BASE_URL", "http://api.test");
    const fetchMock = vi.fn(async () => jsonResponse({ items: [], limit: 12, offset: 0 }));
    vi.stubGlobal("fetch", fetchMock);

    await getEvents({ limit: 12, offset: 0 });

    expect(fetchMock).toHaveBeenCalledWith("http://api.test/events?limit=12&offset=0", { cache: "no-store" });
  });

  it("loads event detail with full source_refs", async () => {
    vi.stubEnv("AI_WORLD_RADAR_API_BASE_URL", "http://api.test/");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          id: "pub_1",
          slug: "openai-python-v243",
          title: "OpenAI Python SDK v2.43.0",
          detail_summary: "SDK 继续补齐 Responses 与工具调用能力。",
          detail_body: "第一段。\n\n第二段。",
          why_it_matters: "SDK 更新会影响真实项目的接口选择。",
          follow_up_points: ["观察迁移成本"],
          source_refs: [
            {
              title: "GitHub Release",
              url: "https://github.com/openai/openai-python/releases"
            }
          ],
          category: "开发者工具",
          signal_label: "官方发布",
          cover_image_url: "https://example.com/cover.png",
          published_at: "2026-06-22T09:20:00Z"
        })
      )
    );

    const detail = await getEventDetail("openai-python-v243");

    expect(detail.source_refs).toEqual([
      {
        title: "GitHub Release",
        url: "https://github.com/openai/openai-python/releases"
      }
    ]);
  });

  it("throws a typed not-found error for missing details", async () => {
    vi.stubEnv("AI_WORLD_RADAR_API_BASE_URL", "http://api.test");
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "Event not found" }, 404)));

    await expect(getEventDetail("missing")).rejects.toMatchObject({
      name: "ProductApiError",
      status: 404,
      isNotFound: true
    } satisfies Partial<ProductApiError>);
  });
});

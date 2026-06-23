import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EventDetail } from "./EventDetail";
import type { ProductEventDetail } from "../lib/product-api";

const detail: ProductEventDetail = {
  id: "pub_1",
  slug: "openai-python-v243",
  title: "OpenAI Python SDK v2.43.0",
  detail_summary: "SDK 继续补齐 Responses 与工具调用能力。",
  detail_body: "第一段解释。\n\n第二段说明影响。",
  why_it_matters: "SDK 更新会影响真实项目的接口选择。",
  follow_up_points: ["观察迁移成本", "观察框架适配"],
  source_refs: [
    {
      title: "GitHub Release",
      url: "https://github.com/openai/openai-python/releases"
    }
  ],
  category: "开发者工具",
  signal_label: "官方发布",
  cover_image_url: null,
  published_at: "2026-06-22T09:20:00Z"
};

describe("EventDetail", () => {
  it("renders dossier sections and source trail", () => {
    render(<EventDetail event={detail} now={new Date("2026-06-23T10:00:00Z")} />);

    expect(screen.getByRole("heading", { name: "OpenAI Python SDK v2.43.0" })).toBeInTheDocument();
    expect(screen.getByText("SDK 继续补齐 Responses 与工具调用能力。")).toBeInTheDocument();
    expect(screen.getByText("第一段解释。")).toBeInTheDocument();
    expect(screen.getByText("第二段说明影响。")).toBeInTheDocument();
    expect(screen.getByText("SDK 更新会影响真实项目的接口选择。")).toBeInTheDocument();
    expect(screen.getByText("观察迁移成本")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /GitHub Release/ })).toHaveAttribute(
      "href",
      "https://github.com/openai/openai-python/releases"
    );
  });

  it("renders category fallback when cover image is missing", () => {
    render(<EventDetail event={detail} now={new Date("2026-06-23T10:00:00Z")} />);

    expect(screen.getByTestId("detail-cover-fallback")).toHaveTextContent("开发者工具");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});

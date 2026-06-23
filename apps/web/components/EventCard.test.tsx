import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EventCard } from "./EventCard";
import type { ProductEventListItem } from "../lib/product-api";

const event: ProductEventListItem = {
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
  published_at: "2026-06-23T04:00:00Z"
};

describe("EventCard", () => {
  it("renders event card content and links to detail", () => {
    render(<EventCard event={event} now={new Date("2026-06-23T10:00:00Z")} />);

    expect(screen.getByRole("link", { name: /开发者社区讨论 OpenAI 式编码 Agent/ })).toHaveAttribute(
      "href",
      "/events/hn-openai-coding-agents"
    );
    expect(screen.getByText("讨论焦点从工具能力转向团队协作和代码审查。")).toBeInTheDocument();
    expect(screen.getByText("6 小时前")).toBeInTheDocument();
  });

  it("keeps source hint in a right-aligned single-line element", () => {
    render(<EventCard event={event} now={new Date("2026-06-23T10:00:00Z")} />);

    const source = screen.getByText("Hacker News 等 2 源");

    expect(source).toHaveClass("event-card__source");
  });

  it("renders category fallback when cover image is missing", () => {
    render(<EventCard event={event} now={new Date("2026-06-23T10:00:00Z")} />);

    expect(screen.getByTestId("cover-fallback")).toHaveTextContent("Agent 与开发");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});

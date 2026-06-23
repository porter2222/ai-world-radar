import { describe, expect, it } from "vitest";

import { formatRelativeTime, sourceDomain, splitBodyParagraphs } from "./format";

describe("formatRelativeTime", () => {
  const now = new Date("2026-06-23T10:00:00Z");

  it("formats recent timestamps as short Chinese relative labels", () => {
    expect(formatRelativeTime("2026-06-23T09:30:00Z", now)).toBe("30 分钟前");
    expect(formatRelativeTime("2026-06-23T04:00:00Z", now)).toBe("6 小时前");
    expect(formatRelativeTime("2026-06-22T10:00:00Z", now)).toBe("昨天");
  });

  it("formats older timestamps as compact dates", () => {
    expect(formatRelativeTime("2026-06-20T10:00:00Z", now)).toBe("2026.06.20");
  });
});

describe("splitBodyParagraphs", () => {
  it("splits blank-line separated detail body into natural paragraphs", () => {
    expect(splitBodyParagraphs("第一段。\n\n第二段。\n \n第三段。")).toEqual(["第一段。", "第二段。", "第三段。"]);
  });
});

describe("sourceDomain", () => {
  it("extracts readable domains from source URLs", () => {
    expect(sourceDomain("https://news.ycombinator.com/item?id=1")).toBe("news.ycombinator.com");
    expect(sourceDomain("https://github.com/openai/openai-python/releases")).toBe("github.com");
  });
});

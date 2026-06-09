from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


HN_ALGOLIA_ENDPOINT = "https://hn.algolia.com/api/v1/search_by_date"

DEFAULT_QUERY_PROFILE = [
    "OpenAI",
    "ChatGPT",
    "Anthropic",
    "Claude",
    "Google DeepMind",
    "Gemini",
    "NVIDIA",
    "Hugging Face",
    "LLM",
    "AI agent",
    "AI coding",
    "Cursor",
    "GitHub Copilot",
    "MCP",
    "machine learning",
]


@dataclass(frozen=True)
class HNStory:
    """HN story 的规范化结构。

    输入：HN Algolia hit 解析后的基础字段。
    输出：供 EvidenceAgentStub 和 pipeline 使用的稳定数据对象。
    """

    hn_id: str
    title: str
    original_url: str | None
    author: str | None
    points: int
    num_comments: int
    created_at: datetime | None
    created_at_i: int | None
    story_text: str | None
    hn_heat_score: int
    matched_query: str


def calculate_hn_heat_score(points: int | None, num_comments: int | None) -> int:
    """计算 HN 热度分。

    输入：HN points 和评论数，可为空。
    输出：`points + num_comments * 2`，空值按 0 处理。
    """
    return (points or 0) + (num_comments or 0) * 2


def parse_algolia_hit(hit: dict[str, Any], query: str) -> HNStory:
    """把 HN Algolia 单条 hit 转成 HNStory。

    输入：Algolia 返回的 hit 字典，以及命中的 query 关键词。
    输出：包含标题、URL、作者、时间和热度分的 `HNStory`。
    """
    points = int(hit.get("points") or 0)
    num_comments = int(hit.get("num_comments") or 0)
    created_at = _parse_datetime(hit.get("created_at"))

    return HNStory(
        hn_id=str(hit["objectID"]),
        title=(hit.get("title") or hit.get("story_title") or "").strip(),
        original_url=hit.get("url") or hit.get("story_url"),
        author=hit.get("author"),
        points=points,
        num_comments=num_comments,
        created_at=created_at,
        created_at_i=hit.get("created_at_i"),
        story_text=hit.get("story_text"),
        hn_heat_score=calculate_hn_heat_score(points, num_comments),
        matched_query=query,
    )


def collect_from_algolia_payload(payload: dict[str, Any], query: str, limit: int) -> list[HNStory]:
    """从 Algolia 响应中提取、去重并排序 story。

    输入：完整响应 payload、当前 query、最大保留数量。
    输出：按 HN 热度分降序排列的 `HNStory` 列表。
    """
    stories = [parse_algolia_hit(hit, query=query) for hit in payload.get("hits", []) if _is_story(hit)]
    return sorted(dedupe_stories(stories), key=lambda story: story.hn_heat_score, reverse=True)[:limit]


def dedupe_stories(stories: list[HNStory]) -> list[HNStory]:
    """对 HN story 做基础去重。

    输入：可能包含重复 HN ID 或重复 URL 的 story 列表。
    输出：去重后的列表；重复项保留热度分更高的一条。
    """
    deduped: list[HNStory] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()

    for story in sorted(stories, key=lambda item: item.hn_heat_score, reverse=True):
        normalized_url = normalize_url(story.original_url)
        if story.hn_id in seen_ids or (normalized_url and normalized_url in seen_urls):
            continue
        deduped.append(story)
        seen_ids.add(story.hn_id)
        if normalized_url:
            seen_urls.add(normalized_url)

    return deduped


def fetch_hn_stories(days: int = 7, limit: int = 100, queries: list[str] | None = None) -> list[HNStory]:
    """请求 HN Algolia API 并返回 P1 候选 story。

    输入：时间窗口天数、最大数量、可选 query profile。
    输出：最近窗口内按热度排序、已去重的 HN story 列表。
    """
    queries = queries or DEFAULT_QUERY_PROFILE
    window_start = int((datetime.now(UTC) - timedelta(days=days)).timestamp())
    all_stories: list[HNStory] = []

    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        for query in queries:
            response = client.get(
                HN_ALGOLIA_ENDPOINT,
                params={
                    "query": query,
                    "tags": "story",
                    "numericFilters": f"created_at_i>{window_start}",
                    "hitsPerPage": limit,
                },
            )
            response.raise_for_status()
            all_stories.extend(collect_from_algolia_payload(response.json(), query=query, limit=limit))

    return sorted(dedupe_stories(all_stories), key=lambda story: story.hn_heat_score, reverse=True)[:limit]


def normalize_url(url: str | None) -> str | None:
    """规范化 URL 以便去重。

    输入：原始 URL，可为空。
    输出：去掉 query/fragment、统一 scheme/host 大小写后的 URL；空输入返回 None。
    """
    if not url:
        return None
    parsed = urlsplit(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _is_story(hit: dict[str, Any]) -> bool:
    """判断 Algolia hit 是否为 story。

    输入：Algolia hit 字典。
    输出：布尔值；没有 tags 或包含 `story` 时视为 story。
    """
    tags = set(hit.get("_tags") or [])
    return not tags or "story" in tags


def _parse_datetime(value: str | None) -> datetime | None:
    """解析 HN 返回的 ISO 时间。

    输入：可能带 `Z` 的时间字符串。
    输出：timezone-aware `datetime`；空值返回 None。
    """
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

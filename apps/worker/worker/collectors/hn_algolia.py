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
    return (points or 0) + (num_comments or 0) * 2


def parse_algolia_hit(hit: dict[str, Any], query: str) -> HNStory:
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
    stories = [parse_algolia_hit(hit, query=query) for hit in payload.get("hits", []) if _is_story(hit)]
    return sorted(dedupe_stories(stories), key=lambda story: story.hn_heat_score, reverse=True)[:limit]


def dedupe_stories(stories: list[HNStory]) -> list[HNStory]:
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
    if not url:
        return None
    parsed = urlsplit(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _is_story(hit: dict[str, Any]) -> bool:
    tags = set(hit.get("_tags") or [])
    return not tags or "story" in tags


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

from __future__ import annotations

from worker.collectors.hn_algolia import HN_ALGOLIA_ENDPOINT, HNStory, normalize_url
from worker.schemas.source import SourceCreate, SourceSignalCreate


def build_hn_source() -> SourceCreate:
    """构造 HN Algolia 来源配置。

    输入：无。
    输出：可交给 SignalService.upsert_source 的 SourceCreate。
    """
    return SourceCreate(
        source_key="hn_algolia",
        name="Hacker News Algolia",
        source_type="community",
        fetch_method="api",
        entry_url=HN_ALGOLIA_ENDPOINT,
        fetch_config={"endpoint": HN_ALGOLIA_ENDPOINT, "tags": "story"},
    )


def hn_story_to_signal(story: HNStory) -> SourceSignalCreate:
    """把 HNStory 映射成新版来源信号。

    输入：HN Algolia collector 已规范化的 HNStory。
    输出：可交给 SignalService.upsert_signal 的 SourceSignalCreate。
    """
    hn_url = _build_hn_item_url(story.hn_id)
    original_url = story.original_url or hn_url
    canonical_url = _canonicalize_story_url(story.original_url, fallback_hn_url=hn_url)

    return SourceSignalCreate(
        source_key="hn_algolia",
        source_item_id=story.hn_id,
        original_title=story.title,
        original_url=original_url,
        canonical_url=canonical_url,
        published_at=story.created_at,
        language="en",
        raw_summary=_build_raw_summary(story),
        content_excerpt=story.story_text,
        source_hash=f"hn_algolia:{story.hn_id}",
        heat_metrics={
            "points": story.points,
            "comments": story.num_comments,
            "hn_heat_score": story.hn_heat_score,
        },
        metadata={
            "source": "hn_algolia",
            "author": story.author,
            "matched_query": story.matched_query,
            "created_at_i": story.created_at_i,
            "hn_url": hn_url,
        },
    )


def _build_hn_item_url(hn_id: str) -> str:
    """生成 HN item 页面地址。

    输入：HN objectID。
    输出：可打开的 HN item URL。
    """
    return f"https://news.ycombinator.com/item?id={hn_id}"


def _canonicalize_story_url(original_url: str | None, *, fallback_hn_url: str) -> str:
    """生成 HN signal 的 canonical_url。

    输入：外部原文 URL 和 HN fallback URL。
    输出：普通外链使用通用 URL 规范化；无外链时保留 HN item 的 id query。
    """
    if not original_url:
        return fallback_hn_url
    return normalize_url(original_url) or original_url


def _build_raw_summary(story: HNStory) -> str:
    """生成 HN signal 的原始摘要。

    输入：HNStory 的热度、命中词和可选 story_text。
    输出：短文本摘要，供后续 Agent stub 或人工 review 理解来源上下文。
    """
    summary = f"HN: {story.points} points, {story.num_comments} comments, matched query {story.matched_query}."
    if story.story_text:
        return f"{summary} {story.story_text}"
    return summary

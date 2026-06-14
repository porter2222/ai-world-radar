from datetime import UTC, datetime

from worker.collectors.hn_algolia import HNStory
from worker.sources.hn_source import build_hn_source, hn_story_to_signal


def make_story(original_url: str | None = "https://example.com/openai-coding-agent/?ref=hn#comments") -> HNStory:
    """构造 HNStory 测试数据。

    输入：可选 original_url，用于覆盖有外链和无外链两种场景。
    输出：字段完整、热度固定的 HNStory fixture。
    """
    return HNStory(
        hn_id="1001",
        title="OpenAI launches a new coding agent",
        original_url=original_url,
        author="alice",
        points=41,
        num_comments=12,
        created_at=datetime(2026, 6, 8, 10, 0, tzinfo=UTC),
        created_at_i=1780912800,
        story_text="HN discussion starter",
        hn_heat_score=65,
        matched_query="OpenAI",
    )


def test_build_hn_source_describes_algolia_api():
    """验证 HN source 配置符合新版 SourceCreate 契约。

    输入：无。
    输出：断言 source_key、来源类型、抓取方式和入口 URL 稳定。
    """
    source = build_hn_source()

    assert source.source_key == "hn_algolia"
    assert source.name == "Hacker News Algolia"
    assert source.source_type == "community"
    assert source.fetch_method == "api"
    assert source.entry_url == "https://hn.algolia.com/api/v1/search_by_date"


def test_hn_story_maps_to_source_signal_create():
    """验证 HNStory 能映射为 SourceSignalCreate。

    输入：带原文 URL、points、comments 和 matched_query 的 HNStory。
    输出：断言 source_hash、canonical_url、热度指标和 metadata 均符合 P1-3 口径。
    """
    signal = hn_story_to_signal(make_story())

    assert signal.source_key == "hn_algolia"
    assert signal.source_item_id == "1001"
    assert signal.source_hash == "hn_algolia:1001"
    assert signal.original_title == "OpenAI launches a new coding agent"
    assert signal.original_url == "https://example.com/openai-coding-agent/?ref=hn#comments"
    assert signal.canonical_url == "https://example.com/openai-coding-agent"
    assert signal.published_at == datetime(2026, 6, 8, 10, 0, tzinfo=UTC)
    assert signal.raw_summary == "HN: 41 points, 12 comments, matched query OpenAI. HN discussion starter"
    assert signal.heat_metrics == {"points": 41, "comments": 12, "hn_heat_score": 65}
    assert signal.metadata["author"] == "alice"
    assert signal.metadata["matched_query"] == "OpenAI"
    assert signal.metadata["hn_url"] == "https://news.ycombinator.com/item?id=1001"


def test_hn_story_without_external_url_uses_hn_item_url():
    """验证无外链 HNStory 会回退到 HN item URL。

    输入：original_url 为空的 HNStory。
    输出：SourceSignalCreate 的 original_url 与 canonical_url 都指向 HN item URL。
    """
    signal = hn_story_to_signal(make_story(original_url=None))

    assert signal.original_url == "https://news.ycombinator.com/item?id=1001"
    assert signal.canonical_url == "https://news.ycombinator.com/item?id=1001"

from datetime import UTC, datetime
from pathlib import Path

from worker.collectors.official_news import OfficialSourceProfile, collect_from_feed_xml, collect_from_news_html
from worker.sources.official_news_source import build_official_news_source, official_news_entry_to_signal


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_text(filename: str) -> str:
    """读取官方源 fixture 文本。
    输入：fixture 文件名。
    输出：UTF-8 解码后的 XML 或 HTML 文本。
    """
    return (FIXTURE_DIR / filename).read_text(encoding="utf-8")


def test_rss_feed_entry_maps_to_source_signal():
    """验证 RSS feed item 可以映射为官方来源信号。
    输入：NVIDIA RSS fixture 与 rss profile。
    输出：断言 source 配置、entry 字段和 SourceSignalCreate 均符合官方源口径。
    """
    profile = OfficialSourceProfile(
        source_key="nvidia_news",
        name="NVIDIA News",
        mode="rss",
        entry_url="https://nvidianews.nvidia.com/rss",
    )
    entry = collect_from_feed_xml(load_text("official_rss_feed.xml"), profile=profile, limit=1)[0]
    source = build_official_news_source(profile)
    signal = official_news_entry_to_signal(entry)

    assert source.source_key == "nvidia_news"
    assert source.source_type == "official"
    assert source.fetch_method == "rss"
    assert entry.entry_id == "nvidia-ai-factory-2026"
    assert entry.title == "NVIDIA unveils new AI factory platform"
    assert entry.url == "https://nvidianews.nvidia.com/news/ai-factory-platform?utm_source=rss"
    assert entry.published_at == datetime(2026, 6, 23, 9, 0, tzinfo=UTC)
    assert signal.source_key == "nvidia_news"
    assert signal.source_hash.startswith("official_news:nvidia_news:")
    assert signal.source_item_id == "nvidia-ai-factory-2026"
    assert signal.canonical_url == "https://nvidianews.nvidia.com/news/ai-factory-platform"
    assert signal.heat_metrics["official_source"] is True
    assert signal.metadata["profile_key"] == "nvidia_news"
    assert signal.metadata["mode"] == "rss"


def test_atom_feed_entry_maps_to_official_news_entry():
    """验证 Atom entry 可以解析为官方来源条目。
    输入：GitHub Changelog Atom fixture 与 atom profile。
    输出：断言 entry id、alternate link、更新时间和 summary 被正确读取。
    """
    profile = OfficialSourceProfile(
        source_key="github_changelog",
        name="GitHub Changelog",
        mode="atom",
        entry_url="https://github.blog/changelog/feed/",
    )

    entries = collect_from_feed_xml(load_text("official_atom_feed.xml"), profile=profile, limit=1)

    assert len(entries) == 1
    assert entries[0].entry_id == "tag:github.blog,2026:copilot-workspace-update"
    assert entries[0].title == "GitHub Copilot adds workspace planning updates"
    assert entries[0].url == "https://github.blog/changelog/2026-06-23-copilot-workspace-update/?utm_source=atom"
    assert entries[0].published_at == datetime(2026, 6, 23, 11, 15, tzinfo=UTC)
    assert entries[0].summary == "GitHub updated Copilot workspace planning for larger AI coding tasks."


def test_html_news_page_entry_maps_to_source_signal():
    """验证轻量 HTML 列表页可以解析为官方来源信号。
    输入：OpenAI News HTML fixture 与 html profile。
    输出：断言只从列表页提取标题、URL、日期和摘要，不跟进详情页。
    """
    profile = OfficialSourceProfile(
        source_key="openai_news",
        name="OpenAI News",
        mode="html",
        entry_url="https://openai.com/news/",
    )
    entry = collect_from_news_html(load_text("official_news_page.html"), profile=profile, limit=1)[0]
    signal = official_news_entry_to_signal(entry)

    assert entry.entry_id == "https://openai.com/news/new-agent-platform?utm_source=homepage"
    assert entry.title == "OpenAI introduces a new agent platform"
    assert entry.url == "https://openai.com/news/new-agent-platform?utm_source=homepage"
    assert entry.published_at == datetime(2026, 6, 23, 12, 0, tzinfo=UTC)
    assert entry.summary == "OpenAI announced a platform update for deploying AI agents across enterprise workflows."
    assert signal.original_title == "OpenAI introduces a new agent platform"
    assert signal.canonical_url == "https://openai.com/news/new-agent-platform"
    assert signal.metadata["source"] == "official_news"
    assert signal.metadata["profile_name"] == "OpenAI News"

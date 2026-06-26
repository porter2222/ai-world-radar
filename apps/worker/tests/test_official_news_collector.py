from datetime import UTC, datetime
from pathlib import Path

import httpx

from worker.collectors import official_news as official_news_module
from worker.collectors.official_news import (
    OfficialSourceProfile,
    collect_from_feed_xml,
    collect_from_news_html,
    fetch_official_news,
)
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


def test_fetch_official_news_falls_back_to_urllib_after_httpx_403(monkeypatch):
    """验证 PyTorch RSS 在 httpx 403 后可通过标准库 fallback 继续采集。
    输入：httpx 主请求返回 403，urllib fallback 返回真实 RSS 形态 XML。
    输出：fetch_official_news 返回条目，并在 entry.fetch_metadata 中记录 fallback 发生过。
    """
    profile = OfficialSourceProfile(
        source_key="pytorch_blog",
        name="PyTorch Blog",
        mode="rss",
        entry_url="https://pytorch.org/blog/feed.xml",
    )

    class FakeHttpxClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def get(self, url):
            return httpx.Response(
                403,
                text="Forbidden",
                request=httpx.Request("GET", url),
            )

    class FakeUrllibResponse:
        status = 200
        headers = {"content-type": "application/rss+xml; charset=UTF-8"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def read(self):
            return b"""
            <rss><channel><item>
              <title>PyTorch fallback item</title>
              <link>https://pytorch.org/blog/fallback-item/</link>
              <guid>pytorch-fallback-item</guid>
              <pubDate>Fri, 26 Jun 2026 05:00:00 GMT</pubDate>
              <description>Fallback summary.</description>
            </item></channel></rss>
            """

    def fake_urlopen(request, timeout):
        assert request.full_url == profile.entry_url
        assert request.headers["User-agent"] == "ai-world-radar-worker"
        assert timeout == 20.0
        return FakeUrllibResponse()

    monkeypatch.setattr(official_news_module.httpx, "Client", FakeHttpxClient)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    entries = fetch_official_news(profile, limit=1)
    signal = official_news_entry_to_signal(entries[0])

    assert len(entries) == 1
    assert entries[0].title == "PyTorch fallback item"
    assert entries[0].fetch_metadata["fallback_used"] is True
    assert entries[0].fetch_metadata["fetch_client"] == "urllib"
    assert "403" in entries[0].fetch_metadata["fallback_reason"]
    assert signal.metadata["fetch_metadata"]["fallback_used"] is True


def test_rss_feed_entry_extracts_media_image_to_signal_metadata():
    """验证 RSS item 的媒体图片会进入来源信号 metadata。
    输入：带 media:thumbnail 的 RSS item。
    输出：OfficialNewsEntry.image_url 与 SourceSignalCreate.metadata["image_url"] 保持同一个可信图片 URL。
    """
    profile = OfficialSourceProfile(
        source_key="nvidia_news",
        name="NVIDIA News",
        mode="rss",
        entry_url="https://nvidianews.nvidia.com/rss.xml",
    )
    entry = collect_from_feed_xml(
        """
        <rss xmlns:media="http://search.yahoo.com/mrss/">
          <channel>
            <item>
              <title>NVIDIA image item</title>
              <link>https://nvidianews.nvidia.com/news/image-item</link>
              <guid>nvidia-image-item</guid>
              <media:thumbnail url="https://nvidianews.nvidia.com/image/news-cover.jpg" />
            </item>
          </channel>
        </rss>
        """,
        profile=profile,
        limit=1,
    )[0]
    signal = official_news_entry_to_signal(entry)

    assert entry.image_url == "https://nvidianews.nvidia.com/image/news-cover.jpg"
    assert signal.metadata["image_url"] == "https://nvidianews.nvidia.com/image/news-cover.jpg"
    assert signal.metadata["image_source"] == "official_feed"


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


def test_html_news_page_entry_extracts_article_image():
    """验证 HTML 列表页 article 图片会规范化为绝对地址。
    输入：带相对路径 img 的官方新闻列表 article。
    输出：OfficialNewsEntry.image_url 使用 profile.entry_url 补全为绝对 URL。
    """
    profile = OfficialSourceProfile(
        source_key="openai_news",
        name="OpenAI News",
        mode="html",
        entry_url="https://openai.com/news/",
    )
    entry = collect_from_news_html(
        """
        <article>
          <a href="/news/image-item"><h2>OpenAI image item</h2></a>
          <img src="/news/image-item/cover.png" alt="cover" />
          <time datetime="2026-06-23T12:00:00Z">Jun 23, 2026</time>
          <p>OpenAI image summary.</p>
        </article>
        """,
        profile=profile,
        limit=1,
    )[0]

    assert entry.image_url == "https://openai.com/news/image-item/cover.png"


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


def test_official_news_signal_uses_short_source_item_id_for_long_entry_id():
    """验证超长官方源 entry id 不会突破 SourceSignal 的 source_item_id 长度限制。
    输入：一个以长 URL 作为 entry_id 的官方源条目。
    输出：source_item_id 使用稳定短 id，metadata 仍保留完整 entry_id 便于追溯。
    """
    profile = OfficialSourceProfile(
        source_key="nvidia_news",
        name="NVIDIA News",
        mode="rss",
        entry_url="https://nvidianews.nvidia.com/rss.xml",
    )
    long_entry_id = (
        "https://nvidianews.nvidia.com/news/"
        "nvidia-ai-platform-announcement-with-a-very-long-title-and-many-path-segments-"
        "for-real-rss-feeds-that-exceed-the-source-item-id-limit"
    )
    entry = collect_from_feed_xml(
        f"""
        <rss><channel><item>
          <title>NVIDIA long URL item</title>
          <link>{long_entry_id}</link>
          <guid>{long_entry_id}</guid>
        </item></channel></rss>
        """,
        profile=profile,
        limit=1,
    )[0]

    signal = official_news_entry_to_signal(entry)

    assert len(signal.source_item_id or "") <= 128
    assert signal.source_item_id.startswith("official:nvidia_news:")
    assert signal.metadata["entry_id"] == long_entry_id


def test_html_news_page_ignores_month_only_datetime():
    """验证月份级日期不会导致官方 HTML 源采集失败。
    输入：time datetime 为 `May 2026` 的轻量 HTML 新闻卡片。
    输出：条目仍被解析，published_at 置空，后续采集流程可继续写入信号。
    """
    profile = OfficialSourceProfile(
        source_key="anthropic_news",
        name="Anthropic News",
        mode="html",
        entry_url="https://www.anthropic.com/news",
    )
    html = """
    <article>
      <a href="/news/example-update"><h2>Anthropic example update</h2></a>
      <time datetime="May 2026">May 2026</time>
      <p>Example summary.</p>
    </article>
    """

    entry = collect_from_news_html(html, profile=profile, limit=1)[0]

    assert entry.title == "Anthropic example update"
    assert entry.published_at is None

from pathlib import Path

from worker.services.cover_image_service import (
    DEFAULT_COVER_IMAGE_URL,
    SOURCE_LOGO_IMAGE_URLS,
    build_github_opengraph_image_url,
    resolve_cover_image_url,
)


def test_resolve_cover_image_prefers_source_image_from_signal_metadata():
    """验证真实来源图优先。
    输入：metadata 中带 image_url 的来源信号。
    输出：直接返回来源图片 URL，不再使用平台 logo 或全局默认图。
    """
    signals = [
        {
            "source_key": "openai_news",
            "metadata": {"image_url": "https://openai.com/news/cover.jpg"},
        }
    ]

    assert resolve_cover_image_url(signals) == "https://openai.com/news/cover.jpg"


def test_resolve_cover_image_uses_github_opengraph_before_logo_fallback():
    """验证 GitHub 类事件优先使用 OpenGraph 图片。
    输入：GitHub repo trends 信号 metadata 中的 owner/repo。
    输出：返回 GitHub OpenGraph URL，而不是 GitHub logo 兜底图。
    """
    signals = [
        {
            "source_key": "github_repo_trends",
            "metadata": {"owner": "Example", "repo": "Fast-LLM"},
        }
    ]

    assert resolve_cover_image_url(signals) == "https://opengraph.githubassets.com/ai-world-radar/example/fast-llm"


def test_resolve_cover_image_uses_source_logo_then_default_cover():
    """验证品牌 logo 与全局默认图兜底。
    输入：一条可识别来源但无图片的 HN 信号，以及一条未知来源信号。
    输出：已知来源返回品牌 logo，未知来源返回 AI World Radar 默认封面。
    """
    assert resolve_cover_image_url([{"source_key": "hn_algolia", "metadata": {}}]) == (
        "/images/source-logos/hacker-news.svg"
    )
    assert resolve_cover_image_url([{"source_key": "unknown_source", "metadata": {}}]) == DEFAULT_COVER_IMAGE_URL


def test_build_github_opengraph_image_url_normalizes_owner_repo():
    """验证 GitHub OpenGraph URL 规范化。
    输入：大小写混合、前后带空格的 owner/repo。
    输出：固定 cache key 和小写 owner/repo 组成的稳定 URL。
    """
    assert build_github_opengraph_image_url(" OpenAI ", " OpenAI-Python ") == (
        "https://opengraph.githubassets.com/ai-world-radar/openai/openai-python"
    )


def test_source_logo_paths_have_local_public_assets():
    """验证本地 logo 兜底路径都能被前端 public 目录实际提供。
    输入：cover image service 中声明的品牌 logo URL。
    输出：每个 `/images/...` 路径都能映射到 apps/web/public 下的真实 SVG 文件。
    """
    public_dir = Path(__file__).resolve().parents[3] / "apps" / "web" / "public"
    urls = set(SOURCE_LOGO_IMAGE_URLS.values()) | {DEFAULT_COVER_IMAGE_URL}

    for url in sorted(urls):
        assert url.startswith("/images/")
        assert (public_dir / url.lstrip("/")).is_file(), f"Missing public asset for {url}"

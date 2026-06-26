from __future__ import annotations

from typing import Any


GITHUB_OPENGRAPH_CACHE_KEY = "ai-world-radar"
GITHUB_OPENGRAPH_BASE_URL = "https://opengraph.githubassets.com"
DEFAULT_COVER_IMAGE_URL = "/images/source-logos/ai-world-radar.svg"


SOURCE_LOGO_IMAGE_URLS = {
    "hn": "/images/source-logos/hacker-news.svg",
    "hn_algolia": "/images/source-logos/hacker-news.svg",
    "github": "/images/source-logos/github.svg",
    "github_releases": "/images/source-logos/github.svg",
    "github_repo_trends": "/images/source-logos/github.svg",
    "github_changelog": "/images/source-logos/github.svg",
    "openai_news": "/images/source-logos/openai.svg",
    "anthropic_news": "/images/source-logos/anthropic.svg",
    "nvidia_news": "/images/source-logos/nvidia.svg",
    "deepmind_blog": "/images/source-logos/deepmind.svg",
    "huggingface_blog": "/images/source-logos/huggingface.svg",
    "google_ai_blog": "/images/source-logos/google-ai.svg",
    "aws_machine_learning_blog": "/images/source-logos/aws.svg",
    "pytorch_blog": "/images/source-logos/pytorch.svg",
    "ollama_blog": "/images/source-logos/ollama.svg",
}


def resolve_cover_image_url(signals: list[dict[str, Any]]) -> str:
    """为事件选择可展示的封面图 URL。

    输入：pipeline 传给 Agent 的来源信号 dict 列表，优先读取 metadata.image_url。
    输出：可直接写入 EventDossier.cover_image_url 的 URL；总会返回源图、GitHub OG、品牌 logo 或全局默认图之一。
    """
    source_image_url = _first_source_image_url(signals)
    if source_image_url:
        return source_image_url

    github_image_url = _first_github_opengraph_image_url(signals)
    if github_image_url:
        return github_image_url

    source_logo_url = _first_source_logo_url(signals)
    if source_logo_url:
        return source_logo_url

    return DEFAULT_COVER_IMAGE_URL


def build_github_opengraph_image_url(owner: str | None, repo: str | None) -> str | None:
    """生成 GitHub 仓库 OpenGraph 图片 URL。

    输入：GitHub owner 与 repo 名称，可包含大小写和前后空格。
    输出：稳定的 GitHub OpenGraph 图片 URL；owner 或 repo 为空时返回 None。
    """
    normalized_owner = _normalize_github_part(owner)
    normalized_repo = _normalize_github_part(repo)
    if not normalized_owner or not normalized_repo:
        return None
    return f"{GITHUB_OPENGRAPH_BASE_URL}/{GITHUB_OPENGRAPH_CACHE_KEY}/{normalized_owner}/{normalized_repo}"


def _first_source_image_url(signals: list[dict[str, Any]]) -> str | None:
    """读取第一张来源真实图片。

    输入：来源信号列表。
    输出：第一个可信 http(s) 图片 URL；没有则返回 None。
    """
    for signal in signals:
        metadata = _metadata(signal)
        image_url = metadata.get("image_url") or metadata.get("cover_image_url")
        if _is_external_image_url(image_url):
            return str(image_url).strip()
    return None


def _first_github_opengraph_image_url(signals: list[dict[str, Any]]) -> str | None:
    """读取第一张可由 GitHub owner/repo 生成的 OpenGraph 图片。

    输入：来源信号列表。
    输出：GitHub OpenGraph 图片 URL；无法识别 GitHub 仓库时返回 None。
    """
    for signal in signals:
        metadata = _metadata(signal)
        owner = metadata.get("owner")
        repo = metadata.get("repo")
        if not owner or not repo:
            full_name = metadata.get("full_name") or signal.get("source_item_id")
            owner, repo = _split_github_full_name(full_name)
        image_url = build_github_opengraph_image_url(str(owner) if owner else None, str(repo) if repo else None)
        if image_url:
            return image_url
    return None


def _first_source_logo_url(signals: list[dict[str, Any]]) -> str | None:
    """按来源 key 选择第一张品牌 logo 兜底图。

    输入：来源信号列表。
    输出：本地 public logo 路径；没有匹配来源时返回 None。
    """
    for signal in signals:
        source_key = str(signal.get("source_key") or "").strip()
        if source_key in SOURCE_LOGO_IMAGE_URLS:
            return SOURCE_LOGO_IMAGE_URLS[source_key]
    return None


def _metadata(signal: dict[str, Any]) -> dict[str, Any]:
    """安全读取 signal metadata。

    输入：来源信号 dict。
    输出：metadata dict；原值缺失或不是 dict 时返回空 dict。
    """
    metadata = signal.get("metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def _split_github_full_name(value: Any) -> tuple[str | None, str | None]:
    """拆分 GitHub full_name。

    输入：可能形如 owner/repo 或 owner/repo#release 的值。
    输出：owner 与 repo；无法拆分时返回 (None, None)。
    """
    if not isinstance(value, str):
        return None, None
    repo_part = value.split("#", maxsplit=1)[0].strip()
    parts = repo_part.split("/", maxsplit=1)
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


def _normalize_github_part(value: str | None) -> str | None:
    """规范化 GitHub owner 或 repo 片段。

    输入：owner 或 repo 字符串。
    输出：去掉首尾空格并转小写的片段；空值返回 None。
    """
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _is_external_image_url(value: Any) -> bool:
    """判断来源图片 URL 是否可作为外部封面图。

    输入：任意 metadata 值。
    输出：仅 http(s) URL 返回 True，避免 data URL 或空字符串进入前台展示。
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return stripped.startswith("https://") or stripped.startswith("http://")

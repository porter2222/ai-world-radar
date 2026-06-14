from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


GITHUB_API_ENDPOINT = "https://api.github.com"


@dataclass(frozen=True)
class GitHubRelease:
    """GitHub release 的规范化结构。

    输入：GitHub REST API release JSON 解析后的基础字段。
    输出：供 GitHub source adapter 映射 SourceSignalCreate 的稳定数据对象。
    """

    release_id: str
    owner: str
    repo: str
    tag_name: str
    name: str
    html_url: str
    published_at: datetime | None
    body: str | None
    assets_count: int
    is_prerelease: bool
    is_draft: bool


def parse_github_release(payload: dict[str, Any], owner: str, repo: str) -> GitHubRelease:
    """把 GitHub release JSON 转成 GitHubRelease。

    输入：单条 GitHub release JSON，以及 owner/repo。
    输出：包含 release id、tag、URL、发布时间、正文和状态标记的 GitHubRelease。
    """
    return GitHubRelease(
        release_id=str(payload["id"]),
        owner=owner,
        repo=repo,
        tag_name=str(payload.get("tag_name") or ""),
        name=str(payload.get("name") or ""),
        html_url=str(payload.get("html_url") or ""),
        published_at=_parse_datetime(payload.get("published_at")),
        body=payload.get("body"),
        assets_count=len(payload.get("assets") or []),
        is_prerelease=bool(payload.get("prerelease")),
        is_draft=bool(payload.get("draft")),
    )


def collect_from_github_releases_payload(
    payload: list[dict[str, Any]],
    owner: str,
    repo: str,
    limit: int,
) -> list[GitHubRelease]:
    """从 GitHub releases 响应中提取并排序 release。

    输入：GitHub REST API releases JSON 列表、owner/repo 和最大保留数量。
    输出：按 published_at 倒序排列的 GitHubRelease 列表。
    """
    releases = [parse_github_release(item, owner=owner, repo=repo) for item in payload]
    return sorted(releases, key=_sort_datetime, reverse=True)[:limit]


def fetch_github_releases(owner: str, repo: str, limit: int = 10, token: str | None = None) -> list[GitHubRelease]:
    """请求 GitHub REST API 并返回 release 列表。

    输入：owner、repo、最大数量和可选 GitHub token。
    输出：按发布时间倒序排列的 GitHubRelease 列表。
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-world-radar-worker",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        response = client.get(
            f"{GITHUB_API_ENDPOINT}/repos/{owner}/{repo}/releases",
            params={"per_page": limit},
        )
        response.raise_for_status()
        payload = response.json()

    return collect_from_github_releases_payload(payload, owner=owner, repo=repo, limit=limit)


def _parse_datetime(value: str | None) -> datetime | None:
    """解析 GitHub 返回的 ISO 时间。

    输入：可能带 `Z` 的时间字符串。
    输出：timezone-aware datetime；空值返回 None。
    """
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _sort_datetime(release: GitHubRelease) -> datetime:
    """返回 release 排序时间。

    输入：GitHubRelease。
    输出：published_at；为空时使用最小时间，保证未知时间排在后面。
    """
    return release.published_at or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)

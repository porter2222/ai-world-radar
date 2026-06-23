from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


GITHUB_REPOSITORY_SEARCH_ENDPOINT = "https://api.github.com/search/repositories"


@dataclass(frozen=True)
class GitHubRepositoryTrend:
    """GitHub 仓库趋势的规范化结构。

    输入：GitHub Search API repository item 解析后的基础字段。
    输出：供 source adapter 映射 SourceSignalCreate 的稳定数据对象。
    """

    repo_id: str
    owner: str
    repo: str
    full_name: str
    html_url: str
    description: str | None
    stargazers_count: int
    forks_count: int
    open_issues_count: int
    language: str | None
    topics: list[str]
    is_archived: bool
    is_fork: bool
    pushed_at: datetime | None
    updated_at: datetime | None
    created_at: datetime | None
    query: str


def parse_github_repository(payload: dict[str, Any], query: str) -> GitHubRepositoryTrend:
    """把 GitHub repository JSON 转成 GitHubRepositoryTrend。

    输入：单条 GitHub Search API repository JSON，以及命中的搜索 query。
    输出：包含仓库身份、热度指标、状态、topics 和时间字段的趋势对象。
    """
    full_name = str(payload.get("full_name") or "")
    owner, repo_name = _split_full_name(full_name)
    owner = str((payload.get("owner") or {}).get("login") or owner)
    repo_name = str(payload.get("name") or repo_name)

    return GitHubRepositoryTrend(
        repo_id=str(payload["id"]),
        owner=owner,
        repo=repo_name,
        full_name=full_name or f"{owner}/{repo_name}",
        html_url=str(payload.get("html_url") or ""),
        description=payload.get("description"),
        stargazers_count=int(payload.get("stargazers_count") or 0),
        forks_count=int(payload.get("forks_count") or 0),
        open_issues_count=int(payload.get("open_issues_count") or 0),
        language=payload.get("language"),
        topics=[str(topic) for topic in (payload.get("topics") or [])],
        is_archived=bool(payload.get("archived")),
        is_fork=bool(payload.get("fork")),
        pushed_at=_parse_datetime(payload.get("pushed_at")),
        updated_at=_parse_datetime(payload.get("updated_at")),
        created_at=_parse_datetime(payload.get("created_at")),
        query=query,
    )


def collect_from_github_search_payload(
    payload: dict[str, Any],
    query: str,
    limit: int,
    min_stars: int,
) -> list[GitHubRepositoryTrend]:
    """从 GitHub repository search 响应中提取趋势仓库。

    输入：完整搜索响应、命中 query、最大保留数量和最低 star 阈值。
    输出：过滤低 star 仓库后，按 GitHub 响应顺序截断的趋势对象列表。
    """
    repositories = [
        parse_github_repository(item, query=query)
        for item in payload.get("items", [])
        if int(item.get("stargazers_count") or 0) >= min_stars
    ]
    return repositories[:limit]


def fetch_github_repository_trends(
    query: str,
    limit: int = 10,
    min_stars: int = 100,
    token: str | None = None,
) -> list[GitHubRepositoryTrend]:
    """请求 GitHub Search API 并返回趋势仓库列表。

    输入：搜索 query、最大数量、最低 star 阈值和可选 GitHub token。
    输出：满足阈值的 GitHubRepositoryTrend 列表；网络或 API 错误会由 httpx 抛出。
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
            GITHUB_REPOSITORY_SEARCH_ENDPOINT,
            params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
        )
        response.raise_for_status()
        payload = response.json()

    return collect_from_github_search_payload(payload, query=query, limit=limit, min_stars=min_stars)


def _split_full_name(full_name: str) -> tuple[str, str]:
    """拆分 GitHub full_name。

    输入：形如 owner/repo 的 GitHub 仓库全名。
    输出：owner 与 repo；格式不完整时用空字符串兜底。
    """
    parts = full_name.split("/", maxsplit=1)
    if len(parts) != 2:
        return "", full_name
    return parts[0], parts[1]


def _parse_datetime(value: str | None) -> datetime | None:
    """解析 GitHub 返回的 ISO 时间。

    输入：可能带 `Z` 的时间字符串。
    输出：timezone-aware datetime；空值返回 None。
    """
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

from __future__ import annotations

from datetime import UTC, datetime

from worker.collectors.github_repo_trends import GITHUB_REPOSITORY_SEARCH_ENDPOINT, GitHubRepositoryTrend
from worker.collectors.hn_algolia import normalize_url
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.cover_image_service import build_github_opengraph_image_url


def build_github_repo_trends_source() -> SourceCreate:
    """构造 GitHub repo trends 来源配置。

    输入：无。
    输出：可交给 SignalService.upsert_source 的 SourceCreate。
    """
    return SourceCreate(
        source_key="github_repo_trends",
        name="GitHub Repo Trends",
        source_type="code_hosting",
        fetch_method="api",
        entry_url=GITHUB_REPOSITORY_SEARCH_ENDPOINT,
        fetch_config={"endpoint": GITHUB_REPOSITORY_SEARCH_ENDPOINT, "mode": "repository_search"},
    )


def github_repo_trend_to_signal(
    repo: GitHubRepositoryTrend,
    *,
    snapshot_bucket: str,
    previous_stargazers_count: int | None = None,
    detected_at: datetime | None = None,
) -> SourceSignalCreate:
    """把 GitHubRepositoryTrend 映射成新版来源信号。

    输入：规范化仓库趋势对象、当前快照 bucket、可选上一轮 star 数和本轮探测时间。
    输出：可交给 SignalService.upsert_signal 的 SourceSignalCreate。
    """
    stars_delta = _calculate_stars_delta(repo.stargazers_count, previous_stargazers_count)
    stars_delta_rate = _calculate_stars_delta_rate(stars_delta, previous_stargazers_count)
    trend_detected_at = detected_at or datetime.now(UTC)
    image_url = build_github_opengraph_image_url(repo.owner, repo.repo)

    return SourceSignalCreate(
        source_key="github_repo_trends",
        source_item_id=repo.full_name,
        original_title=f"{repo.full_name} is gaining attention on GitHub",
        original_url=repo.html_url,
        canonical_url=normalize_url(repo.html_url),
        published_at=trend_detected_at,
        language="en",
        raw_summary=_build_raw_summary(repo),
        source_hash=f"github_repo_trends:{repo.full_name}:{snapshot_bucket}",
        heat_metrics={
            "stargazers_count": repo.stargazers_count,
            "forks_count": repo.forks_count,
            "open_issues_count": repo.open_issues_count,
            "stars_delta_since_last": stars_delta,
            "previous_stargazers_count": previous_stargazers_count,
            "stars_delta_rate": stars_delta_rate,
            "is_archived": repo.is_archived,
            "is_fork": repo.is_fork,
        },
        metadata={
            "source": "github_repo_trends",
            "repo_id": repo.repo_id,
            "full_name": repo.full_name,
            "owner": repo.owner,
            "repo": repo.repo,
            "image_url": image_url,
            "image_source": "github_opengraph",
            "language": repo.language,
            "topics": repo.topics,
            "query": repo.query,
            "snapshot_bucket": snapshot_bucket,
            "detected_at": trend_detected_at.isoformat(),
            "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
            "created_at": repo.created_at.isoformat() if repo.created_at else None,
            "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
        },
    )


def _build_raw_summary(repo: GitHubRepositoryTrend) -> str:
    """生成 GitHub repo trend 的原始摘要。

    输入：GitHubRepositoryTrend 中的描述、星数、fork 数、语言和 topics。
    输出：供后续候选事件生成使用的短文本摘要。
    """
    description = repo.description or "No repository description."
    topics = ", ".join(repo.topics) if repo.topics else "none"
    language = repo.language or "unknown"
    return (
        f"{description} GitHub repo with {repo.stargazers_count} stars, "
        f"{repo.forks_count} forks, language {language}, topics: {topics}."
    )


def _calculate_stars_delta(current_stars: int, previous_stargazers_count: int | None) -> int | None:
    """计算本次快照相对上一轮的 star 增量。

    输入：当前 star 数和可选上一轮 star 数。
    输出：没有历史时返回 None；有历史时返回当前值减上一轮值。
    """
    if previous_stargazers_count is None:
        return None
    return current_stars - previous_stargazers_count


def _calculate_stars_delta_rate(
    stars_delta: int | None,
    previous_stargazers_count: int | None,
) -> float | None:
    """计算 star 增长率。

    输入：已计算的 star 增量和上一轮 star 数。
    输出：没有历史或上一轮为 0 时返回 None；否则返回四位小数以内的增长率。
    """
    if stars_delta is None or not previous_stargazers_count:
        return None
    return round(stars_delta / previous_stargazers_count, 4)

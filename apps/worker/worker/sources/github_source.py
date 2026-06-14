from __future__ import annotations

from worker.collectors.github_releases import GITHUB_API_ENDPOINT, GitHubRelease
from worker.collectors.hn_algolia import normalize_url
from worker.schemas.source import SourceCreate, SourceSignalCreate


def build_github_releases_source() -> SourceCreate:
    """构造 GitHub releases 来源配置。

    输入：无。
    输出：可交给 SignalService.upsert_source 的 SourceCreate。
    """
    return SourceCreate(
        source_key="github_releases",
        name="GitHub Releases",
        source_type="code_hosting",
        fetch_method="api",
        entry_url=GITHUB_API_ENDPOINT,
        fetch_config={"endpoint": f"{GITHUB_API_ENDPOINT}/repos/{{owner}}/{{repo}}/releases"},
    )


def github_release_to_signal(release: GitHubRelease) -> SourceSignalCreate:
    """把 GitHubRelease 映射成新版来源信号。

    输入：GitHub releases collector 已规范化的 GitHubRelease。
    输出：可交给 SignalService.upsert_signal 的 SourceSignalCreate。
    """
    title_value = release.name or release.tag_name
    return SourceSignalCreate(
        source_key="github_releases",
        source_item_id=f"{release.owner}/{release.repo}#{release.release_id}",
        original_title=f"{release.owner}/{release.repo} released {title_value}",
        original_url=release.html_url,
        canonical_url=normalize_url(release.html_url),
        published_at=release.published_at,
        language="en",
        raw_summary=release.body or f"GitHub release {release.tag_name} has no body.",
        source_hash=f"github_releases:{release.owner}/{release.repo}:{release.release_id}",
        heat_metrics={
            "assets_count": release.assets_count,
            "is_prerelease": release.is_prerelease,
            "is_draft": release.is_draft,
        },
        metadata={
            "source": "github_releases",
            "owner": release.owner,
            "repo": release.repo,
            "tag_name": release.tag_name,
            "release_id": release.release_id,
        },
    )

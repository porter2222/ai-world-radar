from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from worker.collectors.github_releases import collect_from_github_releases_payload, fetch_github_releases
from worker.collectors.github_repo_trends import collect_from_github_search_payload, fetch_github_repository_trends
from worker.collectors.hn_algolia import collect_from_algolia_payload, fetch_hn_stories
from worker.collectors.official_news import (
    OfficialSourceProfile,
    collect_from_feed_xml,
    collect_from_news_html,
    fetch_official_news,
)
from worker.db.session import create_worker_engine
from worker.models import Base, Source, SourceSignal
from worker.services.signal_service import SignalService
from worker.sources.github_source import build_github_releases_source, github_release_to_signal
from worker.sources.github_trends_source import build_github_repo_trends_source, github_repo_trend_to_signal
from worker.sources.hn_source import build_hn_source, hn_story_to_signal
from worker.sources.official_news_source import build_official_news_source, official_news_entry_to_signal


OFFICIAL_SOURCE_PROFILES = {
    "nvidia_news": OfficialSourceProfile(
        source_key="nvidia_news",
        name="NVIDIA News",
        mode="rss",
        entry_url="https://nvidianews.nvidia.com/rss.xml",
    ),
    "github_changelog": OfficialSourceProfile(
        source_key="github_changelog",
        name="GitHub Changelog",
        mode="rss",
        entry_url="https://github.blog/changelog/feed/",
    ),
    "openai_news": OfficialSourceProfile(
        source_key="openai_news",
        name="OpenAI News",
        mode="rss",
        entry_url="https://openai.com/news/rss.xml",
    ),
    "anthropic_news": OfficialSourceProfile(
        source_key="anthropic_news",
        name="Anthropic News",
        mode="html",
        entry_url="https://www.anthropic.com/news",
    ),
    "deepmind_blog": OfficialSourceProfile(
        source_key="deepmind_blog",
        name="Google DeepMind Blog",
        mode="html",
        entry_url="https://deepmind.google/discover/blog/",
    ),
    "huggingface_blog": OfficialSourceProfile(
        source_key="huggingface_blog",
        name="Hugging Face Blog",
        mode="rss",
        entry_url="https://huggingface.co/blog/feed.xml",
    ),
    "google_ai_blog": OfficialSourceProfile(
        source_key="google_ai_blog",
        name="Google AI Blog",
        mode="rss",
        entry_url="https://blog.google/technology/ai/rss/",
    ),
    "aws_machine_learning_blog": OfficialSourceProfile(
        source_key="aws_machine_learning_blog",
        name="AWS Machine Learning Blog",
        mode="rss",
        entry_url="https://aws.amazon.com/blogs/machine-learning/feed/",
    ),
    "pytorch_blog": OfficialSourceProfile(
        source_key="pytorch_blog",
        name="PyTorch Blog",
        mode="rss",
        entry_url="https://pytorch.org/blog/feed.xml",
    ),
    "ollama_blog": OfficialSourceProfile(
        source_key="ollama_blog",
        name="Ollama Blog",
        mode="rss",
        entry_url="https://ollama.com/blog/rss.xml",
    ),
}

DAILY_ALL_SOURCE_GROUP_SOURCES = ("hn", "github", "github_trends", "official_feeds")
DEFAULT_DAILY_ALL_OFFICIAL_PROFILES = tuple(sorted(OFFICIAL_SOURCE_PROFILES))
DEFAULT_DAILY_ALL_GITHUB_RELEASE_REPOS = ("openai/openai-python",)
DEFAULT_DAILY_ALL_GITHUB_TREND_QUERIES = ("topic:llm stars:>100",)


def parse_args() -> argparse.Namespace:
    """解析来源采集脚本参数。

    输入：命令行参数。
    输出：包含数据库 URL、来源选择、source group 展开结果和 fixture 开关的 argparse Namespace。
    """
    parser = argparse.ArgumentParser(description="Collect external source signals into source_signals.")
    parser.add_argument("--database-url", default=None, help="覆盖默认 DATABASE_URL。")
    parser.add_argument("--create-schema-for-smoke", action="store_true", help="仅本地 smoke 使用：直接 create_all。")
    parser.add_argument("--fixture-mode", action="store_true", help="仅测试和本地 smoke 使用：读取本地 fixture，不访问外网。")
    parser.add_argument(
        "--source",
        action="append",
        choices=["hn", "github", "github_trends", "official_feeds"],
        default=[],
        help="要采集的来源。",
    )
    parser.add_argument("--source-group", action="append", choices=["daily_all"], default=[], help="预置来源组。")
    parser.add_argument("--hn-days", type=int, default=7, help="HN 搜索时间窗口天数。")
    parser.add_argument("--hn-limit", type=int, default=5, help="HN 最大写入信号数。")
    parser.add_argument("--github-repo", action="append", default=[], help="GitHub 仓库，格式 owner/repo。")
    parser.add_argument("--github-limit", type=int, default=3, help="每个 GitHub 仓库最大 release 数。")
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN", help="读取 GitHub token 的环境变量名。")
    parser.add_argument("--github-trend-query", action="append", default=[], help="GitHub repo trends 搜索 query，可重复传入。")
    parser.add_argument("--github-trend-limit", type=int, default=5, help="每个 GitHub repo trend query 最大写入仓库数。")
    parser.add_argument("--github-trend-min-stars", type=int, default=100, help="GitHub repo trend 最低 star 阈值。")
    parser.add_argument("--github-trend-token-env", default="GITHUB_TOKEN", help="读取 GitHub repo trend token 的环境变量名。")
    parser.add_argument("--snapshot-bucket", default=None, help="GitHub repo trend 快照 bucket；测试或 smoke 可传固定 YYYYMMDDHH。")
    parser.add_argument("--official-profile", action="append", default=[], help="官方源 profile key，可重复传入。")
    parser.add_argument("--official-limit", type=int, default=5, help="每个官方源最大写入条目数。")
    args = parser.parse_args()
    if not args.source and not args.source_group:
        parser.error("at least one --source or --source-group is required")
    expand_source_groups(args)
    return args


def expand_source_groups(args: argparse.Namespace) -> None:
    """把预置来源组展开到具体采集参数。

    输入：parse_args 生成的 argparse Namespace，可包含 `source_group`。
    输出：无返回值；原地补齐 source、官方 profile、GitHub release 仓库和 GitHub trend query。
    """
    if "daily_all" not in set(args.source_group):
        return

    args.source = append_missing(args.source, DAILY_ALL_SOURCE_GROUP_SOURCES)
    args.official_profile = append_missing(args.official_profile, DEFAULT_DAILY_ALL_OFFICIAL_PROFILES)
    args.github_repo = append_missing(args.github_repo, DEFAULT_DAILY_ALL_GITHUB_RELEASE_REPOS)
    args.github_trend_query = append_missing(args.github_trend_query, DEFAULT_DAILY_ALL_GITHUB_TREND_QUERIES)


def append_missing(current: list[str], defaults: tuple[str, ...]) -> list[str]:
    """按顺序追加缺失的默认值。

    输入：用户已传入的字符串列表，以及来源组默认值。
    输出：保留用户顺序并补齐默认值的新列表，不产生重复项。
    """
    values = list(current)
    seen = set(values)
    for value in defaults:
        if value not in seen:
            values.append(value)
            seen.add(value)
    return values


def main() -> int:
    """运行来源采集脚本。

    输入：命令行参数和可选临时数据库。
    输出：向 stdout 打印 JSON 摘要，并用进程退出码表达成功或失败。
    """
    args = parse_args()
    engine = create_worker_engine(args.database_url) if args.database_url else create_worker_engine()
    if args.create_schema_for_smoke:
        Base.metadata.create_all(engine)

    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        service = SignalService(session)
        source_keys = collect_selected_sources(session_service=service, args=args)
        session.commit()
        summary = build_summary(session, source_keys=source_keys)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        session.rollback()
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1
    finally:
        session.close()
        engine.dispose()


def collect_selected_sources(session_service: SignalService, args: argparse.Namespace) -> set[str]:
    """按参数采集并写入来源信号。

    输入：SignalService 和脚本参数。
    输出：本轮涉及的 source_key 集合。
    """
    source_keys: set[str] = set()
    selected_sources = set(args.source)

    if "hn" in selected_sources:
        collect_hn_signals(session_service, days=args.hn_days, limit=args.hn_limit, fixture_mode=args.fixture_mode)
        source_keys.add("hn_algolia")

    if "github" in selected_sources:
        collect_github_signals(
            session_service,
            repos=args.github_repo,
            limit=args.github_limit,
            token=os.getenv(args.github_token_env),
            fixture_mode=args.fixture_mode,
        )
        source_keys.add("github_releases")

    if "github_trends" in selected_sources:
        collect_github_repo_trend_signals(
            session_service,
            queries=args.github_trend_query,
            limit=args.github_trend_limit,
            min_stars=args.github_trend_min_stars,
            token=os.getenv(args.github_trend_token_env),
            fixture_mode=args.fixture_mode,
            snapshot_bucket=args.snapshot_bucket or build_snapshot_bucket(),
        )
        source_keys.add("github_repo_trends")

    if "official_feeds" in selected_sources:
        official_source_keys = collect_official_feed_signals(
            session_service,
            profile_keys=args.official_profile,
            limit=args.official_limit,
            fixture_mode=args.fixture_mode,
        )
        source_keys.update(official_source_keys)

    return source_keys


def collect_hn_signals(service: SignalService, *, days: int, limit: int, fixture_mode: bool) -> None:
    """采集 HN story 并写入 SourceSignal。

    输入：SignalService、时间窗口、数量限制和 fixture 开关。
    输出：无返回值；通过服务层 upsert `hn_algolia` source 和 signal。
    """
    service.upsert_source(build_hn_source())
    stories = load_fixture_hn_stories(limit=limit) if fixture_mode else fetch_hn_stories(days=days, limit=limit)
    for story in stories:
        service.upsert_signal(hn_story_to_signal(story))


def collect_github_signals(
    service: SignalService,
    *,
    repos: list[str],
    limit: int,
    token: str | None,
    fixture_mode: bool,
) -> None:
    """采集 GitHub releases 并写入 SourceSignal。

    输入：SignalService、仓库列表、数量限制、可选 token 和 fixture 开关。
    输出：无返回值；通过服务层 upsert `github_releases` source 和 signal。
    """
    if not repos:
        raise ValueError("--github-repo is required when --source github is used")

    service.upsert_source(build_github_releases_source())
    for repo in repos:
        owner, repo_name = parse_repo(repo)
        releases = (
            load_fixture_github_releases(owner=owner, repo=repo_name, limit=limit)
            if fixture_mode
            else fetch_github_releases(owner=owner, repo=repo_name, limit=limit, token=token)
        )
        for release in releases:
            service.upsert_signal(github_release_to_signal(release))


def collect_github_repo_trend_signals(
    service: SignalService,
    *,
    queries: list[str],
    limit: int,
    min_stars: int,
    token: str | None,
    fixture_mode: bool,
    snapshot_bucket: str,
) -> None:
    """采集 GitHub repo trends 并写入 SourceSignal。

    输入：SignalService、搜索 query 列表、数量限制、star 阈值、可选 token、fixture 开关和快照 bucket。
    输出：无返回值；通过服务层 upsert `github_repo_trends` source 和 signal。
    """
    if not queries:
        raise ValueError("--github-trend-query is required when --source github_trends is used")

    service.upsert_source(build_github_repo_trends_source())
    for query in queries:
        trends = (
            load_fixture_github_repo_trends(query=query, limit=limit, min_stars=min_stars)
            if fixture_mode
            else fetch_github_repository_trends(query=query, limit=limit, min_stars=min_stars, token=token)
        )
        for repo in trends:
            previous_stargazers_count = find_previous_stargazers_count(
                service,
                source_item_id=repo.full_name,
                snapshot_bucket=snapshot_bucket,
            )
            service.upsert_signal(
                github_repo_trend_to_signal(
                    repo,
                    snapshot_bucket=snapshot_bucket,
                    previous_stargazers_count=previous_stargazers_count,
                )
            )


def collect_official_feed_signals(
    service: SignalService,
    *,
    profile_keys: list[str],
    limit: int,
    fixture_mode: bool,
) -> set[str]:
    """采集官方 RSS/Atom/HTML 来源并写入 SourceSignal。

    输入：SignalService、官方 profile key 列表、每个 profile 的数量限制和 fixture 开关。
    输出：本轮实际写入或尝试写入的官方 source_key 集合。
    """
    if not profile_keys:
        raise ValueError("--official-profile is required when --source official_feeds is used")

    source_keys: set[str] = set()
    for profile_key in profile_keys:
        profile = get_official_source_profile(profile_key)
        service.upsert_source(build_official_news_source(profile))
        entries = load_fixture_official_news(profile=profile, limit=limit) if fixture_mode else fetch_official_news(profile, limit=limit)
        if not entries:
            raise ValueError(f"No official entries collected for profile={profile.source_key}")
        for entry in entries:
            service.upsert_signal(official_news_entry_to_signal(entry))
        source_keys.add(profile.source_key)
    return source_keys


def get_official_source_profile(profile_key: str) -> OfficialSourceProfile:
    """读取内置官方来源 profile。

    输入：命令行传入的 profile key。
    输出：OfficialSourceProfile；未知 key 时抛出 ValueError 并列出可选项。
    """
    profile = OFFICIAL_SOURCE_PROFILES.get(profile_key)
    if profile is None:
        available = ", ".join(sorted(OFFICIAL_SOURCE_PROFILES))
        raise ValueError(f"Unknown official profile: {profile_key}. Available profiles: {available}")
    return profile


def parse_repo(value: str) -> tuple[str, str]:
    """解析 owner/repo 格式。

    输入：命令行传入的 GitHub 仓库字符串。
    输出：owner 和 repo 二元组；格式错误时抛出 ValueError。
    """
    parts = value.split("/", maxsplit=1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid GitHub repo format: {value}")
    return parts[0], parts[1]


def build_snapshot_bucket(now: datetime | None = None) -> str:
    """生成 GitHub repo trend 默认快照 bucket。

    输入：可选当前时间；为空时使用 UTC 当前时间。
    输出：`YYYYMMDDHH` 格式的小时级 bucket 字符串。
    """
    current = now or datetime.now(UTC)
    return current.strftime("%Y%m%d%H")


def find_previous_stargazers_count(
    service: SignalService,
    *,
    source_item_id: str,
    snapshot_bucket: str,
) -> int | None:
    """查询同一仓库上一轮不同 bucket 的 star 快照。

    输入：SignalService、仓库 full_name 和当前 snapshot_bucket。
    输出：上一条不同 bucket signal 的 `stargazers_count`；没有历史时返回 None。
    """
    service.session.flush()
    source = service.session.scalar(select(Source).where(Source.source_key == "github_repo_trends"))
    if source is None:
        return None

    current_hash = f"github_repo_trends:{source_item_id}:{snapshot_bucket}"
    previous_signal = service.session.scalars(
        select(SourceSignal)
        .where(
            SourceSignal.source_id == source.id,
            SourceSignal.source_item_id == source_item_id,
            SourceSignal.source_hash != current_hash,
        )
        .order_by(SourceSignal.collected_at.desc(), SourceSignal.id.desc())
        .limit(1)
    ).first()
    if previous_signal is None:
        return None

    value = (previous_signal.heat_metrics or {}).get("stargazers_count")
    return int(value) if value is not None else None


def build_summary(session, *, source_keys: set[str]) -> dict[str, object]:
    """生成采集脚本 JSON 摘要。

    输入：数据库 Session 和本轮涉及的 source_key 集合。
    输出：包含状态、source 数、signal 数和 source_key 列表的字典。
    """
    sources_count = session.scalar(select(func.count(Source.id)).where(Source.source_key.in_(source_keys))) or 0
    signals_count = (
        session.scalar(
            select(func.count(SourceSignal.id))
            .join(Source, Source.id == SourceSignal.source_id)
            .where(Source.source_key.in_(source_keys))
        )
        or 0
    )
    return {
        "status": "succeeded",
        "sources_count": sources_count,
        "signals_count": signals_count,
        "source_keys": sorted(source_keys),
    }


def load_fixture_hn_stories(*, limit: int):
    """读取 HN fixture 并转换为 HNStory。

    输入：最大数量。
    输出：从测试 fixture 解析出的 HNStory 列表。
    """
    payload = json.loads(_fixture_path("hn_algolia_response.json").read_text(encoding="utf-8"))
    return collect_from_algolia_payload(payload, query="OpenAI", limit=limit)


def load_fixture_github_releases(*, owner: str, repo: str, limit: int):
    """读取 GitHub releases fixture 并转换为 GitHubRelease。

    输入：owner、repo 和最大数量。
    输出：从测试 fixture 解析出的 GitHubRelease 列表。
    """
    payload = json.loads(_fixture_path("github_releases_response.json").read_text(encoding="utf-8"))
    return collect_from_github_releases_payload(payload, owner=owner, repo=repo, limit=limit)


def load_fixture_github_repo_trends(*, query: str, limit: int, min_stars: int):
    """读取 GitHub repo search fixture 并转换为 GitHubRepositoryTrend。

    输入：搜索 query、最大数量和最低 star 阈值。
    输出：从测试 fixture 解析出的 GitHubRepositoryTrend 列表。
    """
    payload = json.loads(_fixture_path("github_repo_search_response.json").read_text(encoding="utf-8"))
    return collect_from_github_search_payload(payload, query=query, limit=limit, min_stars=min_stars)


def load_fixture_official_news(*, profile: OfficialSourceProfile, limit: int):
    """读取官方源 fixture 并转换为 OfficialNewsEntry。

    输入：官方来源 profile 和最大数量。
    输出：从测试 fixture 解析出的 OfficialNewsEntry 列表。
    """
    if profile.mode in {"rss", "atom"}:
        filename = "official_atom_feed.xml" if profile.mode == "atom" else "official_rss_feed.xml"
        return collect_from_feed_xml(_fixture_path(filename).read_text(encoding="utf-8"), profile=profile, limit=limit)
    return collect_from_news_html(_fixture_path("official_news_page.html").read_text(encoding="utf-8"), profile=profile, limit=limit)


def _fixture_path(filename: str) -> Path:
    """定位本地 smoke fixture 文件。

    输入：fixture 文件名。
    输出：apps/worker/tests/fixtures 下对应文件的 Path。
    """
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / filename


if __name__ == "__main__":
    raise SystemExit(main())

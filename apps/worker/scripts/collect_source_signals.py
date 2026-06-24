from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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


@dataclass
class CollectionWindow:
    """采集窗口。
    输入：窗口开始、结束和允许未来偏移。
    输出：供信号入库前判断是否写入。
    """

    start: datetime
    end: datetime
    allowed_future_skew: timedelta = timedelta(minutes=5)


@dataclass
class CollectionStats:
    """采集跳过统计。
    输入：无。
    输出：记录 stale、missing_published_at、future 三类跳过数量。
    """

    stale: int = 0
    missing_published_at: int = 0
    future: int = 0

    def as_dict(self) -> dict[str, int]:
        """转换为 stdout JSON 字段。
        输入：当前统计对象。
        输出：稳定 key 顺序的 dict。
        """
        return {
            "stale": self.stale,
            "missing_published_at": self.missing_published_at,
            "future": self.future,
        }


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
    parser.add_argument("--lookback-hours", type=int, default=8, help="采集层默认时效窗口小时数。")
    parser.add_argument("--now", default=None, help="测试专用：覆盖当前 UTC 时间，ISO 8601 格式。")
    parser.add_argument(
        "--continue-on-source-error",
        action="store_true",
        help="生产式采集：单个来源失败时记录失败并继续采集其他来源。",
    )
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
    args.source_failures = []
    current_time = parse_utc_datetime(args.now)
    args.collection_window = build_collection_window(now=current_time, lookback_hours=args.lookback_hours)
    args.collection_stats = CollectionStats()
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
        summary["window"] = {
            "lookback_hours": args.lookback_hours,
            "start": args.collection_window.start.isoformat(),
            "end": args.collection_window.end.isoformat(),
        }
        summary["skipped_signals"] = args.collection_stats.as_dict()
        if args.source_failures:
            summary["failed_sources_count"] = len(args.source_failures)
            summary["failed_sources"] = args.source_failures
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
    continue_on_source_error = bool(getattr(args, "continue_on_source_error", False))
    source_failures = getattr(args, "source_failures", None)
    window = getattr(args, "collection_window", build_collection_window(now=datetime.now(UTC), lookback_hours=8))
    stats = getattr(args, "collection_stats", CollectionStats())

    if "hn" in selected_sources:
        try:
            written_count = collect_hn_signals(
                session_service,
                hours=getattr(args, "lookback_hours", 8),
                limit=args.hn_limit,
                fixture_mode=args.fixture_mode,
                window=window,
                stats=stats,
            )
            mark_source_status(session_service, source_key="hn_algolia", status="succeeded")
            if written_count:
                source_keys.add("hn_algolia")
        except Exception as exc:
            handle_source_error(
                session_service,
                source_key="hn_algolia",
                exc=exc,
                continue_on_source_error=continue_on_source_error,
                source_failures=source_failures,
            )

    if "github" in selected_sources:
        try:
            written_count = collect_github_signals(
                session_service,
                repos=args.github_repo,
                limit=args.github_limit,
                token=os.getenv(args.github_token_env),
                fixture_mode=args.fixture_mode,
                window=window,
                stats=stats,
            )
            mark_source_status(session_service, source_key="github_releases", status="succeeded")
            if written_count:
                source_keys.add("github_releases")
        except Exception as exc:
            handle_source_error(
                session_service,
                source_key="github_releases",
                exc=exc,
                continue_on_source_error=continue_on_source_error,
                source_failures=source_failures,
            )

    if "github_trends" in selected_sources:
        try:
            written_count = collect_github_repo_trend_signals(
                session_service,
                queries=args.github_trend_query,
                limit=args.github_trend_limit,
                min_stars=args.github_trend_min_stars,
                token=os.getenv(args.github_trend_token_env),
                fixture_mode=args.fixture_mode,
                snapshot_bucket=args.snapshot_bucket or build_snapshot_bucket(now=window.end),
                detected_at=window.end,
            )
            mark_source_status(session_service, source_key="github_repo_trends", status="succeeded")
            if written_count:
                source_keys.add("github_repo_trends")
        except Exception as exc:
            handle_source_error(
                session_service,
                source_key="github_repo_trends",
                exc=exc,
                continue_on_source_error=continue_on_source_error,
                source_failures=source_failures,
            )

    if "official_feeds" in selected_sources:
        official_source_keys = collect_official_feed_signals(
            session_service,
            profile_keys=args.official_profile,
            limit=args.official_limit,
            fixture_mode=args.fixture_mode,
            continue_on_source_error=continue_on_source_error,
            source_failures=source_failures,
            window=window,
            stats=stats,
        )
        source_keys.update(official_source_keys)

    return source_keys


def parse_utc_datetime(value: str | None) -> datetime:
    """解析命令行传入的 UTC 时间。
    输入：ISO datetime 字符串；为空时使用当前 UTC。
    输出：timezone-aware UTC datetime。
    """
    if not value:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def build_collection_window(*, now: datetime, lookback_hours: int) -> CollectionWindow:
    """构造本轮采集窗口。
    输入：当前时间和窗口小时数。
    输出：CollectionWindow，start 为 now-lookback_hours，end 为 now。
    """
    return CollectionWindow(start=now - timedelta(hours=lookback_hours), end=now)


def normalize_datetime(value: datetime | None) -> datetime | None:
    """统一 datetime 时区。
    输入：可选 datetime。
    输出：timezone-aware UTC datetime；空值返回 None。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def should_write_signal(payload, *, window: CollectionWindow, stats: CollectionStats) -> bool:
    """判断信号是否应写入 source_signals。
    输入：SourceSignalCreate、采集窗口和统计对象。
    输出：可写入返回 True；否则递增对应跳过计数并返回 False。
    """
    published_at = normalize_datetime(payload.published_at)
    if published_at is None:
        stats.missing_published_at += 1
        return False
    if published_at < window.start:
        stats.stale += 1
        return False
    if published_at > window.end + window.allowed_future_skew:
        stats.future += 1
        return False
    return True


def upsert_signal_if_in_window(
    service: SignalService,
    payload,
    *,
    window: CollectionWindow,
    stats: CollectionStats,
) -> bool:
    """按采集窗口有条件写入信号。
    输入：SignalService、SourceSignalCreate、窗口和统计对象。
    输出：写入返回 True；被窗口过滤返回 False。
    """
    if not should_write_signal(payload, window=window, stats=stats):
        return False
    service.upsert_signal(payload)
    return True


def handle_source_error(
    service: SignalService,
    *,
    source_key: str,
    exc: Exception,
    continue_on_source_error: bool,
    source_failures: list[dict[str, str]] | None,
) -> None:
    """处理单个来源采集失败。
    输入：SignalService、来源 key、异常、是否继续和可选失败摘要列表。
    输出：严格模式重新抛错；继续模式记录 source 失败状态并把失败摘要交给调用方。
    """
    mark_source_status(service, source_key=source_key, status="failed", failure_reason=str(exc))
    if not continue_on_source_error:
        raise exc
    if source_failures is not None:
        source_failures.append({"source_key": source_key, "error": str(exc)})


def mark_source_status(
    service: SignalService,
    *,
    source_key: str,
    status: str,
    failure_reason: str | None = None,
) -> None:
    """更新来源最近一次采集状态。
    输入：SignalService、来源 key、状态和可选失败原因。
    输出：若来源已存在则更新 last_status/failure_reason；来源不存在时不创建占位来源。
    """
    source = service.session.scalar(select(Source).where(Source.source_key == source_key))
    if source is None:
        return
    source.last_status = status
    source.failure_reason = failure_reason
    service.session.flush()


def collect_hn_signals(
    service: SignalService,
    *,
    hours: int,
    limit: int,
    fixture_mode: bool,
    window: CollectionWindow,
    stats: CollectionStats,
) -> int:
    """采集 HN story 并按采集窗口写入 SourceSignal。

    输入：SignalService、小时窗口、数量限制、fixture 开关、采集窗口和统计对象。
    输出：实际写入或幂等命中的信号数量。
    """
    service.upsert_source(build_hn_source())
    stories = (
        load_fixture_hn_stories(limit=limit)
        if fixture_mode
        else fetch_hn_stories(hours=hours, limit=limit, queries=None, now=window.end)
    )
    written_count = 0
    for story in stories:
        if upsert_signal_if_in_window(service, hn_story_to_signal(story), window=window, stats=stats):
            written_count += 1
    return written_count


def collect_github_signals(
    service: SignalService,
    *,
    repos: list[str],
    limit: int,
    token: str | None,
    fixture_mode: bool,
    window: CollectionWindow,
    stats: CollectionStats,
) -> int:
    """采集 GitHub releases 并按采集窗口写入 SourceSignal。

    输入：SignalService、仓库列表、数量限制、可选 token、fixture 开关、采集窗口和统计对象。
    输出：实际写入或幂等命中的信号数量。
    """
    if not repos:
        raise ValueError("--github-repo is required when --source github is used")

    service.upsert_source(build_github_releases_source())
    written_count = 0
    for repo in repos:
        owner, repo_name = parse_repo(repo)
        releases = (
            load_fixture_github_releases(owner=owner, repo=repo_name, limit=limit)
            if fixture_mode
            else fetch_github_releases(owner=owner, repo=repo_name, limit=limit, token=token)
        )
        for release in releases:
            if upsert_signal_if_in_window(service, github_release_to_signal(release), window=window, stats=stats):
                written_count += 1
    return written_count


def collect_github_repo_trend_signals(
    service: SignalService,
    *,
    queries: list[str],
    limit: int,
    min_stars: int,
    token: str | None,
    fixture_mode: bool,
    snapshot_bucket: str,
    detected_at: datetime,
) -> int:
    """采集 GitHub repo trends 并写入 SourceSignal。

    输入：SignalService、搜索 query 列表、数量限制、star 阈值、可选 token、fixture 开关、快照 bucket 和探测时间。
    输出：实际写入或幂等命中的信号数量。
    """
    if not queries:
        raise ValueError("--github-trend-query is required when --source github_trends is used")

    service.upsert_source(build_github_repo_trends_source())
    written_count = 0
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
                    detected_at=detected_at,
                )
            )
            written_count += 1
    return written_count


def collect_official_feed_signals(
    service: SignalService,
    *,
    profile_keys: list[str],
    limit: int,
    fixture_mode: bool,
    continue_on_source_error: bool = False,
    source_failures: list[dict[str, str]] | None = None,
    window: CollectionWindow | None = None,
    stats: CollectionStats | None = None,
) -> set[str]:
    """采集官方 RSS/Atom/HTML 来源并按采集窗口写入 SourceSignal。

    输入：SignalService、官方 profile key 列表、每个 profile 的数量限制、fixture 开关、窗口和统计对象。
    输出：本轮实际写入官方信号的 source_key 集合。
    """
    if not profile_keys:
        raise ValueError("--official-profile is required when --source official_feeds is used")

    window = window or build_collection_window(now=datetime.now(UTC), lookback_hours=8)
    stats = stats or CollectionStats()
    source_keys: set[str] = set()
    for profile_key in profile_keys:
        profile = get_official_source_profile(profile_key)
        service.upsert_source(build_official_news_source(profile))
        try:
            entries = load_fixture_official_news(profile=profile, limit=limit) if fixture_mode else fetch_official_news(profile, limit=limit)
            if not entries:
                raise ValueError(f"No official entries collected for profile={profile.source_key}")
            written_count = 0
            for entry in entries:
                if upsert_signal_if_in_window(service, official_news_entry_to_signal(entry), window=window, stats=stats):
                    written_count += 1
            mark_source_status(service, source_key=profile.source_key, status="succeeded")
            if written_count:
                source_keys.add(profile.source_key)
        except Exception as exc:
            handle_source_error(
                service,
                source_key=profile.source_key,
                exc=exc,
                continue_on_source_error=continue_on_source_error,
                source_failures=source_failures,
            )
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

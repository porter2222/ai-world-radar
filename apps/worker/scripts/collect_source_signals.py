from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from worker.collectors.github_releases import collect_from_github_releases_payload, fetch_github_releases
from worker.collectors.hn_algolia import collect_from_algolia_payload, fetch_hn_stories
from worker.db.session import create_worker_engine
from worker.models import Base, Source, SourceSignal
from worker.services.signal_service import SignalService
from worker.sources.github_source import build_github_releases_source, github_release_to_signal
from worker.sources.hn_source import build_hn_source, hn_story_to_signal


def parse_args() -> argparse.Namespace:
    """解析来源采集脚本参数。

    输入：命令行参数。
    输出：包含数据库 URL、来源选择、HN/GitHub 限制和 fixture 开关的 argparse Namespace。
    """
    parser = argparse.ArgumentParser(description="Collect external source signals into source_signals.")
    parser.add_argument("--database-url", default=None, help="覆盖默认 DATABASE_URL。")
    parser.add_argument("--create-schema-for-smoke", action="store_true", help="仅本地 smoke 使用：直接 create_all。")
    parser.add_argument("--fixture-mode", action="store_true", help="仅测试和本地 smoke 使用：读取本地 fixture，不访问外网。")
    parser.add_argument("--source", action="append", choices=["hn", "github"], required=True, help="要采集的来源。")
    parser.add_argument("--hn-days", type=int, default=7, help="HN 搜索时间窗口天数。")
    parser.add_argument("--hn-limit", type=int, default=5, help="HN 最大写入信号数。")
    parser.add_argument("--github-repo", action="append", default=[], help="GitHub 仓库，格式 owner/repo。")
    parser.add_argument("--github-limit", type=int, default=3, help="每个 GitHub 仓库最大 release 数。")
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN", help="读取 GitHub token 的环境变量名。")
    return parser.parse_args()


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


def parse_repo(value: str) -> tuple[str, str]:
    """解析 owner/repo 格式。

    输入：命令行传入的 GitHub 仓库字符串。
    输出：owner 和 repo 二元组；格式错误时抛出 ValueError。
    """
    parts = value.split("/", maxsplit=1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid GitHub repo format: {value}")
    return parts[0], parts[1]


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


def _fixture_path(filename: str) -> Path:
    """定位本地 smoke fixture 文件。

    输入：fixture 文件名。
    输出：apps/worker/tests/fixtures 下对应文件的 Path。
    """
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / filename


if __name__ == "__main__":
    raise SystemExit(main())

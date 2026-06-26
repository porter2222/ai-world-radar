from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from worker.db.session import create_worker_engine
from worker.models import EventCandidate, EventCandidateSignal, PublishedEvent, Source, SourceSignal
from worker.services.editorial_candidate_service import extract_repo_full_name


TREND_SOURCE_KEY = "github_repo_trends"
HIDDEN_DUPLICATE_STATUS = "hidden_duplicate"


@dataclass(frozen=True)
class DuplicateGitHubTrendGroup:
    """同一 repo 在冷却窗口内的重复 GitHub trend 发布事件组。

    输入：repo 身份、保留事件和待隐藏事件列表。
    输出：供 dry-run 和 apply summary 使用的不可变结构。
    """

    repo_full_name: str
    kept_event: dict[str, Any]
    events_to_hide: list[dict[str, Any]]

    def to_summary(self) -> dict[str, Any]:
        """转换为可 JSON 序列化的摘要。

        输入：DuplicateGitHubTrendGroup。
        输出：包含 repo、保留事件和待隐藏事件的 dict。
        """
        return {
            "repo_full_name": self.repo_full_name,
            "kept_event": self.kept_event,
            "events_to_hide": self.events_to_hide,
        }


def find_duplicate_github_trend_events(
    session: Session,
    *,
    now: datetime | None = None,
    cooldown_days: int = 7,
) -> list[DuplicateGitHubTrendGroup]:
    """查找 7 天内同 repo 的重复纯 GitHub trend 发布事件。

    输入：Session、当前时间和冷却天数。
    输出：每个重复 repo 的保留事件和待隐藏事件；不修改数据库。
    """
    current_time = _normalize_datetime(now or datetime.now(UTC))
    cutoff = current_time - timedelta(days=cooldown_days)
    events_by_repo: dict[str, list[dict[str, Any]]] = {}

    for event in _load_recent_pure_trend_events(session, published_at_gte=cutoff):
        events_by_repo.setdefault(event["repo_full_name"], []).append(event)

    duplicate_groups = []
    for repo_full_name, events in events_by_repo.items():
        if len(events) <= 1:
            continue
        sorted_events = sorted(
            events,
            key=lambda item: (item["published_at"], item["published_event_id"]),
            reverse=True,
        )
        duplicate_groups.append(
            DuplicateGitHubTrendGroup(
                repo_full_name=repo_full_name,
                kept_event=_serialize_event(sorted_events[0]),
                events_to_hide=[_serialize_event(event) for event in sorted_events[1:]],
            )
        )

    return sorted(duplicate_groups, key=lambda group: group.repo_full_name)


def cleanup_duplicate_github_trend_events(
    session: Session,
    *,
    apply: bool = False,
    now: datetime | None = None,
    cooldown_days: int = 7,
) -> dict[str, Any]:
    """治理历史重复 GitHub trend 发布事件。

    输入：Session、是否 apply、当前时间和冷却天数。
    输出：可打印 JSON summary；dry-run 不修改数据库，apply 才写入 hidden_duplicate。
    """
    duplicate_groups = find_duplicate_github_trend_events(session, now=now, cooldown_days=cooldown_days)
    events_to_hide = [event for group in duplicate_groups for event in group.events_to_hide]
    hidden_count = 0

    if apply:
        for event in events_to_hide:
            published = session.get(PublishedEvent, event["published_event_id"])
            if published is None or published.status != "published":
                continue
            published.status = HIDDEN_DUPLICATE_STATUS
            hidden_count += 1
        session.flush()

    return {
        "mode": "apply" if apply else "dry_run",
        "cooldown_days": cooldown_days,
        "duplicate_groups_count": len(duplicate_groups),
        "events_to_hide_count": len(events_to_hide),
        "hidden_count": hidden_count,
        "duplicate_groups": [group.to_summary() for group in duplicate_groups],
        "events_to_hide": events_to_hide,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    """创建 cleanup CLI 参数解析器。

    输入：无。
    输出：支持 dry-run、apply、database-url 和 env-file 的 ArgumentParser。
    """
    parser = argparse.ArgumentParser(description="Dry-run or apply GitHub trend duplicate published event cleanup.")
    parser.add_argument("--apply", action="store_true", help="真正隐藏旧重复事件；默认不修改数据库。")
    parser.add_argument("--database-url", default=None, help="覆盖默认 DATABASE_URL，主要用于本地 smoke。")
    parser.add_argument("--env-file", default=None, help="测试或本地诊断时覆盖项目根 .env 路径。")
    parser.add_argument("--cooldown-days", type=int, default=7, help="同 repo trend 冷却天数，默认 7。")
    return parser


def main(argv: list[str] | None = None) -> int:
    """运行 cleanup CLI。

    输入：可选命令行参数。
    输出：stdout 打印 JSON summary；返回码 0 表示脚本执行成功。
    """
    args = build_arg_parser().parse_args(argv)
    if args.env_file:
        load_dotenv(Path(args.env_file).resolve(), override=True)

    engine = create_worker_engine(args.database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        summary = cleanup_duplicate_github_trend_events(
            session,
            apply=args.apply,
            cooldown_days=args.cooldown_days,
        )
        if args.apply:
            session.commit()
        else:
            session.rollback()
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        session.rollback()
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1
    finally:
        session.close()
        engine.dispose()


def _load_recent_pure_trend_events(session: Session, *, published_at_gte: datetime) -> list[dict[str, Any]]:
    """读取冷却窗口内的纯 GitHub trend 发布事件。

    输入：Session 和 published_at 下限。
    输出：每条可治理事件的 repo 身份和发布快照字段。
    """
    statement = (
        select(PublishedEvent, Source.source_key, SourceSignal)
        .join(EventCandidate, EventCandidate.id == PublishedEvent.candidate_id)
        .join(EventCandidateSignal, EventCandidateSignal.candidate_id == EventCandidate.id)
        .join(SourceSignal, SourceSignal.id == EventCandidateSignal.signal_id)
        .join(Source, Source.id == SourceSignal.source_id)
        .where(PublishedEvent.status == "published", PublishedEvent.published_at >= published_at_gte)
        .order_by(PublishedEvent.published_at.desc(), PublishedEvent.created_at.desc(), PublishedEvent.id.desc())
    )

    raw_events: dict[str, dict[str, Any]] = {}
    for published, source_key, signal in session.execute(statement).all():
        event = raw_events.setdefault(
            published.id,
            {
                "published_event_id": published.id,
                "slug": published.slug,
                "title": published.published_title,
                "published_at": _normalize_datetime(published.published_at),
                "source_keys": set(),
                "repo_full_names": set(),
            },
        )
        event["source_keys"].add(str(source_key or "").strip().lower())
        repo_full_name = _normalize_repo_full_name(extract_repo_full_name(signal))
        if repo_full_name:
            event["repo_full_names"].add(repo_full_name)

    pure_trend_events = []
    for event in raw_events.values():
        source_keys = event["source_keys"]
        repo_full_names = event["repo_full_names"]
        if source_keys != {TREND_SOURCE_KEY} or len(repo_full_names) != 1:
            continue
        pure_trend_events.append(
            {
                "published_event_id": event["published_event_id"],
                "slug": event["slug"],
                "title": event["title"],
                "published_at": event["published_at"],
                "repo_full_name": next(iter(repo_full_names)),
            }
        )
    return pure_trend_events


def _serialize_event(event: dict[str, Any]) -> dict[str, Any]:
    """把内部事件 dict 转为 JSON 友好 dict。

    输入：包含 datetime 的事件 dict。
    输出：published_at 已转 ISO 字符串的 dict。
    """
    return {
        "published_event_id": event["published_event_id"],
        "slug": event["slug"],
        "title": event["title"],
        "repo_full_name": event["repo_full_name"],
        "published_at": event["published_at"].isoformat(),
    }


def _normalize_repo_full_name(value: str | None) -> str | None:
    """规范化 GitHub repo 全名。

    输入：可能为空或大小写混用的 repo。
    输出：小写 `owner/repo`；无法识别返回 None。
    """
    if not value:
        return None
    normalized = value.strip().lower()
    if "/" not in normalized:
        return None
    owner, repo = normalized.split("/", maxsplit=1)
    if not owner or not repo:
        return None
    return f"{owner}/{repo}"


def _normalize_datetime(value: datetime) -> datetime:
    """统一 datetime 为 UTC aware。

    输入：可能是 naive 或 aware 的 datetime。
    输出：带 UTC 时区的 datetime。
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

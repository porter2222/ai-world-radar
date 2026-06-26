from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from worker.models import EventCandidate, EventCandidateSignal, PublishedEvent, Source, SourceSignal
from worker.services.editorial_candidate_service import EditorialCandidateGroup, extract_repo_full_name


GitHubTrendFreshnessAction = Literal["allow", "skip"]


@dataclass(frozen=True)
class GitHubTrendFreshnessDecision:
    """GitHub repo trend 新鲜度判定结果。

    输入：一个 selector 前候选 group 的来源身份和历史发布状态。
    输出：工程闸门的 allow / skip 决策及可写入 metadata 的解释字段。
    """

    action: GitHubTrendFreshnessAction
    reason: str
    repo_full_name: str | None
    matched_published_event_id: str | None
    cooldown_days: int


class GitHubTrendFreshnessService:
    """GitHub repo trend 跨轮次新鲜度闸门。

    输入：SQLAlchemy Session 和 selector 前的 EditorialCandidateGroup。
    输出：判断纯 GitHub trend group 是否应跳过，并可标记对应 SourceSignal。
    """

    TREND_SOURCE_KEY = "github_repo_trends"
    SKIPPED_STATUS = "skipped_duplicate_trend"
    HARD_FRESHNESS_SOURCE_KEYS = {
        "github_releases",
        "hn_algolia",
        "openai_news",
        "anthropic_news",
        "nvidia_news",
        "deepmind_blog",
        "google_ai_blog",
        "huggingface_blog",
        "pytorch_blog",
        "ollama_blog",
        "aws_machine_learning_blog",
    }

    def __init__(self, session: Session):
        """初始化服务。

        输入：调用方管理生命周期和事务的 SQLAlchemy Session。
        输出：可复用的新鲜度服务实例。
        """
        self.session = session

    def evaluate_group(
        self,
        group: EditorialCandidateGroup,
        *,
        now: datetime | None = None,
        cooldown_days: int = 7,
    ) -> GitHubTrendFreshnessDecision:
        """判断候选 group 是否命中 GitHub repo trend 冷却期。

        输入：selector 前候选 group、可选当前时间和冷却天数。
        输出：allow / skip 决策；只有纯 github_repo_trends 且近期已发布同 repo 纯 trend 时 skip。
        """
        current_time = _normalize_datetime(now or datetime.now(UTC))
        source_keys = {_normalize_source_key(source_key) for source_key in group.source_keys}
        repo_full_name = self._resolve_group_repo_full_name(group)

        if source_keys & self.HARD_FRESHNESS_SOURCE_KEYS:
            return GitHubTrendFreshnessDecision(
                action="allow",
                reason="has_hard_freshness_source",
                repo_full_name=repo_full_name,
                matched_published_event_id=None,
                cooldown_days=cooldown_days,
            )
        if source_keys != {self.TREND_SOURCE_KEY}:
            return GitHubTrendFreshnessDecision(
                action="allow",
                reason="not_pure_github_repo_trend",
                repo_full_name=repo_full_name,
                matched_published_event_id=None,
                cooldown_days=cooldown_days,
            )
        if repo_full_name is None:
            return GitHubTrendFreshnessDecision(
                action="allow",
                reason="missing_repo_identity",
                repo_full_name=None,
                matched_published_event_id=None,
                cooldown_days=cooldown_days,
            )

        cutoff = current_time - timedelta(days=cooldown_days)
        recent_event_id = self._find_matching_pure_trend_published_event_id(
            repo_full_name,
            published_at_gte=cutoff,
        )
        if recent_event_id is not None:
            return GitHubTrendFreshnessDecision(
                action="skip",
                reason="recently_published_repo_trend",
                repo_full_name=repo_full_name,
                matched_published_event_id=recent_event_id,
                cooldown_days=cooldown_days,
            )

        older_event_id = self._find_matching_pure_trend_published_event_id(
            repo_full_name,
            published_at_lt=cutoff,
        )
        return GitHubTrendFreshnessDecision(
            action="allow",
            reason="cooldown_expired" if older_event_id is not None else "first_seen_repo",
            repo_full_name=repo_full_name,
            matched_published_event_id=None,
            cooldown_days=cooldown_days,
        )

    def mark_skipped_signals(
        self,
        signal_ids: list[str],
        decision: GitHubTrendFreshnessDecision,
        *,
        skipped_at: datetime | None = None,
    ) -> int:
        """标记被冷却期跳过的 SourceSignal。

        输入：SourceSignal ID 列表、skip 决策和可选跳过时间。
        输出：实际更新的 SourceSignal 数量。
        """
        if decision.action != "skip":
            return 0

        timestamp = _normalize_datetime(skipped_at or datetime.now(UTC)).isoformat()
        changed = 0
        for signal_id in signal_ids:
            signal = self.session.get(SourceSignal, signal_id)
            if signal is None:
                continue
            metadata = dict(signal.metadata_json or {})
            metadata["github_trend_freshness"] = {
                "decision": decision.action,
                "reason": decision.reason,
                "repo_full_name": decision.repo_full_name,
                "matched_published_event_id": decision.matched_published_event_id,
                "cooldown_days": decision.cooldown_days,
                "skipped_at": timestamp,
            }
            signal.status = self.SKIPPED_STATUS
            signal.metadata_json = metadata
            changed += 1

        self.session.flush()
        return changed

    def _resolve_group_repo_full_name(self, group: EditorialCandidateGroup) -> str | None:
        """解析候选 group 的 GitHub repo 身份。

        输入：EditorialCandidateGroup。
        输出：小写 `owner/repo`；无法识别时返回 None。
        """
        normalized = _normalize_repo_full_name(group.repo_full_name)
        if normalized:
            return normalized

        for signal_id in group.signal_ids:
            signal = self.session.get(SourceSignal, signal_id)
            if signal is None:
                continue
            normalized = _normalize_repo_full_name(extract_repo_full_name(signal))
            if normalized:
                return normalized
        return None

    def _find_matching_pure_trend_published_event_id(
        self,
        repo_full_name: str,
        *,
        published_at_gte: datetime | None = None,
        published_at_lt: datetime | None = None,
    ) -> str | None:
        """查找匹配 repo 的历史纯 GitHub trend 发布事件。

        输入：repo 名和发布时间窗口。
        输出：最新匹配的 PublishedEvent ID；没有匹配时返回 None。
        """
        statement = (
            select(PublishedEvent, Source.source_key, SourceSignal)
            .join(EventCandidate, EventCandidate.id == PublishedEvent.candidate_id)
            .join(EventCandidateSignal, EventCandidateSignal.candidate_id == EventCandidate.id)
            .join(SourceSignal, SourceSignal.id == EventCandidateSignal.signal_id)
            .join(Source, Source.id == SourceSignal.source_id)
            .where(PublishedEvent.status == "published")
            .order_by(PublishedEvent.published_at.desc(), PublishedEvent.created_at.desc(), PublishedEvent.id.desc())
        )
        if published_at_gte is not None:
            statement = statement.where(PublishedEvent.published_at >= published_at_gte)
        if published_at_lt is not None:
            statement = statement.where(PublishedEvent.published_at < published_at_lt)

        events: dict[str, dict[str, object]] = {}
        for published, source_key, signal in self.session.execute(statement).all():
            event = events.setdefault(
                published.id,
                {
                    "published_at": published.published_at,
                    "source_keys": set(),
                    "repo_full_names": set(),
                },
            )
            event["source_keys"].add(_normalize_source_key(source_key))
            signal_repo = _normalize_repo_full_name(extract_repo_full_name(signal))
            if signal_repo:
                event["repo_full_names"].add(signal_repo)

        for event_id, event in events.items():
            source_keys = event["source_keys"]
            repo_full_names = event["repo_full_names"]
            if repo_full_name in repo_full_names and source_keys == {self.TREND_SOURCE_KEY}:
                return event_id
        return None


def _normalize_source_key(value: str | None) -> str:
    """规范化 source key。

    输入：可能为空的 source key。
    输出：小写且去除空白的 source key。
    """
    return str(value or "").strip().lower()


def _normalize_repo_full_name(value: str | None) -> str | None:
    """规范化 GitHub repo 全名。

    输入：可能大小写混用的 `owner/repo`。
    输出：小写 `owner/repo`；格式不完整时返回 None。
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


__all__ = ["GitHubTrendFreshnessDecision", "GitHubTrendFreshnessService"]

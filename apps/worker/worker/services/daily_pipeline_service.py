from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.collect_source_signals import (
    CollectionStats,
    build_collection_window,
    build_summary,
    collect_selected_sources,
    expand_source_groups,
)
from scripts.run_event_pipeline import select_candidate_groups
from worker.config import Settings
from worker.models import PipelineRun, Source, SourceSignal
from worker.observability.run_logger import NullRunLogger, RunLogger
from worker.services.editorial_candidate_service import EditorialCandidateGroup, EditorialCandidateService
from worker.services.github_trend_freshness_service import GitHubTrendFreshnessService
from worker.services.signal_service import SignalService
from worker.workflows.event_pipeline import run_event_pipeline


@dataclass(frozen=True)
class DailyPipelineConfig:
    """手动日常 pipeline 运行配置。

    输入：来自 `.env` 或测试显式传入的运行参数。
    输出：供 DailyPipelineService 编排采集、selector 和发布流程使用的不可变配置。
    """

    source_group: str = "daily_all"
    lookback_hours: int = 8
    selector_batch_size: int = 30
    continue_on_source_error: bool = True
    disable_agent_fallback: bool = True
    max_selected: int | None = 5
    agent_mode: str = "llm"
    candidate_lookback_hours: int = 48

    @classmethod
    def from_env(cls, settings: Settings) -> "DailyPipelineConfig":
        """从环境变量和 Settings 构造手动日常 pipeline 配置。

        输入：`load_settings()` 返回的 Settings；函数内部读取当前进程环境变量。
        输出：DailyPipelineConfig；空的 max selected 表示不限制。
        """
        import os

        raw_max_selected = os.getenv("DAILY_PIPELINE_MAX_SELECTED", "5").strip()
        max_selected = None if raw_max_selected in {"", "0"} else int(raw_max_selected)
        return cls(
            source_group=os.getenv("DAILY_PIPELINE_SOURCE_GROUP", "daily_all"),
            lookback_hours=int(os.getenv("DAILY_PIPELINE_LOOKBACK_HOURS", "8")),
            selector_batch_size=int(os.getenv("DAILY_PIPELINE_SELECTOR_BATCH_SIZE", "30")),
            continue_on_source_error=_env_bool("DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR", default=True),
            disable_agent_fallback=_env_bool("DAILY_PIPELINE_DISABLE_AGENT_FALLBACK", default=True),
            max_selected=max_selected,
            agent_mode=settings.agent_mode,
        )


class DailyPipelineService:
    """手动日常全流程编排服务。

    输入：SQLAlchemy Session，以及可选测试替身 collector/selector/pipeline runner。
    输出：`run_once()` 返回可直接打印给用户的漏斗 summary。
    """

    def __init__(
        self,
        session: Session,
        *,
        collector: Callable[[Namespace], dict[str, Any]] | None = None,
        selector_agent: object | None = None,
        pipeline_runner: Callable[..., Any] | None = None,
        now_provider: Callable[[], datetime] | None = None,
        logger: RunLogger | None = None,
    ):
        """初始化服务实例。

        输入：数据库 Session、可选采集函数、可选 selector agent、可选 pipeline runner 和当前时间函数。
        输出：绑定这些依赖的 DailyPipelineService。
        """
        self.session = session
        self.collector = collector
        self.selector_agent = selector_agent
        self.pipeline_runner = pipeline_runner or self._run_event_pipeline
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self.logger = logger or NullRunLogger()

    def run_once(self, config: DailyPipelineConfig) -> dict[str, Any]:
        """运行一次手动日常全流程。

        输入：DailyPipelineConfig。
        输出：包含采集、工程初筛、selector、pipeline 和发布计数的 summary 字典。
        """
        with self.logger.stage(
            component="daily_pipeline",
            stage="daily_pipeline",
            message_zh="日常流水线",
            heartbeat_interval_seconds=30,
            counts={
                "lookback_hours": config.lookback_hours,
                "selector_batch_size": config.selector_batch_size,
                "max_selected": config.max_selected,
            },
            metadata={"source_group": config.source_group, "agent_mode": config.agent_mode},
        ):
            summary = self._run_once_impl(config)
            self.logger.info(
                component="daily_pipeline",
                stage="daily_pipeline",
                event="succeeded",
                status=str(summary.get("status")),
                message_zh="运行完成",
                counts={
                    "raw_new_signals": summary.get("raw_new_signals_count", 0),
                    "candidate_groups": summary.get("candidate_groups_count", 0),
                    "selected": summary.get("selector_selected_count", 0),
                    "published": summary.get("published_count", 0),
                    "pipeline_runs": summary.get("pipeline_runs_count", 0),
                },
            )
            return summary

    def _run_once_impl(self, config: DailyPipelineConfig) -> dict[str, Any]:
        collection_started_at = _normalize_datetime(self.now_provider())
        collection_summary = self._collect(config, collection_started_at=collection_started_at)
        with self.logger.stage(component="daily_pipeline", stage="load_new_signals", message_zh="新信号读取"):
            new_signal_rows = self._load_new_signal_rows(collection_started_at=collection_started_at)
        raw_new_signals_count = len(new_signal_rows)
        self.logger.info(
            component="daily_pipeline",
            stage="load_new_signals",
            event="succeeded",
            message_zh="新信号读取完成",
            counts={"raw_new_signals": raw_new_signals_count},
            metadata={"sample_titles": [row[0].original_title for row in new_signal_rows[:5]]},
        )
        if raw_new_signals_count == 0:
            return self._base_summary(
                status="no_new_signals",
                config=config,
                collection_started_at=collection_started_at,
                collection_summary=collection_summary,
                raw_new_signals_count=0,
            )

        with self.logger.stage(component="daily_pipeline", stage="build_candidate_groups", message_zh="候选构造"):
            groups = build_candidate_groups_from_signal_rows(
                self.session,
                new_signal_rows,
                lookback_hours=config.candidate_lookback_hours,
                now=collection_started_at,
            )
        self.logger.info(
            component="daily_pipeline",
            stage="build_candidate_groups",
            event="succeeded",
            message_zh="候选构造完成",
            counts={"candidate_groups": len(groups), "raw_new_signals": raw_new_signals_count},
            metadata={"samples": candidate_groups_summary(groups[:5])},
        )
        groups, github_trend_freshness_summary = self._apply_github_trend_freshness_gate(
            groups,
            now=collection_started_at,
        )
        if not groups:
            return {
                **self._base_summary(
                    status="no_candidate_groups",
                    config=config,
                    collection_started_at=collection_started_at,
                    collection_summary=collection_summary,
                    raw_new_signals_count=raw_new_signals_count,
                ),
                **github_trend_freshness_summary,
                "candidate_groups_count": 0,
                "candidate_groups": [],
            }

        with self.logger.stage(
            component="selector",
            stage="editorial_selector",
            message_zh="编辑筛选",
            heartbeat_interval_seconds=30,
            counts={"candidate_groups": len(groups), "batch_size": config.selector_batch_size},
        ):
            outcome = select_candidate_groups(
                groups,
                top_n=len(groups),
                agent_mode=config.agent_mode,
                selector_agent=self.selector_agent,
                allow_fallback=not config.disable_agent_fallback,
                batch_size=config.selector_batch_size,
                logger=self.logger,
            )
        selection = outcome.selection
        all_selected_items = list(selection.selected)
        selected_items = apply_max_selected(all_selected_items, max_selected=config.max_selected)
        self.logger.info(
            component="selector",
            stage="editorial_selector",
            event="succeeded",
            message_zh="编辑筛选完成",
            counts={
                "selected": len(all_selected_items),
                "rejected": len(selection.rejected),
                "manual_review": len(selection.manual_review),
                "selected_after_limit": len(selected_items),
            },
            metadata={
                "selector_mode": outcome.selector_mode,
                "batches": outcome.selector_batches_count,
                "selected_samples": [
                    {"candidate_group_id": item.candidate_group_id, "reason": item.reason}
                    for item in all_selected_items[:5]
                ],
            },
        )
        if not selected_items:
            return {
                **self._base_summary(
                    status="no_selected_candidates",
                    config=config,
                    collection_started_at=collection_started_at,
                    collection_summary=collection_summary,
                    raw_new_signals_count=raw_new_signals_count,
                ),
                **github_trend_freshness_summary,
                "candidate_groups_count": len(groups),
                "candidate_groups": candidate_groups_summary(groups),
                "selector_mode": outcome.selector_mode,
                "selector_batches_count": outcome.selector_batches_count,
                "selector_selected_count": len(all_selected_items),
                "selector_rejected_count": len(selection.rejected),
                "selector_manual_review_count": len(selection.manual_review),
                "selected_groups_count": 0,
            }

        states = []
        base_run_key = f"manual-daily-{collection_started_at.strftime('%Y%m%d%H%M%S')}"
        for index, item in enumerate(selected_items, start=1):
            run_key = base_run_key if len(selected_items) == 1 else f"{base_run_key}-{index}"
            with self.logger.stage(
                component="workflow",
                stage="candidate_pipeline",
                message_zh=f"事件生产 {index}/{len(selected_items)}",
                heartbeat_interval_seconds=30,
                candidate_group_id=item.candidate_group_id,
                counts={"signal_ids": len(item.signal_ids), "index": index, "total": len(selected_items)},
                metadata={"event_title": item.event_title, "run_key": run_key},
            ):
                state = self.pipeline_runner(
                    signal_ids=item.signal_ids,
                    run_key=run_key,
                    source_scope={
                        "source": "manual_daily_pipeline",
                        "candidate_group_id": item.candidate_group_id,
                        "collection_started_at": collection_started_at.isoformat(),
                    },
                    agent_mode=config.agent_mode,
                    allow_fallback=not config.disable_agent_fallback,
                    logger=self.logger,
                )
            states.append(state)
            self.session.flush()
            self.logger.info(
                component="workflow",
                stage="candidate_pipeline",
                event="succeeded",
                status=getattr(state, "status", None),
                message_zh="事件生产完成",
                candidate_group_id=item.candidate_group_id,
                pipeline_run_id=getattr(state, "run_id", None),
                counts={"published": 1 if getattr(state, "published_event_id", None) else 0},
            )

        run_ids = [state.run_id for state in states if getattr(state, "run_id", None)]
        runs = list(self.session.scalars(select(PipelineRun).where(PipelineRun.id.in_(run_ids))).all()) if run_ids else []
        status = "succeeded" if all(getattr(state, "status", None) == "succeeded" for state in states) else "partial_failed"
        return {
            **self._base_summary(
                status=status,
                config=config,
                collection_started_at=collection_started_at,
                collection_summary=collection_summary,
                raw_new_signals_count=raw_new_signals_count,
            ),
            **github_trend_freshness_summary,
            "candidate_groups_count": len(groups),
            "candidate_groups": candidate_groups_summary(groups),
            "selector_mode": outcome.selector_mode,
            "selector_batches_count": outcome.selector_batches_count,
            "selector_selected_count": len(all_selected_items),
            "selector_rejected_count": len(selection.rejected),
            "selector_manual_review_count": len(selection.manual_review),
            "selected_groups_count": len(selected_items),
            "pipeline_runs_count": len(runs),
            "run_ids": run_ids,
            "published_count": sum(run.published_count for run in runs),
        }

    def _apply_github_trend_freshness_gate(
        self,
        groups: list[EditorialCandidateGroup],
        *,
        now: datetime,
    ) -> tuple[list[EditorialCandidateGroup], dict[str, Any]]:
        """在 selector 前过滤近期重复 GitHub repo trend group。

        输入：候选 group 列表和本轮运行时间。
        输出：允许进入 selector 的 group，以及可打印的 GitHub trend freshness 统计。
        """
        service = GitHubTrendFreshnessService(self.session)
        allowed_groups: list[EditorialCandidateGroup] = []
        summary = empty_github_trend_freshness_summary()

        for group in groups:
            source_keys = {str(source_key or "").strip().lower() for source_key in group.source_keys}
            is_github_trend_related = GitHubTrendFreshnessService.TREND_SOURCE_KEY in source_keys
            if is_github_trend_related:
                summary["github_trend_groups_total"] += 1

            decision = service.evaluate_group(group, now=now)
            if decision.action == "skip":
                skipped_signals_count = service.mark_skipped_signals(group.signal_ids, decision, skipped_at=now)
                summary["github_trend_groups_skipped"] += 1
                summary["skipped_duplicate_trend_signals"] += skipped_signals_count
                summary["github_trend_freshness_examples"].append(
                    {
                        "candidate_group_id": group.group_id,
                        "repo_full_name": decision.repo_full_name,
                        "reason": decision.reason,
                        "matched_published_event_id": decision.matched_published_event_id,
                        "skipped_signals_count": skipped_signals_count,
                    }
                )
                continue

            if is_github_trend_related:
                summary["github_trend_groups_allowed"] += 1
            allowed_groups.append(group)

        return allowed_groups, summary

    def _collect(self, config: DailyPipelineConfig, *, collection_started_at: datetime) -> dict[str, Any]:
        """运行本轮来源采集。

        输入：DailyPipelineConfig 和采集开始时间。
        输出：采集脚本兼容的 summary 字典。
        """
        args = build_collection_args(config, now=collection_started_at)
        self.logger.info(
            component="collector",
            stage="collection_window",
            event="started",
            message_zh="采集窗口",
            counts={"lookback_hours": config.lookback_hours},
            metadata={
                "start": args.collection_window.start.isoformat(),
                "end": args.collection_window.end.isoformat(),
                "source_group": config.source_group,
                "sources": list(args.source),
                "official_profiles": list(getattr(args, "official_profile", [])),
            },
        )
        with self.logger.stage(
            component="collector",
            stage="collect_sources",
            message_zh="来源采集",
            heartbeat_interval_seconds=30,
            counts={"source_count": len(args.source), "official_profiles": len(getattr(args, "official_profile", []))},
        ):
            if self.collector is not None:
                summary = self.collector(args)
                self._emit_collection_summary(summary)
                return summary

            service = SignalService(self.session)
            source_keys = collect_selected_sources(session_service=service, args=args)
            self.session.flush()
            summary = build_summary(self.session, source_keys=source_keys)
            summary["window"] = {
                "lookback_hours": args.lookback_hours,
                "start": args.collection_window.start.isoformat(),
                "end": args.collection_window.end.isoformat(),
            }
            summary["skipped_signals"] = args.collection_stats.as_dict()
            if args.source_failures:
                summary["failed_sources_count"] = len(args.source_failures)
                summary["failed_sources"] = args.source_failures
        self._emit_collection_summary(summary)
        return summary

    def _emit_collection_summary(self, summary: dict[str, Any]) -> None:
        for source_key in summary.get("source_keys", []) or []:
            self.logger.info(
                component="collector",
                stage="collect_source",
                event="succeeded",
                message_zh="来源采集成功",
                source_key=str(source_key),
            )
        for failure in summary.get("failed_sources", []) or []:
            self.logger.error(
                component="collector",
                stage="collect_source",
                event="failed",
                message_zh="来源采集失败",
                source_key=str(failure.get("source_key", "")),
                error_message=str(failure.get("error", "")),
            )
        self.logger.info(
            component="collector",
            stage="collect_sources",
            event="succeeded",
            message_zh="采集汇总",
            counts={
                "sources": summary.get("sources_count", 0),
                "signals": summary.get("signals_count", 0),
                "failed_sources": summary.get("failed_sources_count", 0),
                **(summary.get("skipped_signals", {}) or {}),
            },
            metadata={"source_keys": summary.get("source_keys", []), "window": summary.get("window", {})},
        )

    def _load_new_signal_rows(self, *, collection_started_at: datetime) -> list[tuple[SourceSignal, str]]:
        """读取本轮新增且尚未被 pipeline 处理的 SourceSignal。

        输入：本轮采集开始时间。
        输出：按 collected_at / id 排序的 `(SourceSignal, source_key)` 列表。
        """
        rows = self.session.execute(
            select(SourceSignal, Source.source_key)
            .join(Source, Source.id == SourceSignal.source_id)
            .where(SourceSignal.collected_at >= collection_started_at)
            .where(SourceSignal.pipeline_run_id.is_(None))
            .order_by(SourceSignal.collected_at.asc(), SourceSignal.id.asc())
        ).all()
        return [(row[0], row[1]) for row in rows]

    def _run_event_pipeline(
        self,
        *,
        signal_ids: list[str],
        run_key: str,
        source_scope: dict[str, Any],
        agent_mode: str,
        allow_fallback: bool,
        logger: RunLogger | None = None,
    ) -> Any:
        """调用现有 LangGraph 事件生产 workflow。

        输入：signal_ids、run_key、source_scope、agent_mode 和是否允许 fallback。
        输出：run_event_pipeline 返回的 EventPipelineState。
        """
        return run_event_pipeline(
            self.session,
            signal_ids=signal_ids,
            run_key=run_key,
            source_scope=source_scope,
            agent_mode=agent_mode,
            allow_fallback=allow_fallback,
            logger=logger,
        )

    def _base_summary(
        self,
        *,
        status: str,
        config: DailyPipelineConfig,
        collection_started_at: datetime,
        collection_summary: dict[str, Any],
        raw_new_signals_count: int,
    ) -> dict[str, Any]:
        """构造所有状态共享的 summary 字段。

        输入：状态、配置、采集开始时间、采集 summary 和本轮新增信号数。
        输出：包含默认漏斗计数字段的 summary 字典。
        """
        return {
            "status": status,
            "agent_mode": config.agent_mode,
            "collection_started_at": collection_started_at.isoformat(),
            "collection_summary": collection_summary,
            "raw_new_signals_count": raw_new_signals_count,
            "candidate_groups_count": 0,
            "candidate_groups": [],
            "selector_mode": None,
            "selector_batches_count": 0,
            "selector_selected_count": 0,
            "selector_rejected_count": 0,
            "selector_manual_review_count": 0,
            "selected_groups_count": 0,
            "pipeline_runs_count": 0,
            "run_ids": [],
            "published_count": 0,
            **empty_github_trend_freshness_summary(),
        }


def build_collection_args(config: DailyPipelineConfig, *, now: datetime) -> Namespace:
    """构造 collect_source_signals 兼容参数对象。

    输入：DailyPipelineConfig 和当前时间。
    输出：可传给 collect_selected_sources 的 argparse Namespace。
    """
    args = Namespace(
        database_url=None,
        create_schema_for_smoke=False,
        fixture_mode=False,
        source=[],
        source_group=[config.source_group],
        hn_days=7,
        hn_limit=5,
        github_repo=[],
        github_limit=3,
        github_token_env="GITHUB_TOKEN",
        github_trend_query=[],
        github_trend_limit=5,
        github_trend_min_stars=100,
        github_trend_token_env="GITHUB_TOKEN",
        snapshot_bucket=None,
        official_profile=[],
        official_limit=5,
        lookback_hours=config.lookback_hours,
        now=now.isoformat(),
        continue_on_source_error=config.continue_on_source_error,
        source_failures=[],
        collection_window=build_collection_window(now=now, lookback_hours=config.lookback_hours),
        collection_stats=CollectionStats(),
    )
    expand_source_groups(args)
    return args


def build_candidate_groups_from_signal_rows(
    session: Session,
    signal_rows: list[tuple[SourceSignal, str]],
    *,
    lookback_hours: int,
    now: datetime,
) -> list[EditorialCandidateGroup]:
    """从显式 signal rows 构造候选分组。

    输入：Session、本轮新增 signal rows、候选 lookback 小时数和当前时间。
    输出：复用 EditorialCandidateService 规则构造的 candidate groups。
    """
    service = EditorialCandidateService(session)
    return service.build_candidate_groups_from_rows(signal_rows, lookback_hours=lookback_hours, now=now)


def apply_max_selected(selected_items: list[Any], *, max_selected: int | None) -> list[Any]:
    """按配置限制 selected item 数量。

    输入：selector selected item 列表和可选最大数量。
    输出：限制后的 selected item 列表；None 或 0 表示不限制。
    """
    if max_selected is None or max_selected <= 0:
        return selected_items
    return selected_items[:max_selected]


def candidate_groups_summary(groups: list[EditorialCandidateGroup]) -> list[dict[str, Any]]:
    """生成候选 group 的可打印摘要。

    输入：EditorialCandidateGroup 列表。
    输出：只包含 id、title、signal_ids、source_keys 等非敏感字段的 dict 列表。
    """
    return [
        {
            "candidate_group_id": group.group_id,
            "title": group.title,
            "signal_ids": list(group.signal_ids),
            "source_keys": list(group.source_keys),
            "merge_reason": group.merge_reason,
        }
        for group in groups
    ]


def empty_github_trend_freshness_summary() -> dict[str, Any]:
    """构造 GitHub trend freshness summary 零值。

    输入：无。
    输出：所有日常 pipeline 返回状态共享的 GitHub trend freshness 统计字段。
    """
    return {
        "github_trend_groups_total": 0,
        "github_trend_groups_skipped": 0,
        "github_trend_groups_allowed": 0,
        "skipped_duplicate_trend_signals": 0,
        "github_trend_freshness_examples": [],
    }


def _normalize_datetime(value: datetime) -> datetime:
    """统一 datetime 为 UTC aware。

    输入：可能是 naive 或 aware 的 datetime。
    输出：带 UTC 时区的 datetime。
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _env_bool(name: str, *, default: bool) -> bool:
    """读取布尔环境变量。

    输入：环境变量名和默认值。
    输出：`1/true/yes/on` 为 True，`0/false/no/off` 为 False，其他空值返回默认值。
    """
    import os

    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default

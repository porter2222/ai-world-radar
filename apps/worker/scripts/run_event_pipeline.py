from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from worker.config import load_settings
from worker.db.session import create_worker_engine
from worker.models import Base, PipelineRun, Source, SourceSignal
from worker.agents.editorial_selector_agent import EditorialSelectorLLMAgent
from worker.observability.run_logger import NullRunLogger, RunLogger
from worker.schemas.editorial_selection import (
    EditorialRejectedItem,
    EditorialSelectedItem,
    EditorialSelectionResult,
)
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.editorial_candidate_service import EditorialCandidateGroup, EditorialCandidateService
from worker.services.signal_service import SignalService
from worker.workflows.event_pipeline import run_event_pipeline


@dataclass(frozen=True)
class SelectorSelectionOutcome:
    """封装 selector 选择结果和运行模式。

    输入：结构化选择结果、selector 实际模式和可选 fallback 原因。
    输出：供 selector pipeline 汇总 stdout 使用的不可变结果对象。
    """

    selection: EditorialSelectionResult
    selector_mode: str
    fallback_reason: str | None = None
    selector_batches_count: int = 1


@dataclass(frozen=True)
class CandidatePipelineResult:
    """封装单个候选事件 pipeline 的执行结果。
    输入：候选分组、run_key、workflow 返回状态或异常。
    输出：供 selector pipeline 汇总 stdout 和失败隔离使用的不可变结果对象。
    """

    index: int
    candidate_group_id: str
    run_key: str
    status: str
    run_id: str | None = None
    published_event_id: str | None = None
    error: str | None = None

    def to_summary_item(self) -> dict[str, object]:
        """转换成 stdout 中的单条候选结果。
        输入：CandidatePipelineResult。
        输出：隐藏内部对象、保留追踪字段的 dict。
        """
        if self.error is not None:
            return {
                "candidate_group_id": self.candidate_group_id,
                "run_key": self.run_key,
                "status": "failed",
                "error": self.error,
            }
        return {
            "candidate_group_id": self.candidate_group_id,
            "run_key": self.run_key,
            "status": self.status,
            "run_id": self.run_id,
            "published_event_id": self.published_event_id,
        }


def parse_args() -> argparse.Namespace:
    """解析新版事件 pipeline 脚本参数。

    输入：命令行参数。
    输出：包含数据库 URL、run_key、agent mode 和 smoke 开关的 argparse Namespace。
    """
    parser = argparse.ArgumentParser(description="Run the P1-2 event dossier pipeline.")
    parser.add_argument("--database-url", default=None, help="覆盖默认 DATABASE_URL。")
    parser.add_argument("--run-key", default=None, help="本轮 pipeline run key。")
    parser.add_argument("--create-schema-for-smoke", action="store_true", help="仅本地 smoke 使用：直接 create_all。")
    parser.add_argument("--seed-demo-signal", action="store_true", help="写入一条 demo SourceSignal 后运行。")
    parser.add_argument("--source-key", default=None, help="从已入库 source_signals 中按 source_key 选择信号。")
    parser.add_argument("--limit", type=int, default=1, help="按 source_key 选择信号时的最大数量。")
    parser.add_argument("--select-top-candidates", type=int, default=None, help="从 selector 输出中选择 Top N 候选组运行 pipeline。")
    parser.add_argument("--select-all-candidates", action="store_true", help="处理 selector 认为可进入后续流程的全部候选组。")
    parser.add_argument("--candidate-pool-limit", type=int, default=60, help="selector 前候选池最大 source_signals 数。")
    parser.add_argument("--selector-batch-size", type=int, default=30, help="LLM selector 每次请求处理的候选组数量。")
    parser.add_argument("--candidate-concurrency", type=int, default=3, help="selector 选中候选后的并发生产数量，允许 1-5。")
    parser.add_argument("--agent-mode", choices=["stub", "llm"], default=None, help="覆盖 AGENT_MODE，选择 stub 或 llm。")
    parser.add_argument("--disable-agent-fallback", action="store_true", help="Strict real LLM smoke: disable stub fallback.")
    return parser.parse_args()


def main() -> int:
    """运行新版事件 pipeline 脚本。

    输入：命令行参数和可选临时数据库。
    输出：向 stdout 打印 JSON 摘要，并用进程退出码表达成功或失败。
    """
    args = parse_args()
    settings = load_settings()
    agent_mode = args.agent_mode or settings.agent_mode
    engine = create_worker_engine(args.database_url) if args.database_url else create_worker_engine()
    if args.create_schema_for_smoke:
        Base.metadata.create_all(engine)

    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        if args.select_top_candidates is not None or args.select_all_candidates:
            summary = run_selector_pipeline(
                session,
                args=args,
                agent_mode=agent_mode,
                session_factory=session_factory,
                allow_fallback=not args.disable_agent_fallback,
            )
            session.commit()
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
            return 0

        signal_ids = []
        source_scope = {"source": "manual"}
        if args.seed_demo_signal:
            signal_ids.extend(seed_demo_signal(session))
            source_scope = {"source": "demo"}
        if args.source_key:
            signal_ids.extend(load_signal_ids_by_source_key(session, source_key=args.source_key, limit=args.limit))
            source_scope = {"source": args.source_key}
        if not signal_ids:
            raise ValueError("No signal_ids available. Use --seed-demo-signal or --source-key.")
        run_key = args.run_key or f"manual-p1-2-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        state = run_event_pipeline(
            session,
            signal_ids=signal_ids,
            run_key=run_key,
            source_scope=source_scope,
            agent_mode=agent_mode,
            allow_fallback=not args.disable_agent_fallback,
        )
        session.commit()

        run = session.scalar(select(PipelineRun).where(PipelineRun.id == state.run_id))
        summary = {
            "status": state.status,
            "agent_mode": agent_mode,
            "run_id": state.run_id,
            "published_event_id": state.published_event_id,
            "signals_count": run.signals_count if run else 0,
            "candidates_count": run.candidates_count if run else 0,
            "dossiers_count": run.dossiers_count if run else 0,
            "published_count": run.published_count if run else 0,
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        session.rollback()
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1
    finally:
        session.close()
        engine.dispose()


def seed_demo_signal(session) -> list[str]:
    """写入 demo 来源和来源信号。

    输入：调用方管理事务的 SQLAlchemy Session。
    输出：可传给 workflow 的 SourceSignal ID 列表。
    """
    service = SignalService(session)
    service.upsert_source(
        SourceCreate(
            source_key="demo",
            name="Demo Source",
            source_type="fixture",
            fetch_method="manual",
            entry_url="https://example.com/demo",
        )
    )
    signal = service.upsert_signal(
        SourceSignalCreate(
            source_key="demo",
            source_item_id="demo-1",
            original_title="OpenAI releases a new developer tool",
            original_url="https://example.com/openai-tool",
            raw_summary="Developers discuss the new tool and pricing.",
            source_hash="demo:openai-developer-tool",
            heat_metrics={"points": 120, "comments": 45},
        )
    )
    return [signal.id]


def load_signal_ids_by_source_key(session, *, source_key: str, limit: int) -> list[str]:
    """按来源 key 读取已入库的 SourceSignal ID。

    输入：调用方管理事务的 SQLAlchemy Session、source_key 和最大数量。
    输出：按 created_at 倒序排列、可传给 workflow 的 SourceSignal ID 列表。
    """
    statement = (
        select(SourceSignal.id)
        .join(Source, Source.id == SourceSignal.source_id)
        .where(Source.source_key == source_key)
        .order_by(SourceSignal.created_at.desc(), SourceSignal.id.desc())
        .limit(limit)
    )
    return list(session.scalars(statement).all())


def run_selector_pipeline(
    session: Session,
    *,
    args: argparse.Namespace,
    agent_mode: str,
    session_factory: Callable[[], Session] | None = None,
    selector_agent: object | None = None,
    allow_fallback: bool = True,
    workflow_runner: Callable[..., Any] = run_event_pipeline,
) -> dict[str, object]:
    """从 selector 结果运行一个或多个事件 pipeline。

    输入：主 Session、脚本参数、agent_mode、可选 session_factory / selector agent / workflow runner。
    输出：stdout 使用的 JSON summary 字典；只对 selected Top N group 运行 workflow，多个候选可并发生产。
    """
    select_all_candidates = bool(getattr(args, "select_all_candidates", False))
    requested_top_n = getattr(args, "select_top_candidates", None)
    if not select_all_candidates and (requested_top_n is None or requested_top_n <= 0):
        raise ValueError("--select-top-candidates must be greater than 0")
    candidate_concurrency = resolve_candidate_concurrency(getattr(args, "candidate_concurrency", 3))

    candidate_service = EditorialCandidateService(session)
    groups = candidate_service.build_candidate_groups(candidate_pool_limit=args.candidate_pool_limit)
    top_n = len(groups) if select_all_candidates else requested_top_n
    outcome = select_candidate_groups(
        groups,
        top_n=top_n,
        agent_mode=agent_mode,
        selector_agent=selector_agent,
        allow_fallback=allow_fallback,
        batch_size=getattr(args, "selector_batch_size", None),
    )
    selection = outcome.selection
    selected_items = selection.selected[:top_n]
    if not selected_items:
        raise ValueError("No selected candidate groups available")

    base_run_key = args.run_key or f"manual-p1-9-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    if session_factory is not None:
        results = run_selected_candidates_concurrently(
            selected_items,
            base_run_key=base_run_key,
            session_factory=session_factory,
            agent_mode=agent_mode,
            allow_fallback=allow_fallback,
            candidate_concurrency=candidate_concurrency,
            workflow_runner=workflow_runner,
        )
    else:
        results = run_selected_candidates_serially(
            session,
            selected_items,
            base_run_key=base_run_key,
            agent_mode=agent_mode,
            allow_fallback=allow_fallback,
            workflow_runner=workflow_runner,
        )

    run_ids = [result.run_id for result in results if result.run_id is not None]
    runs = list(session.scalars(select(PipelineRun).where(PipelineRun.id.in_(run_ids))).all()) if run_ids else []
    failed_count = len([result for result in results if result.status == "failed"])
    succeeded_count = len(results) - failed_count
    if failed_count == 0:
        status = "succeeded"
    elif succeeded_count > 0:
        status = "partial_failed"
    else:
        status = "failed"
    summary = {
        "status": status,
        "agent_mode": agent_mode,
        "selector_mode": outcome.selector_mode,
        "selector_batches_count": outcome.selector_batches_count,
        "candidate_concurrency": candidate_concurrency,
        "selected_groups_count": len(selected_items),
        "rejected_groups_count": len(selection.rejected),
        "manual_review_groups_count": len(selection.manual_review),
        "pipeline_runs_count": len(runs),
        "run_ids": run_ids,
        "published_count": sum(run.published_count for run in runs),
        "failed_count": failed_count,
        "candidate_results": [result.to_summary_item() for result in sorted(results, key=lambda result: result.index)],
    }
    if outcome.fallback_reason is not None:
        summary["selector_fallback_reason"] = outcome.fallback_reason
    return summary


def resolve_candidate_concurrency(value: int) -> int:
    """校验候选事件级并发数量。
    输入：命令行或测试传入的并发数量。
    输出：1 到 5 之间的安全并发数；超出范围时抛出 ValueError。
    """
    if value < 1 or value > 5:
        raise ValueError("--candidate-concurrency must be between 1 and 5")
    return value


def run_selected_candidates_serially(
    session: Session,
    selected_items: list[EditorialSelectedItem],
    *,
    base_run_key: str,
    agent_mode: str,
    allow_fallback: bool,
    workflow_runner: Callable[..., Any],
) -> list[CandidatePipelineResult]:
    """串行运行 selector 选中的候选事件。
    输入：当前 Session、selected items、run key 前缀和 workflow runner。
    输出：每个候选的执行结果；任意候选异常会按单条失败记录并继续后续候选。
    """
    results: list[CandidatePipelineResult] = []
    for index, item in enumerate(selected_items, start=1):
        run_key = build_candidate_run_key(base_run_key, index=index, total=len(selected_items))
        try:
            state = workflow_runner(
                session,
                signal_ids=item.signal_ids,
                run_key=run_key,
                source_scope={"source": "editorial_selector", "candidate_group_id": item.candidate_group_id},
                agent_mode=agent_mode,
                allow_fallback=allow_fallback,
            )
            session.flush()
            results.append(
                CandidatePipelineResult(
                    index=index,
                    candidate_group_id=item.candidate_group_id,
                    run_key=run_key,
                    status=state.status,
                    run_id=state.run_id,
                    published_event_id=state.published_event_id,
                )
            )
        except Exception as exc:  # noqa: BLE001 - 单条候选失败需要汇总到本轮结果而不是中断整轮。
            session.rollback()
            results.append(
                CandidatePipelineResult(
                    index=index,
                    candidate_group_id=item.candidate_group_id,
                    run_key=run_key,
                    status="failed",
                    error=str(exc),
                )
            )
    return results


def run_selected_candidates_concurrently(
    selected_items: list[EditorialSelectedItem],
    *,
    base_run_key: str,
    session_factory: Callable[[], Session],
    agent_mode: str,
    allow_fallback: bool,
    candidate_concurrency: int,
    workflow_runner: Callable[..., Any],
) -> list[CandidatePipelineResult]:
    """并发运行 selector 选中的候选事件。
    输入：selected items、Session 工厂、Agent 配置、并发数和 workflow runner。
    输出：每个候选的执行结果；每个候选使用独立 Session 和独立事务。
    """
    results: list[CandidatePipelineResult] = []
    with ThreadPoolExecutor(max_workers=candidate_concurrency) as executor:
        futures = [
            executor.submit(
                run_single_candidate_pipeline,
                item,
                index=index,
                total=len(selected_items),
                base_run_key=base_run_key,
                session_factory=session_factory,
                agent_mode=agent_mode,
                allow_fallback=allow_fallback,
                workflow_runner=workflow_runner,
            )
            for index, item in enumerate(selected_items, start=1)
        ]
        for future in as_completed(futures):
            results.append(future.result())
    return results


def run_single_candidate_pipeline(
    item: EditorialSelectedItem,
    *,
    index: int,
    total: int,
    base_run_key: str,
    session_factory: Callable[[], Session],
    agent_mode: str,
    allow_fallback: bool,
    workflow_runner: Callable[..., Any],
) -> CandidatePipelineResult:
    """运行单个候选事件 pipeline。
    输入：一个 selected item、独立 Session 工厂、run key 信息和 workflow runner。
    输出：单个候选的成功或失败结果；内部负责 commit / rollback / close。
    """
    run_key = build_candidate_run_key(base_run_key, index=index, total=total)
    session = session_factory()
    try:
        state = workflow_runner(
            session,
            signal_ids=item.signal_ids,
            run_key=run_key,
            source_scope={"source": "editorial_selector", "candidate_group_id": item.candidate_group_id},
            agent_mode=agent_mode,
            allow_fallback=allow_fallback,
        )
        session.commit()
        return CandidatePipelineResult(
            index=index,
            candidate_group_id=item.candidate_group_id,
            run_key=run_key,
            status=state.status,
            run_id=state.run_id,
            published_event_id=state.published_event_id,
        )
    except Exception as exc:  # noqa: BLE001 - 单候选失败必须隔离，不能影响其他线程。
        session.rollback()
        return CandidatePipelineResult(
            index=index,
            candidate_group_id=item.candidate_group_id,
            run_key=run_key,
            status="failed",
            error=str(exc),
        )
    finally:
        session.close()


def build_candidate_run_key(base_run_key: str, *, index: int, total: int) -> str:
    """生成候选事件对应的 pipeline run key。
    输入：基础 run key、当前候选序号和候选总数。
    输出：单候选时复用 base_run_key，多候选时追加序号后缀。
    """
    return base_run_key if total == 1 else f"{base_run_key}-{index}"


def select_candidate_groups(
    groups: list[EditorialCandidateGroup],
    *,
    top_n: int,
    agent_mode: str,
    selector_agent: object | None = None,
    allow_fallback: bool = True,
    batch_size: int | None = None,
    logger: RunLogger | None = None,
) -> SelectorSelectionOutcome:
    """运行 selector 或 stub selector。

    输入：候选分组、Top N、agent_mode、可选 selector agent 和是否允许 stub fallback。
    输出：SelectorSelectionOutcome；stub 模式不调用真实 LLM，llm 模式调用 LLM selector，异常时按 allow_fallback 决定是否兜底。
    """
    run_logger = logger or NullRunLogger()
    if agent_mode == "llm":
        agent = selector_agent or EditorialSelectorLLMAgent(logger=run_logger)
        try:
            selection, batches_count = run_llm_selector_in_batches(
                agent,
                groups,
                batch_size=batch_size,
                logger=run_logger,
            )
            return SelectorSelectionOutcome(
                selection=selection,
                selector_mode="llm",
                selector_batches_count=batches_count,
            )
        except Exception as exc:
            if not allow_fallback:
                raise
            run_logger.warning(
                component="selector",
                stage="editorial_selector",
                event="fallback",
                message_zh="编辑筛选失败，使用确定性兜底",
                agent_name=getattr(agent, "name", "editorial_selector"),
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                counts={"candidate_groups": len(groups), "top_n": top_n},
            )
            return SelectorSelectionOutcome(
                selection=build_stub_selection(groups, top_n=top_n),
                selector_mode="stub_fallback",
                fallback_reason=str(exc),
            )
    run_logger.info(
        component="selector",
        stage="editorial_selector",
        event="succeeded",
        message_zh="编辑筛选使用stub模式",
        counts={"candidate_groups": len(groups), "top_n": top_n},
    )
    return SelectorSelectionOutcome(selection=build_stub_selection(groups, top_n=top_n), selector_mode="stub")


def run_llm_selector_in_batches(
    agent: object,
    groups: list[EditorialCandidateGroup],
    *,
    batch_size: int | None,
    logger: RunLogger | None = None,
) -> tuple[EditorialSelectionResult, int]:
    """分批调用 LLM selector 并合并结构化结果。
    输入：selector agent、候选分组全集和可选 batch_size。
    输出：合并后的 EditorialSelectionResult 和实际调用批次数；分批只拆请求，不丢弃候选。
    """
    if batch_size is None or batch_size <= 0:
        batch_size = len(groups) or 1

    selected = []
    rejected = []
    manual_review = []
    batches_count = 0
    run_logger = logger or NullRunLogger()
    for start in range(0, len(groups), batch_size):
        batch = groups[start : start + batch_size]
        batch_index = batches_count + 1
        with run_logger.stage(
            component="selector",
            stage="editorial_selector_batch",
            message_zh="编辑筛选批次",
            agent_name=getattr(agent, "name", "editorial_selector"),
            counts={"batch_index": batch_index, "batch_size": len(batch), "candidate_groups": len(groups)},
        ):
            batch_selection = agent.select([candidate_group_to_selector_input(group) for group in batch])
        selected.extend(batch_selection.selected)
        rejected.extend(batch_selection.rejected)
        manual_review.extend(batch_selection.manual_review)
        batches_count += 1

    return EditorialSelectionResult(selected=selected, rejected=rejected, manual_review=manual_review), batches_count


def build_stub_selection(groups: list[EditorialCandidateGroup], *, top_n: int) -> EditorialSelectionResult:
    """构造确定性 selector 输出。

    输入：候选分组和 Top N。
    输出：前 Top N 进入 selected，其余进入 rejected；用于默认 stub 模式和本地回归。
    """
    selected = [
        EditorialSelectedItem(
            candidate_group_id=group.group_id,
            signal_ids=group.signal_ids,
            event_title=group.title,
            priority_score=max(0, 100 - index),
            suggested_angle="按当前来源信号进入后续写作。",
            reason="stub selector selected this group for deterministic local pipeline testing.",
        )
        for index, group in enumerate(groups[:top_n])
    ]
    rejected = [
        EditorialRejectedItem(
            candidate_group_id=group.group_id,
            reason="未进入本轮 stub selector Top N。",
        )
        for group in groups[top_n:]
    ]
    return EditorialSelectionResult(selected=selected, rejected=rejected, manual_review=[])


def candidate_group_to_selector_input(group: EditorialCandidateGroup) -> dict[str, object]:
    """把服务层 group 转换为 LLM selector 输入。

    输入：EditorialCandidateGroup。
    输出：包含 candidate_group_id、title、signal_ids、source_keys 和合并原因的 dict。
    """
    return {
        "candidate_group_id": group.group_id,
        "title": group.title,
        "signal_ids": group.signal_ids,
        "source_keys": group.source_keys,
        "canonical_url": group.canonical_url,
        "repo_full_name": group.repo_full_name,
        "merge_reason": group.merge_reason,
    }


if __name__ == "__main__":
    raise SystemExit(main())

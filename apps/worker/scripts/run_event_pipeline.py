from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from worker.config import load_settings
from worker.db.session import create_worker_engine
from worker.models import Base, PipelineRun, Source, SourceSignal
from worker.agents.editorial_selector_agent import EditorialSelectorLLMAgent
from worker.schemas.editorial_selection import (
    EditorialRejectedItem,
    EditorialSelectedItem,
    EditorialSelectionResult,
)
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.editorial_candidate_service import EditorialCandidateGroup, EditorialCandidateService
from worker.services.signal_service import SignalService
from worker.workflows.event_pipeline import run_event_pipeline


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
    parser.add_argument("--candidate-pool-limit", type=int, default=60, help="selector 前候选池最大 source_signals 数。")
    parser.add_argument("--agent-mode", choices=["stub", "llm"], default=None, help="覆盖 AGENT_MODE，选择 stub 或 llm。")
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
        if args.select_top_candidates is not None:
            summary = run_selector_pipeline(session, args=args, agent_mode=agent_mode)
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


def run_selector_pipeline(session, *, args: argparse.Namespace, agent_mode: str) -> dict[str, object]:
    """从 selector 结果运行一个或多个事件 pipeline。

    输入：Session、脚本参数和 agent_mode。
    输出：stdout 使用的 JSON summary 字典；只对 selected Top N group 运行 workflow。
    """
    if args.select_top_candidates <= 0:
        raise ValueError("--select-top-candidates must be greater than 0")

    candidate_service = EditorialCandidateService(session)
    groups = candidate_service.build_candidate_groups(candidate_pool_limit=args.candidate_pool_limit)
    selection = select_candidate_groups(groups, top_n=args.select_top_candidates, agent_mode=agent_mode)
    selected_items = selection.selected[: args.select_top_candidates]
    if not selected_items:
        raise ValueError("No selected candidate groups available")

    base_run_key = args.run_key or f"manual-p1-9-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    states = []
    for index, item in enumerate(selected_items, start=1):
        run_key = base_run_key if len(selected_items) == 1 else f"{base_run_key}-{index}"
        state = run_event_pipeline(
            session,
            signal_ids=item.signal_ids,
            run_key=run_key,
            source_scope={"source": "editorial_selector", "candidate_group_id": item.candidate_group_id},
            agent_mode=agent_mode,
        )
        states.append(state)
        session.flush()

    run_ids = [state.run_id for state in states if state.run_id is not None]
    runs = list(session.scalars(select(PipelineRun).where(PipelineRun.id.in_(run_ids))).all()) if run_ids else []
    status = "succeeded" if all(state.status == "succeeded" for state in states) else "partial_failed"
    return {
        "status": status,
        "agent_mode": agent_mode,
        "selector_mode": agent_mode,
        "selected_groups_count": len(selected_items),
        "rejected_groups_count": len(selection.rejected),
        "manual_review_groups_count": len(selection.manual_review),
        "pipeline_runs_count": len(runs),
        "run_ids": run_ids,
        "published_count": sum(run.published_count for run in runs),
    }


def select_candidate_groups(
    groups: list[EditorialCandidateGroup],
    *,
    top_n: int,
    agent_mode: str,
) -> EditorialSelectionResult:
    """运行 selector 或 stub selector。

    输入：候选分组、Top N 和 agent_mode。
    输出：EditorialSelectionResult；stub 模式不调用真实 LLM，llm 模式显式调用 LLM selector。
    """
    if agent_mode == "llm":
        agent = EditorialSelectorLLMAgent()
        return agent.select([candidate_group_to_selector_input(group) for group in groups])
    return build_stub_selection(groups, top_n=top_n)


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

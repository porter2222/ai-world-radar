from __future__ import annotations

import json
import subprocess
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from worker.models import Base
from worker.schemas.event import EventCandidateDraft, EventDossierDraft, PublishEventCommand, ReviewResultDraft
from worker.schemas.run import AgentRunRecord, PipelineRunCreate
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.event_service import EventService
from worker.services.run_log_service import RunLogService
from worker.services.signal_service import SignalService


def rich_detail_body() -> str:
    """构造 smoke 测试用详情正文。

    输入：无。
    输出：满足 EventDossierDraft 最低信息密度要求的正文。
    """
    paragraph = (
        "AI 编程 Agent 的讨论集中在开发者工作流变化、工具稳定性、上下文理解、成本和企业接入。"
        "用户阅读详情页时，需要看到事件本身的背景、讨论焦点、不同观点和后续观察方向，而不是内部流程语言。"
    )
    return "\n\n".join([paragraph for _ in range(6)])


def seed_product_query_smoke_database(database_url: str) -> None:
    """写入产品查询 smoke 所需的最小数据。

    输入：SQLite database_url。
    输出：已写入 published event、pipeline run、agent run 和 manual_review 数据。
    """
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        signal_service = SignalService(session)
        signal_service.upsert_source(
            SourceCreate(
                source_key="hn_algolia",
                name="Hacker News Algolia",
                source_type="community",
                fetch_method="api",
            )
        )
        signal = signal_service.upsert_signal(
            SourceSignalCreate(
                source_key="hn_algolia",
                source_item_id="product-smoke",
                original_title="Product query smoke event",
                original_url="https://news.ycombinator.com/item?id=product-smoke",
                source_hash="hn_algolia:product-smoke",
            )
        )
        event_service = EventService(session)
        candidate = event_service.create_candidate_with_signals(
            EventCandidateDraft(
                candidate_key="product-query-smoke",
                title="Product Query Smoke 事件",
                category="模型与产品",
                heat_score=80,
                importance_score=78,
                audience_value_score=82,
                ranking_score=85,
                ranking_reason="用于产品查询 smoke。",
            ),
            signal_ids=[signal.id],
            merge_reason="产品查询 smoke。",
        )
        dossier = event_service.save_dossier(
            candidate.id,
            EventDossierDraft(
                candidate_key="product-query-smoke",
                card_title="Product Query Smoke 事件",
                card_summary="用于验证产品查询 smoke 的发布事件。",
                category="模型与产品",
                signal_label="高热讨论",
                detail_title="Product Query Smoke 事件",
                detail_summary="用于验证产品查询 smoke 的事件详情。",
                detail_body=rich_detail_body(),
                why_it_matters="它验证产品接口层可以读取已发布事件。",
                follow_up_points=["继续验证 PostgreSQL"],
                source_refs=[{"title": "HN discussion", "url": "https://news.ycombinator.com/item?id=product-smoke"}],
            ),
        )
        event_service.save_review_result(
            dossier.id,
            ReviewResultDraft(
                decision="publish",
                risk_level="low",
                checked_items={"source_supported": True},
            ),
        )
        event_service.publish_dossier(
            PublishEventCommand(candidate_id=candidate.id, dossier_id=dossier.id, publish_mode="auto")
        )
        manual_candidate = event_service.create_candidate_with_signals(
            EventCandidateDraft(
                candidate_key="product-query-manual",
                title="Product Query Manual 事件",
                category="模型与产品",
                heat_score=60,
                importance_score=60,
                audience_value_score=60,
                ranking_score=60,
                ranking_reason="用于人工审核队列 smoke。",
            ),
            signal_ids=[signal.id],
            merge_reason="产品查询 manual smoke。",
        )
        manual_dossier = event_service.save_dossier(
            manual_candidate.id,
            EventDossierDraft(
                candidate_key="product-query-manual",
                card_title="Product Query Manual 事件",
                card_summary="用于验证人工审核队列。",
                category="模型与产品",
                signal_label="待人工确认",
                detail_title="Product Query Manual 事件",
                detail_summary="用于验证人工审核队列。",
                detail_body=rich_detail_body(),
                why_it_matters="它验证产品接口层可以读取人工审核队列。",
                follow_up_points=["人工确认"],
                source_refs=[{"title": "HN discussion", "url": "https://news.ycombinator.com/item?id=manual"}],
            ),
        )
        event_service.save_review_result(
            manual_dossier.id,
            ReviewResultDraft(
                decision="manual_review",
                risk_level="medium",
                issues=["需要人工确认"],
                revision_instructions="请人工复核。",
                checked_items={"source_supported": True},
            ),
        )
        run_service = RunLogService(session)
        run = run_service.start_pipeline_run(
            PipelineRunCreate(
                run_key="product-query-smoke-run",
                trigger_type="manual",
                source_scope={"sources": ["hn_algolia"]},
            )
        )
        run.published_count = 1
        run_service.record_agent_run(
            AgentRunRecord(
                pipeline_run_id=run.id,
                agent_name="research_writer_llm",
                agent_role="writer",
                input_summary="1 candidate",
                output_json={"detail_title": "Product Query Smoke 事件"},
                trace_json={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
                status="succeeded",
                duration_ms=100,
            )
        )
        run_service.finish_pipeline_run(run.id, status="succeeded", summary="product query smoke")
        session.commit()


def test_smoke_product_queries_reads_existing_database_without_leaking_url(tmp_path):
    """验证产品查询 smoke 脚本只读已有数据库并输出摘要。

    输入：已种好数据的临时 SQLite 数据库。
    输出：脚本返回 0，stdout JSON 包含各核心查询计数且不包含 database_url。
    """
    db_path = tmp_path / "product_queries.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path}"
    seed_product_query_smoke_database(database_url)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/smoke_product_queries.py",
            "--database-url",
            database_url,
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "succeeded"
    assert summary["events_count"] == 1
    assert summary["detail_found"] is True
    assert summary["pipeline_runs_count"] == 1
    assert summary["agent_runs_count"] == 1
    assert summary["review_queue_count"] == 1
    assert "database_url" not in summary

from __future__ import annotations

import warnings

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")
    from fastapi.testclient import TestClient

from worker.api.app import create_app
from worker.models import Base
from worker.schemas.event import EventCandidateDraft, EventDossierDraft, PublishEventCommand, ReviewResultDraft
from worker.schemas.run import AgentRunRecord, PipelineRunCreate
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.event_service import EventService
from worker.services.run_log_service import RunLogService
from worker.services.signal_service import SignalService


def make_session_factory():
    """创建 FastAPI 测试用 SQLite Session 工厂。

    输入：无。
    输出：可跨 TestClient 请求复用同一内存库的 sessionmaker。
    """
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def rich_detail_body(topic: str) -> str:
    """构造 API 测试用详情正文。

    输入：正文主题。
    输出：符合 EventDossierDraft 最低信息密度要求的五段正文。
    """
    return (
        f"{topic} 的讨论集中在 AI 工具是否正在改变开发者日常工作。"
        "这类变化不仅影响单个工具的使用体验，也会影响团队如何拆解需求、生成代码、修复问题和安排上线节奏。\n\n"
        "开发者社区关注的重点通常包括能力边界、上下文理解、稳定性、价格、隐私和代码质量。"
        "这些问题会决定工具能否进入真实项目，而不是只停留在短期试用或社交媒体讨论中。\n\n"
        "从产品角度看，用户点进详情页时需要看到事件本身的背景和关键变化。"
        "正文应该解释事情为什么被讨论、讨论集中在哪里、可能影响哪些开发流程，而不是复述内部排序指标。\n\n"
        "不同观点也应该被放在同一事件档案里。乐观观点强调效率和小团队能力放大，谨慎观点则提醒上下文缺失、调试成本和安全责任仍需要人类工程师判断。\n\n"
        "后续值得观察的是官方文档、开发者实测、价格政策和企业接入情况。"
        "如果这些条件逐渐稳定，这类工具就可能从热点话题变成软件团队日常流程的一部分。"
        "接口层需要稳定读取这一发布快照，保证前端看到的是已发布版本。"
        "在后台生产链路已经完成之后，产品接口层的责任是把这些整理好的内容可靠地交给页面。"
        "它不应该重新判断事件，也不应该触发新的 Agent，只需要按发布快照呈现给用户。"
        "后台审计和前台展示都依赖这种稳定边界：生产链路负责生成，查询服务负责读取，HTTP 接口负责转换成 JSON。"
        "当这三个职责分开后，后续前端页面、后台列表和运行记录都可以围绕同一套数据契约迭代。"
    )


def seed_signal(session, key: str):
    """写入 API 测试用 SourceSignal。

    输入：测试 Session 和业务 key。
    输出：已 flush 的 SourceSignal ORM 对象。
    """
    signal_service = SignalService(session)
    signal_service.upsert_source(
        SourceCreate(
            source_key="hn_algolia",
            name="Hacker News Algolia",
            source_type="community",
            fetch_method="api",
        )
    )
    return signal_service.upsert_signal(
        SourceSignalCreate(
            source_key="hn_algolia",
            source_item_id=key,
            original_title=f"OpenAI Agent API test {key}",
            original_url=f"https://news.ycombinator.com/item?id={key}",
            source_hash=f"hn_algolia:{key}",
        )
    )


def create_published_event(session, candidate_key: str = "openai-agent-api"):
    """创建 API 测试用已发布事件。

    输入：测试 Session 和 candidate_key。
    输出：已 flush 的 PublishedEvent ORM 对象。
    """
    signal = seed_signal(session, candidate_key)
    event_service = EventService(session)
    candidate = event_service.create_candidate_with_signals(
        EventCandidateDraft(
            candidate_key=candidate_key,
            title="OpenAI Agent API 事件",
            category="模型与产品",
            heat_score=80,
            importance_score=78,
            audience_value_score=82,
            ranking_score=85,
            ranking_reason="开发者社区讨论热度较高。",
        ),
        signal_ids=[signal.id],
        merge_reason="API 测试事件。",
    )
    dossier = event_service.save_dossier(
        candidate.id,
        EventDossierDraft(
            candidate_key=candidate_key,
            card_title="OpenAI Agent API 事件",
            card_summary="开发者关注 AI Agent 对日常工作流的影响。",
            category="模型与产品",
            signal_label="高热讨论",
            detail_title="OpenAI Agent API 事件",
            detail_summary="这次讨论集中在 AI Agent 对开发者工作流的影响。",
            detail_body=rich_detail_body("OpenAI Agent API 事件"),
            why_it_matters="它帮助中文用户理解海外开发者正在如何讨论 AI 编程工具。",
            follow_up_points=["观察开发者实测", "观察工具接入成本"],
            source_refs=[{"title": "HN discussion", "url": "https://news.ycombinator.com/item?id=api"}],
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
    return event_service.publish_dossier(
        PublishEventCommand(candidate_id=candidate.id, dossier_id=dossier.id, publish_mode="auto")
    )


def create_manual_review_item(session):
    """创建 API 测试用人工审核事件。

    输入：测试 Session。
    输出：manual_review 状态的候选事件。
    """
    signal = seed_signal(session, "manual-api")
    event_service = EventService(session)
    candidate = event_service.create_candidate_with_signals(
        EventCandidateDraft(
            candidate_key="manual-api",
            title="需要人工审核的 Agent 事件",
            category="模型与产品",
            heat_score=70,
            importance_score=70,
            audience_value_score=70,
            ranking_score=70,
            ranking_reason="需要人工确认来源边界。",
        ),
        signal_ids=[signal.id],
        merge_reason="API 测试人工审核。",
    )
    dossier = event_service.save_dossier(
        candidate.id,
        EventDossierDraft(
            candidate_key="manual-api",
            card_title="需要人工审核的 Agent 事件",
            card_summary="需要人工确认表达边界。",
            category="模型与产品",
            signal_label="待人工确认",
            detail_title="需要人工审核的 Agent 事件",
            detail_summary="这条事件需要人工确认。",
            detail_body=rich_detail_body("人工审核 API 事件"),
            why_it_matters="需要人工判断后再决定是否发布。",
            follow_up_points=["人工确认来源边界"],
            source_refs=[{"title": "HN discussion", "url": "https://news.ycombinator.com/item?id=manual"}],
        ),
    )
    event_service.save_review_result(
        dossier.id,
        ReviewResultDraft(
            decision="manual_review",
            risk_level="medium",
            issues=["需要人工确认来源边界"],
            revision_instructions="请人工复核。",
            checked_items={"source_supported": True},
        ),
    )
    return candidate


def test_public_event_api_returns_events_detail_and_404():
    """验证前台只读事件 API。

    输入：一条已发布事件。
    输出：health、事件列表、事件详情可读，缺失 slug 返回 404。
    """
    session_factory = make_session_factory()
    with session_factory() as session:
        published = create_published_event(session)
        session.commit()

    client = TestClient(create_app(session_factory=session_factory))

    assert client.get("/health").json() == {"status": "ok"}

    events_response = client.get("/events")
    assert events_response.status_code == 200
    events_payload = events_response.json()
    assert events_payload["limit"] == 20
    assert events_payload["offset"] == 0
    assert events_payload["items"][0]["slug"] == published.slug
    assert events_payload["items"][0]["title"] == "OpenAI Agent API 事件"
    assert "ranking_score" not in events_payload["items"][0]

    detail_response = client.get(f"/events/{published.slug}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["id"] == published.id
    assert detail_payload["why_it_matters"] == "它帮助中文用户理解海外开发者正在如何讨论 AI 编程工具。"

    missing_response = client.get("/events/not-found")
    assert missing_response.status_code == 404


def test_admin_read_only_api_returns_runs_agent_runs_and_review_queue():
    """验证后台只读审计 API。

    输入：一次 pipeline run、一条 agent run 和一条 manual_review 事件。
    输出：后台接口可读，agent run 响应隐藏完整 raw trace。
    """
    session_factory = make_session_factory()
    with session_factory() as session:
        create_manual_review_item(session)
        run_service = RunLogService(session)
        run = run_service.start_pipeline_run(
            PipelineRunCreate(
                run_key="manual-api-run",
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
                output_json={"detail_title": "OpenAI Agent API 事件"},
                trace_json={
                    "llm_raw_text": "完整模型原文不应暴露",
                    "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
                status="succeeded",
                duration_ms=321,
            )
        )
        run_service.finish_pipeline_run(run.id, status="succeeded", summary="published 1 event")
        session.commit()

    client = TestClient(create_app(session_factory=session_factory))

    runs_response = client.get("/admin/pipeline-runs")
    assert runs_response.status_code == 200
    runs_payload = runs_response.json()
    assert runs_payload["items"][0]["id"] == run.id
    assert runs_payload["items"][0]["published_count"] == 1

    run_response = client.get(f"/admin/pipeline-runs/{run.id}")
    assert run_response.status_code == 200
    assert run_response.json()["summary"] == "published 1 event"

    agent_runs_response = client.get(f"/admin/pipeline-runs/{run.id}/agent-runs")
    assert agent_runs_response.status_code == 200
    agent_run_payload = agent_runs_response.json()["items"][0]
    assert agent_run_payload["token_usage"] == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert "llm_raw_text" not in agent_run_payload
    assert "trace_json" not in agent_run_payload

    review_queue_response = client.get("/admin/review-queue")
    assert review_queue_response.status_code == 200
    review_queue_payload = review_queue_response.json()
    assert review_queue_payload["items"][0]["title"] == "需要人工审核的 Agent 事件"
    assert review_queue_payload["items"][0]["issues"] == ["需要人工确认来源边界"]

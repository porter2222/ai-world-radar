from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from worker.models import Base, EventDossier, PublishedEvent
from worker.schemas.event import EventCandidateDraft, EventDossierDraft, PublishEventCommand, ReviewResultDraft
from worker.schemas.run import AgentRunRecord, PipelineRunCreate
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.event_service import EventService
from worker.services.product_query_service import ProductQueryService
from worker.services.run_log_service import RunLogService
from worker.services.signal_service import SignalService


def make_session():
    """创建产品查询服务测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 `autoflush=False` 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def rich_detail_body(topic: str = "OpenAI Agent") -> str:
    """构造符合详情正文质量要求的测试正文。

    输入：用于区分正文版本的主题。
    输出：至少五段、长度达标且不含后台流程词的详情正文。
    """
    return (
        f"{topic} 的讨论首先集中在它会不会改变开发者完成日常工作的方式。"
        "这类事件的价值不只在于单个工具是否好用，更在于它可能改变需求拆解、代码生成、测试修复和交付协作的节奏。\n\n"
        "对开发者社区来说，新的编码 Agent 往往意味着工作流重新分配。"
        "一部分任务会被交给模型处理，工程师则需要更多关注边界、架构判断、代码审查和上线风险，这会影响团队内部的协作方式。\n\n"
        "讨论中也会出现不同立场。乐观者关注效率提升、重复劳动减少和小团队能力放大；谨慎者则担心上下文理解不足、调试成本增加、代码质量不稳定和安全责任不清晰。\n\n"
        "中文用户需要看到的是这件事本身的变化，而不是只看到一个产品名或一条链接。"
        "如果海外开发者已经围绕它展开集中讨论，就说明它可能正在影响真实的软件开发实践，需要被整理成更容易理解的事件档案。\n\n"
        "后续值得继续观察的是工具能力是否稳定、价格是否可接受、企业环境是否容易接入，以及开发者是否会把它长期放进日常流程。"
        "这些进展会决定它只是一次短期热议，还是会成为 AI 编程工具链中的稳定组成部分。"
        "如果更多团队开始把这类工具放入真实项目，它还会影响招聘、协作规范和代码交付标准。"
        "这也是产品接口层需要稳定展示详情正文的原因：用户点开事件后，看到的应该是完整背景、讨论焦点和后续观察方向。"
    )


def seed_signal(session, source_item_id: str = "123"):
    """写入产品查询测试用来源信号。

    输入：测试 Session 和来源 item id。
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
            source_item_id=source_item_id,
            original_title=f"OpenAI coding agents discussion {source_item_id}",
            original_url=f"https://news.ycombinator.com/item?id={source_item_id}",
            source_hash=f"hn_algolia:{source_item_id}",
        )
    )


def create_reviewed_dossier(
    session,
    *,
    candidate_key: str,
    title: str,
    decision: str = "publish",
    body_topic: str = "OpenAI Agent",
) -> dict[str, object]:
    """创建候选事件、dossier 和审稿结果。

    输入：测试 Session、candidate_key、标题、审稿 decision 和正文主题。
    输出：包含 candidate、dossier、review 的测试辅助字典。
    """
    signal = seed_signal(session, candidate_key)
    event_service = EventService(session)
    candidate = event_service.create_candidate_with_signals(
        EventCandidateDraft(
            candidate_key=candidate_key,
            title=title,
            category="模型与产品",
            heat_score=82,
            importance_score=80,
            audience_value_score=78,
            ranking_score=85,
            ranking_reason="开发者社区讨论热度较高。",
        ),
        signal_ids=[signal.id],
        merge_reason="测试产品查询服务。",
    )
    dossier = event_service.save_dossier(
        candidate.id,
        EventDossierDraft(
            candidate_key=candidate_key,
            card_title=title,
            card_summary=f"{title}，开发者关注其工作流影响。",
            category="模型与产品",
            signal_label="高热讨论",
            cover_image_url=None,
            detail_title=title,
            detail_summary=f"{title} 的讨论集中在开发者工作流变化。",
            detail_body=rich_detail_body(body_topic),
            why_it_matters=f"{title} 可能影响中文开发者理解海外 AI 工具链变化。",
            follow_up_points=["观察开发者长期使用反馈", "观察官方文档和价格变化"],
            source_refs=[
                {
                    "title": "HN discussion",
                    "url": f"https://news.ycombinator.com/item?id={candidate_key}",
                }
            ],
        ),
    )
    review = event_service.save_review_result(
        dossier.id,
        ReviewResultDraft(
            decision=decision,
            risk_level="low" if decision == "publish" else "medium",
            issues=[] if decision == "publish" else ["需要人工确认"],
            revision_instructions="" if decision == "publish" else "请人工确认表达边界。",
            checked_items={"source_supported": True},
        ),
    )
    return {"candidate": candidate, "dossier": dossier, "review": review}


def publish_reviewed_dossier(session, reviewed: dict[str, object]) -> PublishedEvent:
    """发布已通过审稿的测试 dossier。

    输入：测试 Session 和 create_reviewed_dossier 返回的字典。
    输出：已 flush 的 PublishedEvent ORM 对象。
    """
    event_service = EventService(session)
    return event_service.publish_dossier(
        PublishEventCommand(
            candidate_id=reviewed["candidate"].id,
            dossier_id=reviewed["dossier"].id,
            publish_mode="auto",
        )
    )


def test_list_published_events_returns_public_cards_sorted_and_filtered():
    """验证首页事件列表只返回 published 事件，按产品排序，且不暴露内部评分。

    输入：两条 published 事件和一条 hidden 事件。
    输出：列表只包含 published 事件，homepage_rank 更靠前的事件排在前面。
    """
    session = make_session()
    first = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="openai-agent-a",
            title="OpenAI Agent A 引发讨论",
        ),
    )
    second = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="openai-agent-b",
            title="OpenAI Agent B 引发讨论",
        ),
    )
    hidden = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="openai-agent-hidden",
            title="隐藏事件不应出现在前台",
        ),
    )
    first.homepage_rank = 2
    first.published_at = datetime(2026, 6, 20, tzinfo=UTC)
    second.homepage_rank = 1
    second.published_at = datetime(2026, 6, 21, tzinfo=UTC)
    hidden.status = "hidden"
    session.flush()

    service = ProductQueryService(session)
    items = service.list_published_events(limit=10, offset=0)
    dumped = [item.model_dump() for item in items]

    assert [item.slug for item in items] == [second.slug, first.slug]
    assert dumped[0]["title"] == "OpenAI Agent B 引发讨论"
    assert dumped[0]["card_summary"] == "OpenAI Agent B 引发讨论，开发者关注其工作流影响。"
    assert all("ranking_score" not in item for item in dumped)
    assert hidden.slug not in [item.slug for item in items]


def test_get_event_by_slug_returns_published_snapshot_dossier_version():
    """验证详情页按 slug 读取发布快照绑定的 dossier 版本。

    输入：一个已发布事件，以及同 candidate 后续新增的一版草稿 dossier。
    输出：详情仍读取 PublishedEvent.dossier_id 指向的发布时版本，不取最新草稿。
    """
    session = make_session()
    reviewed = create_reviewed_dossier(
        session,
        candidate_key="openai-agent-detail",
        title="OpenAI Agent 详情页事件",
        body_topic="发布时正文",
    )
    published = publish_reviewed_dossier(session, reviewed)
    EventService(session).save_dossier(
        reviewed["candidate"].id,
        EventDossierDraft(
            candidate_key="openai-agent-detail",
            card_title="OpenAI Agent 详情页事件新草稿",
            card_summary="这是一版不应被详情接口误读的新草稿。",
            category="模型与产品",
            signal_label="高热讨论",
            detail_title="OpenAI Agent 详情页事件新草稿",
            detail_summary="不应被发布详情读取。",
            detail_body=rich_detail_body("未发布草稿"),
            why_it_matters="未发布草稿的 why_it_matters 不应出现在详情接口。",
            follow_up_points=["未发布草稿跟进点"],
            source_refs=[{"title": "Draft source", "url": "https://example.com/draft"}],
        ),
    )

    service = ProductQueryService(session)
    detail = service.get_event_by_slug(published.slug)

    assert detail is not None
    assert detail.id == published.id
    assert "发布时正文" in detail.detail_body
    assert "未发布草稿" not in detail.detail_body
    assert detail.why_it_matters == "OpenAI Agent 详情页事件 可能影响中文开发者理解海外 AI 工具链变化。"
    assert service.get_event_by_slug("missing-slug") is None


def test_pipeline_run_and_agent_run_queries_redact_raw_llm_text():
    """验证后台审计查询能返回运行摘要，并隐藏完整 LLM 原文。

    输入：一条 pipeline run 和一条带 llm_raw_text/token_usage 的 agent run。
    输出：查询结果包含 token_usage，但不暴露 llm_raw_text。
    """
    session = make_session()
    run_service = RunLogService(session)
    run = run_service.start_pipeline_run(
        PipelineRunCreate(
            run_key="manual-20260622-product-query",
            trigger_type="manual",
            source_scope={"sources": ["hn_algolia"]},
        )
    )
    run.signals_count = 1
    run.candidates_count = 1
    run.dossiers_count = 1
    run.published_count = 1
    agent_run = run_service.record_agent_run(
        AgentRunRecord(
            pipeline_run_id=run.id,
            candidate_id="cand_demo",
            dossier_id="dos_demo",
            agent_name="research_writer_llm",
            agent_role="writer",
            model_provider="openai",
            model_name="gpt-5.5",
            prompt_version="p1-4-writer-v1",
            input_summary="1 candidate",
            output_json={"detail_title": "OpenAI Agent 详情"},
            trace_json={
                "llm_raw_text": "完整模型原文不应出现在产品接口",
                "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
            status="succeeded",
            duration_ms=1234,
            retry_count=1,
        )
    )
    run_service.finish_pipeline_run(run.id, status="succeeded", summary="published 1 event")

    service = ProductQueryService(session)
    run_summary = service.get_pipeline_run(run.id)
    agent_runs = service.list_agent_runs(run.id)
    dumped = agent_runs[0].model_dump()

    assert run_summary is not None
    assert run_summary.id == run.id
    assert run_summary.published_count == 1
    assert agent_runs[0].id == agent_run.id
    assert dumped["token_usage"] == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert "llm_raw_text" not in dumped
    assert "trace_json" not in dumped


def test_manual_review_queue_returns_latest_item_per_candidate():
    """验证人工审核队列只返回当前 manual_review 的最新 dossier/review。

    输入：同一 candidate 两版 manual_review dossier，以及一个 rejected candidate。
    输出：队列只返回 manual_review candidate，且使用最新 dossier version。
    """
    session = make_session()
    reviewed = create_reviewed_dossier(
        session,
        candidate_key="openai-agent-manual",
        title="OpenAI Agent 人工审核事件",
        decision="manual_review",
        body_topic="人工审核第一版",
    )
    latest_dossier = EventService(session).save_dossier(
        reviewed["candidate"].id,
        EventDossierDraft(
            candidate_key="openai-agent-manual",
            card_title="OpenAI Agent 人工审核事件第二版",
            card_summary="第二版人工审核内容。",
            category="模型与产品",
            signal_label="待人工确认",
            detail_title="OpenAI Agent 人工审核事件第二版",
            detail_summary="需要人工确认表达边界。",
            detail_body=rich_detail_body("人工审核第二版"),
            why_it_matters="第二版 why_it_matters 应展示在人工审核队列。",
            follow_up_points=["人工确认来源边界"],
            source_refs=[{"title": "HN discussion", "url": "https://news.ycombinator.com/item?id=manual"}],
        ),
    )
    latest_review = EventService(session).save_review_result(
        latest_dossier.id,
        ReviewResultDraft(
            decision="manual_review",
            risk_level="medium",
            issues=["需要人工确认来源边界"],
            revision_instructions="请人工确认。",
            checked_items={"source_supported": True},
        ),
    )
    create_reviewed_dossier(
        session,
        candidate_key="openai-agent-rejected",
        title="OpenAI Agent 已拒绝事件",
        decision="reject",
        body_topic="已拒绝事件",
    )

    service = ProductQueryService(session)
    queue = service.list_manual_review_items(limit=10, offset=0)

    assert len(queue) == 1
    assert queue[0].candidate_id == reviewed["candidate"].id
    assert queue[0].dossier_id == latest_dossier.id
    assert queue[0].review_id == latest_review.id
    assert queue[0].dossier_version == 2
    assert queue[0].issues == ["需要人工确认来源边界"]

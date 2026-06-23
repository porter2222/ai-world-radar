from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


def test_list_published_events_defaults_to_recent_48_hour_window():
    """验证首页列表默认优先使用最近 48 小时时效窗口。

    输入：8 条 48 小时内事件和 1 条 72 小时前事件。
    输出：窗口内事件出现在列表，超过 48 小时的事件不出现在默认首页列表。
    """
    session = make_session()
    now = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)
    recent_events = []
    for index in range(8):
        published = publish_reviewed_dossier(
            session,
            create_reviewed_dossier(
                session,
                candidate_key=f"recent-ai-event-{index}",
                title=f"最近 AI 事件 {index}",
            ),
        )
        published.published_at = now - timedelta(hours=2 + index)
        recent_events.append(published)
    old = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="old-ai-event",
            title="过期 AI 事件",
        ),
    )
    old.published_at = now - timedelta(hours=72)
    session.commit()

    service = ProductQueryService(session)
    items = service.list_published_events(limit=20, offset=0, now=now)
    slugs = [item.slug for item in items]

    assert all(event.slug in slugs for event in recent_events)
    assert old.slug not in slugs


def test_list_published_events_backfills_to_7_days_when_recent_count_is_low():
    """验证 48 小时内事件不足时首页会向 7 天窗口兜底。

    输入：1 条 48 小时内事件、1 条 3 天前事件和 1 条 9 天前事件。
    输出：3 天前事件进入兜底列表，9 天前事件仍不进入首页列表。
    """
    session = make_session()
    now = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)
    recent = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="recent-backfill-ai-event",
            title="最近兜底 AI 事件",
        ),
    )
    recent.published_at = now - timedelta(hours=3)
    backfill = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="backfill-ai-event",
            title="兜底 AI 事件",
        ),
    )
    backfill.published_at = now - timedelta(days=3)
    too_old = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="too-old-ai-event",
            title="超出兜底窗口 AI 事件",
        ),
    )
    too_old.published_at = now - timedelta(days=9)
    session.commit()

    service = ProductQueryService(session)
    items = service.list_published_events(limit=20, offset=0, now=now)
    slugs = [item.slug for item in items]

    assert recent.slug in slugs
    assert backfill.slug in slugs
    assert too_old.slug not in slugs


def test_get_event_by_slug_still_returns_old_published_event():
    """验证详情页不受首页时效窗口影响。

    输入：一条 9 天前已发布事件。
    输出：`get_event_by_slug()` 仍能读取该老事件详情。
    """
    session = make_session()
    now = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)
    old = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="old-detail-event",
            title="老详情 AI 事件",
        ),
    )
    old.published_at = now - timedelta(days=9)
    session.commit()

    service = ProductQueryService(session)
    detail = service.get_event_by_slug(old.slug)

    assert detail is not None
    assert detail.slug == old.slug


def test_list_published_events_applies_category_filter_with_recent_window():
    """验证分类过滤和首页时效窗口同时生效。

    输入：同一 48 小时窗口内的模型类事件和开源类事件，以及 3 天前的模型类事件。
    输出：按模型分类查询时只返回窗口内模型类事件，不返回其他分类或过期模型类事件。
    """
    session = make_session()
    now = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)
    model_event = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="recent-model-event",
            title="近期模型事件",
        ),
    )
    model_event.category = "模型与产品"
    model_event.published_at = now - timedelta(hours=5)
    open_source_event = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="recent-open-source-event",
            title="近期开源事件",
        ),
    )
    open_source_event.category = "开源项目"
    open_source_event.published_at = now - timedelta(hours=4)
    old_model_event = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="old-model-event",
            title="过期模型事件",
        ),
    )
    old_model_event.category = "模型与产品"
    old_model_event.published_at = now - timedelta(days=3)
    session.commit()

    service = ProductQueryService(session)
    items = service.list_published_events(
        limit=20,
        offset=0,
        category="模型与产品",
        now=now,
        min_recent_items=0,
    )
    slugs = [item.slug for item in items]

    assert model_event.slug in slugs
    assert open_source_event.slug not in slugs
    assert old_model_event.slug not in slugs


def test_list_published_events_returns_single_line_source_hint_with_deduped_platform_count():
    """验证首页列表返回轻量单行来源提示，并按平台去重计数。

    输入：一条已发布事件，source_refs 包含两个 HN 链接和一个 GitHub 链接。
    输出：列表项返回短来源提示 `Hacker News 等 2 源`，不返回完整 source_refs 或内部评分字段。
    """
    session = make_session()
    published = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="multi-source-event",
            title="多来源事件",
        ),
    )
    published.source_refs = [
        {
            "title": "A long HN post title should not appear in source hint",
            "url": "https://news.ycombinator.com/item?id=111",
            "source_key": "hn_algolia",
        },
        {
            "title": "Another HN discussion",
            "url": "https://news.ycombinator.com/item?id=222",
            "source_key": "hn_algolia",
        },
        {
            "title": "GitHub repository",
            "url": "https://github.com/openai/openai-python",
            "source_key": "github_repo_trends",
        },
    ]
    session.flush()

    service = ProductQueryService(session)
    dumped = service.list_published_events(limit=10, offset=0)[0].model_dump()

    assert dumped["source_hint"] == "Hacker News 等 2 源"
    assert dumped["source_count"] == 2
    assert "source_refs" not in dumped
    assert "ranking_score" not in dumped
    assert "heat_score" not in dumped
    assert "importance_score" not in dumped


def test_list_published_events_returns_single_source_hint_and_empty_source_state():
    """验证单来源和无来源时的首页来源提示。

    输入：一条 GitHub 单来源事件，以及一条 source_refs 为空的发布事件。
    输出：单来源返回平台名和计数 1；无来源返回 None 和计数 0。
    """
    session = make_session()
    github_event = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="single-github-source",
            title="GitHub 单来源事件",
        ),
    )
    github_event.source_refs = [
        {
            "title": "Release notes title should not be used first",
            "url": "https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.0.0",
            "source_key": "github_releases",
        }
    ]
    empty_source_event = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(
            session,
            candidate_key="empty-source-event",
            title="无来源提示事件",
        ),
    )
    empty_source_event.source_refs = []
    session.flush()

    service = ProductQueryService(session)
    dumped_by_slug = {item.slug: item.model_dump() for item in service.list_published_events(limit=10, offset=0)}

    assert dumped_by_slug[github_event.slug]["source_hint"] == "GitHub Release"
    assert dumped_by_slug[github_event.slug]["source_count"] == 1
    assert dumped_by_slug[empty_source_event.slug]["source_hint"] is None
    assert dumped_by_slug[empty_source_event.slug]["source_count"] == 0


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

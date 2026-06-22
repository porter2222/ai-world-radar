import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from worker.models import Base, PublishedEvent
from worker.schemas.event import EventCandidateDraft, EventDossierDraft, PublishEventCommand, ReviewResultDraft
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.event_service import EventService
from worker.services.signal_service import SignalService


def make_session():
    """创建事件服务测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 `autoflush=False` 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def seed_signal(session):
    """写入一条候选事件可引用的来源信号。

    输入：测试 Session。
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
            source_item_id="123",
            original_title="OpenAI model discussion",
            original_url="https://example.com/openai",
            source_hash="hn_algolia:123",
        )
    )


def rich_detail_body() -> str:
    """构造事件服务测试用高信息密度详情正文。

    输入：无。
    输出：符合 EventDossierDraft 最低详情质量要求的正文。
    """
    return (
        "OpenAI 新模型能力和开发者工具链的讨论，核心在于模型更新是否会改变应用开发方式。"
        "开发者关注的不只是一次功能变化，而是它会不会影响 API 调用、成本评估、产品设计和现有工具链迁移。\n\n"
        "讨论的触发点通常来自模型能力、API 使用方式、价格结构或工具集成变化。"
        "对开发者来说，这些变化会影响选型、成本评估、产品路线和现有工具链迁移，因此需要被解释成可理解的具体变化。\n\n"
        "社区关注的焦点不只是模型强不强，还包括调用是否稳定、是否方便集成、是否会改变已有应用架构，以及是否会让小团队获得更强的开发能力。"
        "这些讨论能帮助中文用户看到海外开发者真实关心的问题，也能避免只根据标题判断一个工具是否值得跟进。\n\n"
        "不同观点也需要并置呈现：乐观者会关注效率提升和新产品机会，谨慎者会关注成本、可靠性、隐私和供应商锁定。"
        "详情正文应把这些分歧写出来，而不是只给一句笼统结论，这样读者才能理解事件背后的实际取舍。\n\n"
        "后续更值得观察的是官方文档、API 说明、开发者实测和价格变动。"
        "如果这些变化能稳定落到真实项目里，它会影响团队选择模型、安排预算和规划产品能力的方式。"
        "它也会让产品团队重新考虑哪些能力应该自己实现，哪些能力可以交给底层模型和工具链承担。"
    )


def test_candidate_dossier_review_and_publish_flow_is_idempotent():
    """验证候选事件、档案、审稿和发布快照的完整服务流。

    输入：一条 SourceSignal、一个候选事件草案、一个 dossier 草案和 publish 审稿结果。
    输出：候选事件发布成功，重复发布返回同一个 PublishedEvent。
    """
    session = make_session()
    signal = seed_signal(session)
    service = EventService(session)

    candidate = service.create_candidate_with_signals(
        EventCandidateDraft(
            candidate_key="openai-new-model",
            title="OpenAI 新模型引发开发者讨论",
            category="模型与产品",
            heat_score=82,
            importance_score=90,
            audience_value_score=76,
            ranking_score=85,
            ranking_reason="HN 热度较高，且来自重要 AI 公司相关消息。",
        ),
        signal_ids=[signal.id],
        merge_reason="同一 HN story 指向同一事件。",
    )
    dossier = service.save_dossier(
        candidate.id,
        EventDossierDraft(
            candidate_key="openai-new-model",
            card_title="OpenAI 新模型引发开发者讨论",
            card_summary="开发者关注其能力、价格和工具链影响。",
            category="模型与产品",
            signal_label="高热讨论",
            detail_title="OpenAI 新模型为什么引发开发者关注",
            detail_summary="这次讨论集中在模型能力、调用成本和开发者工具集成。",
            detail_body=rich_detail_body(),
            why_it_matters="它可能影响 AI 编程工具和应用开发成本。",
            follow_up_points=["是否开放 API"],
            source_refs=[{"title": "HN discussion", "url": "https://news.ycombinator.com/item?id=123"}],
        ),
    )
    review = service.save_review_result(
        dossier.id,
        ReviewResultDraft(
            decision="publish",
            risk_level="low",
            issues=[],
            revision_instructions="",
            checked_items={"has_sources": True},
        ),
    )
    first_publish = service.publish_dossier(
        PublishEventCommand(candidate_id=candidate.id, dossier_id=dossier.id, publish_mode="auto")
    )
    second_publish = service.publish_dossier(
        PublishEventCommand(candidate_id=candidate.id, dossier_id=dossier.id, publish_mode="auto")
    )

    assert candidate.status == "published"
    assert dossier.status == "published_snapshot"
    assert review.decision == "publish"
    assert first_publish.id == second_publish.id
    assert first_publish.published_title == "OpenAI 新模型为什么引发开发者关注"


@pytest.mark.parametrize(
    ("decision", "expected_candidate_status", "expected_dossier_status"),
    [
        ("revise", "drafting", "needs_revision"),
        ("manual_review", "manual_review", "manual_review"),
        ("reject", "rejected", "rejected"),
    ],
)
def test_non_publish_review_decisions_update_status_without_publishing(
    decision: str,
    expected_candidate_status: str,
    expected_dossier_status: str,
):
    """验证非发布审稿决策只流转状态，不写入发布快照。

    输入：revise、manual_review、reject 三种 ReviewResult.decision。
    输出：候选事件和 dossier 进入对应状态，published_events 保持为空。
    """
    session = make_session()
    signal = seed_signal(session)
    service = EventService(session)
    candidate = service.create_candidate_with_signals(
        EventCandidateDraft(
            candidate_key=f"openai-new-model-{decision}",
            title="OpenAI 新模型引发开发者讨论",
            category="模型与产品",
            heat_score=82,
            importance_score=90,
            audience_value_score=76,
            ranking_score=85,
            ranking_reason="HN 热度较高，且来自重要 AI 公司相关消息。",
        ),
        signal_ids=[signal.id],
        merge_reason="同一 HN story 指向同一事件。",
    )
    dossier = service.save_dossier(
        candidate.id,
        EventDossierDraft(
            candidate_key=candidate.candidate_key,
            card_title="OpenAI 新模型引发开发者讨论",
            card_summary="开发者关注其能力、价格和工具链影响。",
            category="模型与产品",
            signal_label="高热讨论",
            detail_title="OpenAI 新模型为什么引发开发者关注",
            detail_summary="这次讨论集中在模型能力、调用成本和开发者工具集成。",
            detail_body=rich_detail_body(),
            why_it_matters="它可能影响 AI 编程工具和应用开发成本。",
            follow_up_points=["是否开放 API"],
            source_refs=[{"title": "HN discussion", "url": "https://news.ycombinator.com/item?id=123"}],
        ),
    )

    review = service.save_review_result(
        dossier.id,
        ReviewResultDraft(
            decision=decision,
            risk_level="medium",
            issues=["需要人工确认"] if decision != "revise" else ["需要重写"],
            revision_instructions="请按审稿意见处理。",
            checked_items={"has_sources": True},
        ),
    )

    assert review.decision == decision
    assert candidate.status == expected_candidate_status
    assert dossier.status == expected_dossier_status
    assert session.scalars(select(PublishedEvent)).all() == []
    with pytest.raises(ValueError, match="Dossier has no publish review result"):
        service.publish_dossier(
            PublishEventCommand(candidate_id=candidate.id, dossier_id=dossier.id, publish_mode="auto")
        )


def test_slug_collision_adds_candidate_suffix_while_same_candidate_is_idempotent():
    """验证不同候选事件 slug 冲突时追加短后缀，同候选事件重复发布仍幂等。

    输入：两个 candidate_key 归一化后同为 openai-agent 的候选事件。
    输出：第二个发布快照自动追加 candidate ID 后缀，第一个候选事件重复发布仍返回原记录。
    """
    session = make_session()
    signal = seed_signal(session)
    service = EventService(session)

    first_candidate = _create_reviewed_candidate(service, signal.id, "openai-agent")
    first_publish = service.publish_dossier(
        PublishEventCommand(
            candidate_id=first_candidate["candidate"].id,
            dossier_id=first_candidate["dossier"].id,
            publish_mode="auto",
        )
    )
    repeated_publish = service.publish_dossier(
        PublishEventCommand(
            candidate_id=first_candidate["candidate"].id,
            dossier_id=first_candidate["dossier"].id,
            publish_mode="auto",
        )
    )
    second_candidate = _create_reviewed_candidate(service, signal.id, "openai agent")
    second_publish = service.publish_dossier(
        PublishEventCommand(
            candidate_id=second_candidate["candidate"].id,
            dossier_id=second_candidate["dossier"].id,
            publish_mode="auto",
        )
    )

    assert repeated_publish.id == first_publish.id
    assert first_publish.slug == "openai-agent"
    assert second_publish.slug == f"openai-agent-{second_candidate['candidate'].id[-8:]}"
    assert first_publish.slug != second_publish.slug


def _create_reviewed_candidate(service: EventService, signal_id: str, candidate_key: str) -> dict[str, object]:
    """创建一条已通过审稿但尚未发布的候选事件。

    输入：EventService、SourceSignal ID 和 candidate_key。
    输出：包含 candidate 与 dossier 的测试辅助字典。
    """
    candidate = service.create_candidate_with_signals(
        EventCandidateDraft(
            candidate_key=candidate_key,
            title="OpenAI Agent 引发开发者讨论",
            category="模型与产品",
            heat_score=82,
            importance_score=90,
            audience_value_score=76,
            ranking_score=85,
            ranking_reason="HN 热度较高，且开发者使用价值明显。",
        ),
        signal_ids=[signal_id],
        merge_reason="测试 slug 冲突。",
    )
    dossier = service.save_dossier(
        candidate.id,
        EventDossierDraft(
            candidate_key=candidate_key,
            card_title="OpenAI Agent 引发关注",
            card_summary="开发者关注其能力、价格和工具链影响。",
            category="模型与产品",
            signal_label="高热讨论",
            detail_title="OpenAI Agent 为什么引发开发者关注",
            detail_summary="这次讨论集中在 Agent 对开发者工具链的影响。",
            detail_body=rich_detail_body(),
            why_it_matters="它可能影响 AI 编程工具和应用开发成本。",
            follow_up_points=["是否开放 API"],
            source_refs=[{"title": "HN discussion", "url": "https://news.ycombinator.com/item?id=123"}],
        ),
    )
    service.save_review_result(
        dossier.id,
        ReviewResultDraft(
            decision="publish",
            risk_level="low",
            issues=[],
            revision_instructions="",
            checked_items={"has_sources": True},
        ),
    )
    return {"candidate": candidate, "dossier": dossier}

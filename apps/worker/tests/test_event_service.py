from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from worker.models import Base
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
        "Hacker News 上出现一则围绕 OpenAI 新模型能力和开发者工具链影响的讨论，来源信号显示它正在被开发者关注。"
        "这类信息适合作为热议型事件处理，因为它反映社区正在讨论什么，而不是直接证明官方已经发布了完整结论。\n\n"
        "讨论的触发点通常来自模型能力、API 使用方式、价格结构或工具集成变化。"
        "对开发者来说，这些变化会影响选型、成本评估、产品路线和现有工具链迁移，因此需要被解释成可理解的事件档案。\n\n"
        "社区关注的焦点不只是模型强不强，还包括调用是否稳定、是否方便集成、是否会改变已有应用架构，以及是否会让小团队获得更强的开发能力。"
        "这些讨论能帮助中文用户看到海外开发者真实关心的问题，也能避免只根据标题判断一个工具是否值得跟进。\n\n"
        "不同观点也需要并置呈现：乐观者会关注效率提升和新产品机会，谨慎者会关注成本、可靠性、隐私和供应商锁定。"
        "详情正文应把这些分歧写出来，而不是只给一句笼统结论，这样 review 时才能判断内容是否真的服务于中文用户理解。\n\n"
        "来源边界同样重要。当前信号只能支撑开发者社区正在讨论，不应写成官方已经确认所有能力、价格或发布时间。"
        "后续应继续观察官方文档、API 说明、开发者实测和价格变动。"
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

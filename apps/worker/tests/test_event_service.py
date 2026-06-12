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
            detail_body="这是一段面向中文用户的事件解释正文，说明背景、变化和可能影响。",
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

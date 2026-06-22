from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from worker.agents.event_pipeline_agents import ResearchWriterAgentStub
from worker.models import AgentRun, Base, EventCandidate, EventDossier, PipelineRun, PublishedEvent, ReviewResult
from worker.schemas.event import EventDossierDraft, ReviewResultDraft
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.signal_service import SignalService
from worker.tools.event_pipeline_tools import EventPipelineTools
from worker.workflows.event_pipeline import run_event_pipeline


def make_session():
    """创建 workflow 测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 autoflush=False 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def seed_signal(session):
    """写入一条 workflow 可消费的来源信号。

    输入：测试 Session。
    输出：SourceSignal ORM 对象。
    """
    service = SignalService(session)
    service.upsert_source(SourceCreate(source_key="demo", name="Demo", source_type="fixture", fetch_method="manual"))
    return service.upsert_signal(
        SourceSignalCreate(
            source_key="demo",
            source_item_id="demo-1",
            original_title="OpenAI releases a new developer tool",
            original_url="https://example.com/openai-tool",
            raw_summary="Developers discuss the new tool.",
            source_hash="demo:1",
            heat_metrics={"points": 120, "comments": 45},
        )
    )


class FixedDecisionReviewer:
    """按预设 decision 返回审稿结果的 workflow 测试 reviewer。

    输入：ReviewResult.decision 队列。
    输出：每次 review 调用返回一个 ReviewResultDraft。
    """

    name = "fixed_decision_reviewer"
    role = "reviewer"

    def __init__(self, decisions: list[str]):
        """初始化 reviewer。

        输入：按调用顺序消费的 decision 列表。
        输出：可注入 EventPipelineTools 的测试 reviewer。
        """
        self.decisions = decisions

    def review(self, dossier: EventDossierDraft, revision_count: int = 0) -> ReviewResultDraft:
        """返回预设审稿结果。

        输入：事件档案草案和当前修订次数。
        输出：ReviewResultDraft，包含可供 writer 使用的修订说明。
        """
        decision = self.decisions.pop(0)
        instructions = "请补充正文中的现实影响和后续观察点。" if decision == "revise" else ""
        return ReviewResultDraft(
            decision=decision,
            risk_level="medium" if decision != "publish" else "low",
            issues=[] if decision == "publish" else ["需要继续处理"],
            revision_instructions=instructions,
            checked_items={"source_supported": True, "revision_count": revision_count},
        )


class AlwaysReviseReviewer:
    """始终返回 revise 的 workflow 测试 reviewer。

    输入：任意 EventDossierDraft。
    输出：固定为 revise 的 ReviewResultDraft，用于验证最大修订深度。
    """

    name = "always_revise_reviewer"
    role = "reviewer"

    def review(self, dossier: EventDossierDraft, revision_count: int = 0) -> ReviewResultDraft:
        """返回 revise 审稿结果。

        输入：事件档案草案和当前修订次数。
        输出：包含修订说明的 ReviewResultDraft。
        """
        return ReviewResultDraft(
            decision="revise",
            risk_level="medium",
            issues=["仍需修订"],
            revision_instructions=f"第 {revision_count + 1} 次审稿要求补充背景和现实影响。",
            checked_items={"source_supported": True, "revision_count": revision_count},
        )


class RecordingWriter(ResearchWriterAgentStub):
    """记录 revision_instructions 的 workflow 测试 writer。

    输入：候选事件、来源信号和修订说明。
    输出：沿用 ResearchWriterAgentStub 的 EventDossierDraft，同时保存每次收到的修订说明。
    """

    def __init__(self):
        """初始化 writer。

        输入：无。
        输出：带 revision_instructions 记录列表的测试 writer。
        """
        self.revision_instructions: list[str] = []

    def draft(self, candidate, signals, revision_instructions: str = ""):
        """记录修订说明并生成事件档案。

        输入：ResearchWriterAgentStub.draft 的原始参数。
        输出：EventDossierDraft。
        """
        self.revision_instructions.append(revision_instructions)
        return super().draft(candidate, signals, revision_instructions)


def test_langgraph_pipeline_publishes_event_and_records_counts():
    """验证 LangGraph 工作流首跑即可发布事件并记录真实计数。

    输入：一条预置 SourceSignal 和 run_key。
    输出：PublishedEvent、PipelineRun、AgentRun 均入库，PipelineRun 计数等于最终表结果。
    """
    session = make_session()
    signal = seed_signal(session)

    state = run_event_pipeline(
        session,
        signal_ids=[signal.id],
        run_key="manual-p1-2-workflow",
        source_scope={"source": "demo"},
    )

    published_count = len(session.scalars(select(PublishedEvent)).all())
    agent_run_count = len(session.scalars(select(AgentRun)).all())
    run = session.scalar(select(PipelineRun))

    assert state.status == "succeeded"
    assert state.published_event_id is not None
    assert published_count == 1
    assert agent_run_count == 3
    assert run.signals_count == 1
    assert run.candidates_count == 1
    assert run.dossiers_count == 1
    assert run.published_count == published_count
    assert run.failed_count == 0


def test_langgraph_pipeline_revises_once_then_publishes():
    """验证 revise 分支会重新生成 dossier 后再发布。

    输入：第一次审稿返回 revise，第二次审稿返回 publish 的 reviewer。
    输出：workflow 成功发布，生成两版 dossier 和两个 review_result，但只写一个 PublishedEvent。
    """
    session = make_session()
    signal = seed_signal(session)
    reviewer = FixedDecisionReviewer(["revise", "publish"])
    tools = EventPipelineTools(session, reviewer=reviewer)

    state = run_event_pipeline(
        session,
        signal_ids=[signal.id],
        run_key="manual-p1-5-revise-then-publish",
        source_scope={"source": "demo"},
        tools=tools,
    )

    dossiers = session.scalars(select(EventDossier).order_by(EventDossier.version)).all()
    reviews = session.scalars(select(ReviewResult).order_by(ReviewResult.created_at)).all()
    published_events = session.scalars(select(PublishedEvent)).all()
    run = session.scalar(select(PipelineRun))

    assert state.status == "succeeded"
    assert state.revision_count == 1
    assert len(dossiers) == 2
    assert [dossier.version for dossier in dossiers] == [1, 2]
    assert [review.decision for review in reviews] == ["revise", "publish"]
    assert dossiers[0].status == "needs_revision"
    assert dossiers[1].status == "published_snapshot"
    assert len(published_events) == 1
    assert run.dossiers_count == 2
    assert run.published_count == 1


def test_langgraph_pipeline_passes_revision_instructions_to_writer():
    """验证 reviewer 的修订意见会传给下一轮 writer。

    输入：第一次审稿 revise、第二次审稿 publish 的 reviewer 和记录型 writer。
    输出：writer 第二次 draft 收到 reviewer 给出的 revision_instructions。
    """
    session = make_session()
    signal = seed_signal(session)
    writer = RecordingWriter()
    reviewer = FixedDecisionReviewer(["revise", "publish"])
    tools = EventPipelineTools(session, writer=writer, reviewer=reviewer)

    state = run_event_pipeline(
        session,
        signal_ids=[signal.id],
        run_key="manual-p1-5-revision-instructions",
        source_scope={"source": "demo"},
        tools=tools,
    )

    assert state.status == "succeeded"
    assert writer.revision_instructions == ["", "请补充正文中的现实影响和后续观察点。"]


def test_langgraph_pipeline_stops_after_max_revision_attempts_without_publishing():
    """验证超过最大修订次数后进入 manual_review 且不发布。

    输入：始终返回 revise 的 reviewer。
    输出：workflow 最多生成三版 dossier，最终进入 manual_review，PublishedEvent 为空。
    """
    session = make_session()
    signal = seed_signal(session)
    writer = RecordingWriter()
    tools = EventPipelineTools(session, writer=writer, reviewer=AlwaysReviseReviewer())

    state = run_event_pipeline(
        session,
        signal_ids=[signal.id],
        run_key="manual-p1-5-max-revisions",
        source_scope={"source": "demo"},
        tools=tools,
    )

    candidate = session.scalar(select(EventCandidate))
    dossiers = session.scalars(select(EventDossier).order_by(EventDossier.version)).all()
    reviews = session.scalars(select(ReviewResult).order_by(ReviewResult.created_at)).all()
    run = session.scalar(select(PipelineRun))

    assert state.status == "manual_review"
    assert state.revision_count == 2
    assert state.published_event_id is None
    assert candidate.status == "manual_review"
    assert len(dossiers) == 3
    assert dossiers[-1].status == "manual_review"
    assert [review.decision for review in reviews] == ["revise", "revise", "revise"]
    assert writer.revision_instructions == [
        "",
        "第 1 次审稿要求补充背景和现实影响。",
        "第 2 次审稿要求补充背景和现实影响。",
    ]
    assert session.scalars(select(PublishedEvent)).all() == []
    assert run.status == "partial_failed"
    assert run.published_count == 0


def test_langgraph_pipeline_manual_review_does_not_publish():
    """验证 manual_review 分支进入人工处理且不发布。

    输入：审稿直接返回 manual_review 的 reviewer。
    输出：candidate 和 dossier 均为 manual_review，PublishedEvent 为空。
    """
    session = make_session()
    signal = seed_signal(session)
    tools = EventPipelineTools(session, reviewer=FixedDecisionReviewer(["manual_review"]))

    state = run_event_pipeline(
        session,
        signal_ids=[signal.id],
        run_key="manual-p1-5-manual-review",
        source_scope={"source": "demo"},
        tools=tools,
    )

    candidate = session.scalar(select(EventCandidate))
    dossier = session.scalar(select(EventDossier))
    run = session.scalar(select(PipelineRun))

    assert state.status == "manual_review"
    assert state.published_event_id is None
    assert candidate.status == "manual_review"
    assert dossier.status == "manual_review"
    assert session.scalars(select(PublishedEvent)).all() == []
    assert run.status == "partial_failed"
    assert run.published_count == 0


def test_langgraph_pipeline_reject_does_not_publish():
    """验证 reject 分支会拒绝候选事件且不发布。

    输入：审稿直接返回 reject 的 reviewer。
    输出：candidate 和 dossier 均为 rejected，PipelineRun 失败，PublishedEvent 为空。
    """
    session = make_session()
    signal = seed_signal(session)
    tools = EventPipelineTools(session, reviewer=FixedDecisionReviewer(["reject"]))

    state = run_event_pipeline(
        session,
        signal_ids=[signal.id],
        run_key="manual-p1-5-reject",
        source_scope={"source": "demo"},
        tools=tools,
    )

    candidate = session.scalar(select(EventCandidate))
    dossier = session.scalar(select(EventDossier))
    run = session.scalar(select(PipelineRun))

    assert state.status == "failed"
    assert state.published_event_id is None
    assert candidate.status == "rejected"
    assert dossier.status == "rejected"
    assert session.scalars(select(PublishedEvent)).all() == []
    assert run.status == "failed"
    assert run.published_count == 0

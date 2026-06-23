from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from worker.agents.event_pipeline_agents import (
    OnDutyEditorAgentStub,
    ResearchWriterAgentStub,
    ReviewPublisherAgentStub,
)
from worker.agents.factory import EventAgentSet
from worker.agents.llm_event_pipeline_agents import (
    OnDutyEditorLLMAgent,
    ResearchWriterLLMAgent,
    ReviewPublisherLLMAgent,
)
from worker.agents.llm_json_agent import LLMAgentOutputError
from worker.models import AgentRun, Base, PublishedEvent
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.signal_service import SignalService
from worker.tools.event_pipeline_tools import EventPipelineTools


def make_session():
    """创建 tool 测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 autoflush=False 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def seed_signal(session):
    """写入一条 tool 可处理的来源信号。

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


def stub_agent_set() -> EventAgentSet:
    """创建 tool 层离线测试用 stub agent 集合。

    输入：无。
    输出：显式 EventAgentSet，避免测试依赖运行态默认 Agent 模式。
    """
    return EventAgentSet(
        editor=OnDutyEditorAgentStub(),
        writer=ResearchWriterAgentStub(),
        reviewer=ReviewPublisherAgentStub(),
    )


class BrokenEditorAgent:
    """模拟真实 LLM editor 异常的测试 Agent。

    输入：任意 signals。
    输出：抛出 LLMAgentOutputError，用于验证工程 fallback。
    """

    name = "broken_editor_llm"
    role = "editor"
    model_provider = "fake"
    model_name = "broken-model"
    prompt_version = "broken-editor-v1"

    def triage(self, signals):
        """始终抛出 LLM 输出异常。

        输入：来源信号列表。
        输出：抛出 LLMAgentOutputError。
        """
        raise LLMAgentOutputError("fake llm editor failure")


def test_tools_default_to_llm_agents(monkeypatch):
    """验证 EventPipelineTools 默认运行态使用真实 LLM Agent。

    输入：临时 Session 和测试用 OPENAI_API_KEY。
    输出：三类默认 Agent 均为 LLM Agent；不会退回 stub。
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    session = make_session()

    tools = EventPipelineTools(session)

    assert isinstance(tools.editor, OnDutyEditorLLMAgent)
    assert isinstance(tools.writer, ResearchWriterLLMAgent)
    assert isinstance(tools.reviewer, ReviewPublisherLLMAgent)


def test_tools_fallback_to_stub_when_llm_agent_fails():
    """验证 LLM Agent 异常时会用 stub 兜底且记录原因。

    输入：一个会抛错的 editor LLM Agent 和默认 stub fallback。
    输出：candidate 仍能生成，fallback_events 记录 editor 的失败原因。
    """
    session = make_session()
    signal = seed_signal(session)
    tools = EventPipelineTools(session, agents=stub_agent_set(), editor=BrokenEditorAgent())
    run = tools.start_run(run_key="manual-fallback-tools", source_scope={"source": "demo"})

    signals = tools.load_signals([signal.id])
    candidate = tools.create_candidate(signals)
    agent_run = tools.record_agent_result(
        run.id,
        tools.effective_agent_for_role("editor").name,
        "editor",
        "triage one source signal",
        {"candidate_id": candidate.id},
        agent=tools.effective_agent_for_role("editor"),
    )

    assert candidate.id is not None
    assert agent_run.agent_name == "on_duty_editor_stub"
    assert agent_run.trace_json["fallback"]["agent_role"] == "editor"
    assert agent_run.trace_json["fallback"]["failed_agent_name"] == "broken_editor_llm"
    assert session.scalar(select(AgentRun)).trace_json["fallback"]["fallback_agent_name"] == "on_duty_editor_stub"
    assert tools.fallback_events == [
        {
            "agent_role": "editor",
            "failed_agent_name": "broken_editor_llm",
            "fallback_agent_name": "on_duty_editor_stub",
            "reason": "fake llm editor failure",
        }
    ]


def test_tools_create_publish_flow_and_update_run_counts():
    """验证工程 tool 通过服务层完成候选、档案、审稿、发布和 run 计数。

    输入：一条 SourceSignal 和显式确定性 Agent stub。
    输出：PublishedEvent 入库，PipelineRun 计数字段与最终数据库结果一致。
    """
    session = make_session()
    signal = seed_signal(session)
    tools = EventPipelineTools(session, agents=stub_agent_set())
    run = tools.start_run(run_key="manual-p1-2-tools", source_scope={"source": "demo"})

    signals = tools.load_signals([signal.id])
    candidate = tools.create_candidate(signals)
    dossier = tools.create_dossier(candidate, signals)
    review = tools.review_dossier(dossier)
    published = tools.publish_if_approved(candidate.id, dossier.id, review.decision)
    finished_run = tools.finish_run_with_counts(run.id, status="succeeded", summary="tool smoke")

    assert published is not None
    assert session.scalar(select(PublishedEvent)).id == published.id
    assert finished_run.signals_count == 1
    assert finished_run.candidates_count == 1
    assert finished_run.dossiers_count == 1
    assert finished_run.published_count == 1
    assert finished_run.failed_count == 0

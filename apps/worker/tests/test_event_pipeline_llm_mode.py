from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from worker.models import AgentRun, Base, PublishedEvent
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.signal_service import SignalService
from worker.workflows.event_pipeline import run_event_pipeline


class FakeLLMClient:
    """事件 pipeline LLM 模式测试用 fake client。

    输入：预设 response 文本列表。
    输出：记录 chat 调用，并按顺序返回 response。
    """

    provider = "fake"
    model = "fake-model"

    def __init__(self, responses: list[str]):
        """初始化 fake client。

        输入：模型响应文本列表。
        输出：可供三类 LLM Agent 共享的 fake client。
        """
        self.responses = responses
        self.calls: list[dict[str, str]] = []

    def chat(self, message: str, system_prompt: str = "You are a helpful assistant.") -> str:
        """模拟 LLMClient.chat。

        输入：user message 和 system_prompt。
        输出：下一条预设模型响应。
        """
        self.calls.append({"message": message, "system_prompt": system_prompt})
        return self.responses.pop(0)


def make_session():
    """创建 LLM mode workflow 测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 autoflush=False 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def seed_signal(session):
    """写入一条 LLM mode workflow 可消费的来源信号。

    输入：测试 Session。
    输出：SourceSignal ORM 对象。
    """
    service = SignalService(session)
    service.upsert_source(
        SourceCreate(source_key="hn_algolia", name="Hacker News Algolia", source_type="community", fetch_method="api")
    )
    return service.upsert_signal(
        SourceSignalCreate(
            source_key="hn_algolia",
            source_item_id="1001",
            original_title="OpenAI releases a new coding agent",
            original_url="https://example.com/openai-coding-agent",
            raw_summary="HN discussion about OpenAI's new coding agent.",
            source_hash="hn_algolia:1001",
            heat_metrics={"points": 120, "comments": 45},
        )
    )


def candidate_json() -> str:
    """生成 fake LLM 候选事件响应。

    输入：无。
    输出：符合 EventCandidateDraft 的 JSON 字符串。
    """
    return """
{
  "candidate_key": "hn-openai-agent",
  "title": "OpenAI 新编码 Agent 引发开发者关注",
  "event_type": "product_update",
  "category": "模型与产品",
  "primary_subject": "OpenAI",
  "suggested_angle": "从开发者工作流变化解释这件事。",
  "heat_score": 75,
  "importance_score": 82,
  "audience_value_score": 78,
  "ranking_score": 79,
  "ranking_reason": "HN 讨论热度和开发者使用价值同时存在。",
  "merge_reason": "当前信号可单独形成候选事件。"
}
""".strip()


def dossier_json() -> str:
    """生成 fake LLM 事件档案响应。

    输入：无。
    输出：符合 EventDossierDraft 的 JSON 字符串。
    """
    return """
{
  "candidate_key": "hn-openai-agent",
  "card_title": "OpenAI 新编码 Agent 引发关注",
  "card_summary": "开发者正在讨论 OpenAI 新编码 Agent 对工作流的影响。",
  "category": "模型与产品",
  "signal_label": "高热讨论",
  "detail_title": "OpenAI 新编码 Agent 为什么值得关注",
  "detail_summary": "这次讨论集中在编码 Agent 对开发者工作流和工具选择的影响。",
  "detail_body": "发生了什么：HN 上开发者正在讨论 OpenAI 新编码 Agent。\\n\\n为什么重要：编码 Agent 可能改变开发者使用 AI 工具的方式。\\n\\n后续看什么：观察官方说明、API 能力和社区反馈。",
  "why_it_matters": "这件事有助于中文用户理解 AI 编程工具的新变化。",
  "follow_up_points": ["观察官方文档", "观察社区反馈"],
  "source_refs": [
    {
      "signal_id": "sig_1",
      "title": "OpenAI releases a new coding agent",
      "url": "https://example.com/openai-coding-agent",
      "source_key": "hn_algolia"
    }
  ],
  "status": "draft"
}
""".strip()


def review_json() -> str:
    """生成 fake LLM 审稿结果响应。

    输入：无。
    输出：符合 ReviewResultDraft 的 JSON 字符串。
    """
    return """
{
  "decision": "publish",
  "risk_level": "low",
  "issues": [],
  "revision_instructions": "",
  "checked_items": {
    "source_supported": true,
    "not_overstated": true,
    "has_chinese_context": true
  }
}
""".strip()


def test_event_pipeline_can_run_with_injected_llm_agents():
    """验证 workflow 可通过注入 fake LLM agents 跑通，不依赖真实网络。

    输入：一条 SourceSignal、agent_mode=llm 和共享 fake LLM client。
    输出：PublishedEvent 入库，AgentRun 记录三类 LLM Agent 名称。
    """
    session = make_session()
    signal = seed_signal(session)
    fake_client = FakeLLMClient([candidate_json(), candidate_json(), dossier_json(), review_json()])

    state = run_event_pipeline(
        session,
        signal_ids=[signal.id],
        run_key="manual-p1-4-llm-mode",
        source_scope={"source": "hn_algolia"},
        agent_mode="llm",
        llm_client=fake_client,
    )

    published_events = session.scalars(select(PublishedEvent)).all()
    agent_runs = session.scalars(select(AgentRun)).all()
    agent_names = {run.agent_name for run in agent_runs}

    assert state.status == "succeeded"
    assert state.published_event_id == published_events[0].id
    assert len(agent_runs) == 3
    assert agent_names == {
        "on_duty_editor_llm",
        "research_writer_llm",
        "review_publisher_llm",
    }
    assert len(fake_client.calls) == 4

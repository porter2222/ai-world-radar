import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from worker.models import AgentRun, Base, PipelineRun, PublishedEvent
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


def rich_detail_body() -> str:
    """生成 LLM workflow 测试用高信息密度详情正文。

    输入：无。
    输出：至少五段、满足 EventDossierDraft 校验的正文。
    """
    return (
        "Hacker News 上出现一则关于 OpenAI 新编码 Agent 的讨论，开发者正在关注它是否会改变日常软件开发流程。"
        "这条来源是社区热度信号，因此它能证明讨论正在发生，但不能证明官方已经发布或确认完整产品路线。\n\n"
        "讨论的背景是 AI 编程工具正在从代码补全和问答辅助，向更主动的任务执行形态发展。"
        "开发者关心这类 Agent 是否能理解项目上下文、跨文件修改代码、运行测试并解释失败原因。\n\n"
        "社区讨论焦点包括效率提升、重复劳动减少、迁移脚本生成和代码审查辅助。"
        "同时也有开发者担心上下文误读、权限过大、生成代码不可控，以及团队协作中的责任边界不清。"
        "这些争议决定了它能否从新鲜工具变成稳定工作流。\n\n"
        "对中文用户来说，这类讨论可以帮助判断 AI 编程工具的真正落地方向。"
        "如果后续出现稳定实测、企业采用案例或官方 API 能力说明，它可能从社区热议升级为更强的事实型事件。"
        "在此之前，正文应帮助用户理解为什么这股热度值得观察。\n\n"
        "边界必须明确：当前只能写成 HN 开发者正在热议，不能写成 OpenAI 已确认新功能，也不能写成行业已经得出结论。"
        "后续应观察官方文档、开发者实测和开源项目工作流模板，并把新的强证据和当前社区热度区分开。"
    )


def dossier_json() -> str:
    """生成 fake LLM 事件档案响应。

    输入：无。
    输出：符合 EventDossierDraft 的 JSON 字符串。
    """
    return json.dumps(
        {
            "candidate_key": "hn-openai-agent",
            "card_title": "OpenAI 新编码 Agent 引发关注",
            "card_summary": "开发者正在讨论 OpenAI 新编码 Agent 对工作流的影响。",
            "category": "模型与产品",
            "signal_label": "高热讨论",
            "detail_title": "OpenAI 新编码 Agent 为什么值得关注",
            "detail_summary": "这次讨论集中在编码 Agent 对开发者工作流和工具选择的影响。",
            "detail_body": rich_detail_body(),
            "why_it_matters": "这件事有助于中文用户理解 AI 编程工具的新变化。",
            "follow_up_points": ["观察官方文档", "观察社区反馈"],
            "source_refs": [
                {
                    "signal_id": "sig_1",
                    "title": "OpenAI releases a new coding agent",
                    "url": "https://example.com/openai-coding-agent",
                    "source_key": "hn_algolia",
                }
            ],
            "status": "draft",
        },
        ensure_ascii=False,
    )


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


def test_llm_agent_runs_record_provider_model_prompt_and_retry_count():
    """验证 agent_runs 记录真实 LLM metadata。

    输入：writer 第一次返回非法 JSON、第二次 repair 成功的 fake LLM client。
    输出：AgentRun 写入 provider、model、prompt_version 和 JSON repair retry_count。
    """
    session = make_session()
    signal = seed_signal(session)
    fake_client = FakeLLMClient(
        [candidate_json(), candidate_json(), "not json", dossier_json(), review_json()]
    )

    state = run_event_pipeline(
        session,
        signal_ids=[signal.id],
        run_key="manual-p1-4-llm-metadata",
        source_scope={"source": "hn_algolia"},
        agent_mode="llm",
        llm_client=fake_client,
    )

    agent_runs = session.scalars(select(AgentRun)).all()
    runs_by_name = {run.agent_name: run for run in agent_runs}

    assert state.status == "succeeded"
    assert runs_by_name["on_duty_editor_llm"].model_provider == "fake"
    assert runs_by_name["on_duty_editor_llm"].model_name == "fake-model"
    assert runs_by_name["on_duty_editor_llm"].prompt_version == "p1-4-editor-v1"
    assert runs_by_name["on_duty_editor_llm"].retry_count == 0
    assert runs_by_name["research_writer_llm"].model_provider == "fake"
    assert runs_by_name["research_writer_llm"].model_name == "fake-model"
    assert runs_by_name["research_writer_llm"].prompt_version == "p1-4-writer-v1"
    assert runs_by_name["research_writer_llm"].retry_count == 1
    assert runs_by_name["research_writer_llm"].trace_json["llm_prompt_version"] == "p1-4-writer-v1"
    assert runs_by_name["review_publisher_llm"].prompt_version == "p1-4-reviewer-v1"


def test_llm_agent_failure_records_failed_agent_run():
    """验证 LLM 输出持续失败时记录 failed agent_run。

    输入：reviewer 连续三次返回非法 JSON 的 fake LLM client。
    输出：workflow 返回 failed，AgentRun 和 PipelineRun 均记录失败信息。
    """
    session = make_session()
    signal = seed_signal(session)
    fake_client = FakeLLMClient(
        [candidate_json(), candidate_json(), dossier_json(), "not json", "still not json", "bad again"]
    )

    state = run_event_pipeline(
        session,
        signal_ids=[signal.id],
        run_key="manual-p1-4-llm-failure",
        source_scope={"source": "hn_algolia"},
        agent_mode="llm",
        llm_client=fake_client,
    )

    failed_run = session.scalar(select(AgentRun).where(AgentRun.status == "failed"))
    pipeline_run = session.scalar(select(PipelineRun))
    published_count = len(session.scalars(select(PublishedEvent)).all())

    assert state.status == "failed"
    assert state.errors
    assert failed_run is not None
    assert failed_run.agent_name == "review_publisher_llm"
    assert failed_run.model_provider == "fake"
    assert failed_run.model_name == "fake-model"
    assert failed_run.prompt_version == "p1-4-reviewer-v1"
    assert failed_run.retry_count == 2
    assert "无法解析 LLM 输出为 ReviewResultDraft" in failed_run.error_message
    assert pipeline_run.status == "failed"
    assert pipeline_run.failed_count == 1
    assert published_count == 0

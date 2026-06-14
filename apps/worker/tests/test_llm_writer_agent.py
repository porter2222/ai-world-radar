from worker.agents.llm_event_pipeline_agents import ResearchWriterLLMAgent
from worker.schemas.event import EventCandidateDraft, EventDossierDraft


class FakeLLMClient:
    """测试用 fake LLM client。

    输入：预设 response 文本列表。
    输出：记录 chat 调用，并按顺序返回 response。
    """

    def __init__(self, responses: list[str]):
        """初始化 fake client。

        输入：模型响应文本列表。
        输出：可供 ResearchWriterLLMAgent 调用的 fake client。
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


def candidate_draft() -> EventCandidateDraft:
    """创建研究写作测试用候选事件。

    输入：无。
    输出：EventCandidateDraft。
    """
    return EventCandidateDraft(
        candidate_key="hn-openai-agent",
        title="OpenAI 新编码 Agent 引发开发者关注",
        event_type="product_update",
        category="模型与产品",
        primary_subject="OpenAI",
        suggested_angle="从开发者工作流变化解释这件事。",
        heat_score=75,
        importance_score=82,
        audience_value_score=78,
        ranking_score=79,
        ranking_reason="HN 讨论热度和开发者使用价值同时存在。",
        merge_reason="当前信号可单独形成候选事件。",
    )


def sample_signal() -> dict:
    """创建研究写作测试用来源信号。

    输入：无。
    输出：包含标题、URL、摘要和来源 key 的 source signal dict。
    """
    return {
        "id": "sig_1",
        "source_key": "hn_algolia",
        "original_title": "OpenAI releases a new coding agent",
        "original_url": "https://example.com/openai-coding-agent",
        "raw_summary": "HN discussion about OpenAI's new coding agent.",
        "heat_metrics": {"points": 120, "comments": 45},
    }


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


def test_research_writer_llm_agent_returns_event_dossier_draft():
    """验证研究写作 LLM Agent 输出 EventDossierDraft。

    输入：候选事件、来源信号和返回合法 JSON 的 fake LLM。
    输出：EventDossierDraft，包含卡片、详情正文和 source_refs。
    """
    fake_client = FakeLLMClient([dossier_json()])
    agent = ResearchWriterLLMAgent(fake_client)

    result = agent.draft(candidate_draft(), [sample_signal()])

    assert isinstance(result, EventDossierDraft)
    assert result.candidate_key == "hn-openai-agent"
    assert result.card_title == "OpenAI 新编码 Agent 引发关注"
    assert result.source_refs[0]["signal_id"] == "sig_1"
    assert "中文用户" in result.why_it_matters
    assert agent.name == "research_writer_llm"
    assert agent.role == "writer"
    assert agent.prompt_version == "p1-4-writer-v1"


def test_research_writer_receives_revision_instructions():
    """验证审稿修订意见会进入写作 prompt。

    输入：候选事件、来源信号、修订意见和 fake LLM。
    输出：user prompt 包含修订意见和写作边界。
    """
    fake_client = FakeLLMClient([dossier_json()])
    agent = ResearchWriterLLMAgent(fake_client)

    agent.draft(candidate_draft(), [sample_signal()], revision_instructions="补充来源支撑，减少过度推断。")

    combined_prompt = fake_client.calls[0]["system_prompt"] + "\n" + fake_client.calls[0]["message"]
    assert "补充来源支撑，减少过度推断。" in combined_prompt
    assert "面向中文用户" in combined_prompt
    assert "不要编造来源没有支撑的信息" in combined_prompt
    assert "card_summary 不超过 120 字符" in combined_prompt
    assert "source_refs 必须引用输入 signal" in combined_prompt

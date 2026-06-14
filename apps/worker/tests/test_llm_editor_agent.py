from worker.agents.llm_event_pipeline_agents import OnDutyEditorLLMAgent
from worker.schemas.event import EventCandidateDraft


class FakeLLMClient:
    """测试用 fake LLM client。

    输入：预设 response 文本列表。
    输出：记录 chat 调用，并按顺序返回 response。
    """

    def __init__(self, responses: list[str]):
        """初始化 fake client。

        输入：模型响应文本列表。
        输出：可供 OnDutyEditorLLMAgent 调用的 fake client。
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


def sample_signal() -> dict:
    """创建值班编辑 LLM Agent 测试信号。

    输入：无。
    输出：包含 HN 标题、URL、摘要和热度指标的 source signal dict。
    """
    return {
        "id": "sig_1",
        "source_key": "hn_algolia",
        "source_item_id": "1001",
        "original_title": "OpenAI releases a new coding agent",
        "original_url": "https://example.com/openai-coding-agent",
        "raw_summary": "HN discussion about OpenAI's new coding agent.",
        "heat_metrics": {"points": 120, "comments": 45},
        "metadata": {"author": "hn-user"},
    }


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


def test_on_duty_editor_llm_agent_returns_candidate_draft():
    """验证值班编辑 LLM Agent 把来源信号转为 EventCandidateDraft。

    输入：一条标准化 source signal 和返回合法 JSON 的 fake LLM。
    输出：EventCandidateDraft，包含候选事件 key、标题和排序分。
    """
    fake_client = FakeLLMClient([candidate_json()])
    agent = OnDutyEditorLLMAgent(fake_client)

    result = agent.triage([sample_signal()])

    assert isinstance(result, EventCandidateDraft)
    assert result.candidate_key == "hn-openai-agent"
    assert result.title == "OpenAI 新编码 Agent 引发开发者关注"
    assert result.ranking_score == 79
    assert agent.name == "on_duty_editor_llm"
    assert agent.role == "editor"
    assert agent.prompt_version == "p1-4-editor-v1"
    assert "OpenAI releases a new coding agent" in fake_client.calls[0]["message"]


def test_on_duty_editor_prompt_forbids_database_and_publish_actions():
    """验证 prompt 明确要求 Agent 不写数据库、不发布、不删除信号。

    输入：一条标准化 source signal 和 fake LLM。
    输出：system/user prompt 中包含工程边界约束。
    """
    fake_client = FakeLLMClient([candidate_json()])
    agent = OnDutyEditorLLMAgent(fake_client)

    agent.triage([sample_signal()])

    combined_prompt = fake_client.calls[0]["system_prompt"] + "\n" + fake_client.calls[0]["message"]
    assert "只输出 JSON" in combined_prompt
    assert "不要写数据库" in combined_prompt
    assert "不要直接发布" in combined_prompt
    assert "不要删除或隐藏信号" in combined_prompt
    assert "不做完整事实核验" in combined_prompt

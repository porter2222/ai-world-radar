import pytest

from worker.agents.llm_json_agent import LLMAgentOutputError, LLMJsonAgent
from worker.schemas.event import EventCandidateDraft


class FakeLLMClient:
    """测试用 fake LLM client。

    输入：预设 response 文本列表。
    输出：记录每次 chat 调用，并按顺序返回 response。
    """

    def __init__(self, responses: list[str], usages: list[dict[str, int] | None] | None = None):
        """初始化 fake client。

        输入：模型响应文本列表，以及可选 usage 列表。
        输出：可供 LLMJsonAgent 调用的 fake client。
        """
        self.responses = responses
        self.usages = usages or []
        self.last_usage: dict[str, int] | None = None
        self.calls: list[dict[str, str]] = []

    def chat(self, message: str, system_prompt: str = "You are a helpful assistant.") -> str:
        """模拟 LLMClient.chat。

        输入：user message 和 system_prompt。
        输出：下一条预设模型响应。
        """
        self.calls.append({"message": message, "system_prompt": system_prompt})
        self.last_usage = self.usages.pop(0) if self.usages else None
        return self.responses.pop(0)


def candidate_json() -> str:
    """生成候选事件 JSON。

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


def test_llm_json_agent_parses_fenced_json_into_schema():
    """验证 LLMJsonAgent 能提取 fenced JSON 并校验为 Pydantic schema。

    输入：返回 fenced JSON 的 fake LLM client。
    输出：LLMJsonResult.payload 是 EventCandidateDraft，且 retry_count 为 0。
    """
    fake_client = FakeLLMClient([f"```json\n{candidate_json()}\n```"])
    agent = LLMJsonAgent(fake_client)

    result = agent.run_json(
        EventCandidateDraft,
        system_prompt="你是 AI 情报编辑。",
        user_prompt="请输出候选事件 JSON。",
    )

    assert isinstance(result.payload, EventCandidateDraft)
    assert result.payload.candidate_key == "hn-openai-agent"
    assert result.raw_text.startswith("```json")
    assert result.retry_count == 0
    assert fake_client.calls[0]["system_prompt"] == "你是 AI 情报编辑。"


def test_llm_json_agent_repairs_invalid_json_once():
    """验证第一次输出非法时会带错误摘要重试，并返回 retry_count=1。

    输入：第一次返回非 JSON、第二次返回合法 JSON 的 fake LLM client。
    输出：第二次调用携带修复提示，最终返回 EventCandidateDraft。
    """
    fake_client = FakeLLMClient(["not json", candidate_json()])
    agent = LLMJsonAgent(fake_client, max_retries=2)

    result = agent.run_json(
        EventCandidateDraft,
        system_prompt="你是 AI 情报编辑。",
        user_prompt="请输出候选事件 JSON。",
    )

    assert isinstance(result.payload, EventCandidateDraft)
    assert result.retry_count == 1
    assert len(fake_client.calls) == 2
    assert "请修复" in fake_client.calls[1]["message"]
    assert "not json" in fake_client.calls[1]["message"]


def test_llm_json_agent_records_duration_and_token_usage():
    """验证 LLMJsonAgent 会记录耗时和 token usage。

    输入：暴露 last_usage 的 fake LLM client。
    输出：LLMJsonResult 包含非负 duration_ms 和 usage 计数。
    """
    fake_client = FakeLLMClient(
        [candidate_json()],
        usages=[{"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}],
    )
    agent = LLMJsonAgent(fake_client)

    result = agent.run_json(
        EventCandidateDraft,
        system_prompt="你是 AI 情报编辑。",
        user_prompt="请输出候选事件 JSON。",
    )

    assert result.duration_ms >= 0
    assert result.token_usage == {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}


def test_llm_json_agent_raises_after_max_retries():
    """验证多次修复失败后抛出 LLMAgentOutputError。

    输入：连续三次非法响应，max_retries 为 2。
    输出：抛出 LLMAgentOutputError，并已完成 3 次 chat 调用。
    """
    fake_client = FakeLLMClient(["not json", "still not json", "bad again"])
    agent = LLMJsonAgent(fake_client, max_retries=2)

    with pytest.raises(LLMAgentOutputError) as exc_info:
        agent.run_json(
            EventCandidateDraft,
            system_prompt="你是 AI 情报编辑。",
            user_prompt="请输出候选事件 JSON。",
        )

    assert "无法解析" in str(exc_info.value)
    assert len(fake_client.calls) == 3

from __future__ import annotations

import pytest
from pydantic import ValidationError

from worker.agents.editorial_selector_agent import EditorialSelectorLLMAgent
from worker.schemas.editorial_selection import EditorialSelectionResult


class FakeLLMClient:
    """测试用 fake LLM client。

    输入：预设 response 文本列表。
    输出：记录 chat 调用，并按顺序返回 response。
    """

    def __init__(self, responses: list[str]):
        """初始化 fake client。

        输入：模型响应文本列表。
        输出：可供 EditorialSelectorLLMAgent 调用的 fake client。
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


def candidate_groups() -> list[dict]:
    """创建 selector 测试候选组。

    输入：无。
    输出：包含 selected、rejected、manual_review 三类预期判断的 candidate group dict 列表。
    """
    return [
        {
            "candidate_group_id": "group_hot",
            "title": "OpenAI releases a new coding agent",
            "signal_ids": ["sig_1", "sig_2"],
            "source_keys": ["hn_algolia", "openai_news"],
            "merge_reason": "same_canonical_url",
        },
        {
            "candidate_group_id": "group_minor",
            "title": "Small dependency patch release",
            "signal_ids": ["sig_3"],
            "source_keys": ["github_releases"],
            "merge_reason": "single_signal",
        },
        {
            "candidate_group_id": "group_unclear",
            "title": "Unclear model rumor spreading online",
            "signal_ids": ["sig_4"],
            "source_keys": ["hn_algolia"],
            "merge_reason": "single_signal",
        },
    ]


def selection_json() -> str:
    """生成 fake LLM 编辑筛选响应。

    输入：无。
    输出：符合 EditorialSelectionResult 的 JSON 字符串。
    """
    return """
{
  "selected": [
    {
      "candidate_group_id": "group_hot",
      "signal_ids": ["sig_1", "sig_2"],
      "event_title": "OpenAI 新编码 Agent 引发开发者关注",
      "priority_score": 92,
      "suggested_angle": "从开发者工作流和工具生态变化解释这件事。",
      "reason": "官方发布叠加社区讨论，对中文 AI 用户有明显理解价值。"
    }
  ],
  "rejected": [
    {
      "candidate_group_id": "group_minor",
      "reason": "只是普通依赖补丁版本，暂不构成值得展示的 AI 圈事件。"
    }
  ],
  "manual_review": [
    {
      "candidate_group_id": "group_unclear",
      "reason": "来源信号不足，可能是传闻，需要人工确认展示边界。"
    }
  ]
}
""".strip()


def test_editorial_selector_agent_returns_structured_selection_result():
    """验证 LLM Editorial Selector 返回 selected / rejected / manual_review 结构。

    输入：三个候选组和返回合法 JSON 的 fake LLM。
    输出：EditorialSelectionResult，selected 项包含 priority_score、reason、suggested_angle。
    """
    fake_client = FakeLLMClient([selection_json()])
    agent = EditorialSelectorLLMAgent(fake_client)

    result = agent.select(candidate_groups())

    assert isinstance(result, EditorialSelectionResult)
    assert result.selected[0].candidate_group_id == "group_hot"
    assert result.selected[0].priority_score == 92
    assert result.selected[0].reason == "官方发布叠加社区讨论，对中文 AI 用户有明显理解价值。"
    assert result.selected[0].suggested_angle == "从开发者工作流和工具生态变化解释这件事。"
    assert result.rejected[0].candidate_group_id == "group_minor"
    assert result.manual_review[0].candidate_group_id == "group_unclear"
    assert agent.name == "editorial_selector_llm"
    assert agent.role == "editorial_selector"
    assert agent.prompt_version == "p1-9-selector-v1"
    assert "OpenAI releases a new coding agent" in fake_client.calls[0]["message"]


def test_editorial_selection_schema_requires_selected_item_explanation_fields():
    """验证 selected 项必须包含编辑筛选解释字段。

    输入：缺少 suggested_angle 的 selected item。
    输出：Pydantic ValidationError，防止 selector 只返回不可解释的 id 列表。
    """
    with pytest.raises(ValidationError):
        EditorialSelectionResult.model_validate(
            {
                "selected": [
                    {
                        "candidate_group_id": "group_hot",
                        "signal_ids": ["sig_1"],
                        "event_title": "OpenAI 新编码 Agent",
                        "priority_score": 90,
                        "reason": "值得展示。",
                    }
                ],
                "rejected": [],
                "manual_review": [],
            }
        )


def test_editorial_selector_prompt_forbids_database_and_publish_actions():
    """验证 selector prompt 明确限制 Agent 只能输出建议。

    输入：候选组和 fake LLM。
    输出：system/user prompt 包含不写库、不发布、不修改信号的工程边界。
    """
    fake_client = FakeLLMClient([selection_json()])
    agent = EditorialSelectorLLMAgent(fake_client)

    agent.select(candidate_groups())

    combined_prompt = fake_client.calls[0]["system_prompt"] + "\n" + fake_client.calls[0]["message"]
    assert "只输出 JSON" in combined_prompt
    assert "只能输出编辑筛选建议" in combined_prompt
    assert "不要写数据库" in combined_prompt
    assert "不要直接发布" in combined_prompt
    assert "不要修改 source_signals" in combined_prompt

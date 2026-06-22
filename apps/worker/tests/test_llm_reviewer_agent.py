from worker.agents.llm_event_pipeline_agents import ReviewPublisherLLMAgent
from worker.schemas.event import EventDossierDraft, ReviewResultDraft


class FakeLLMClient:
    """测试用 fake LLM client。

    输入：预设 response 文本列表。
    输出：记录 chat 调用，并按顺序返回 response。
    """

    def __init__(self, responses: list[str]):
        """初始化 fake client。

        输入：模型响应文本列表。
        输出：可供 ReviewPublisherLLMAgent 调用的 fake client。
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


def sample_dossier() -> EventDossierDraft:
    """创建审稿发布测试用事件档案。

    输入：无。
    输出：包含卡片、详情正文、影响说明和来源引用的 EventDossierDraft。
    """
    return EventDossierDraft(
        candidate_key="hn-openai-agent",
        card_title="OpenAI 新编码 Agent 引发关注",
        card_summary="开发者正在讨论 OpenAI 新编码 Agent 对工作流的影响。",
        category="模型与产品",
        signal_label="高热讨论",
        detail_title="OpenAI 新编码 Agent 为什么值得关注",
        detail_summary="这次讨论集中在编码 Agent 对开发者工作流和工具选择的影响。",
        detail_body=(
            "发生了什么：HN 上开发者正在讨论 OpenAI 新编码 Agent。\n\n"
            "为什么重要：编码 Agent 可能改变开发者使用 AI 工具的方式。\n\n"
            "后续看什么：观察官方说明、API 能力和社区反馈。"
        ),
        why_it_matters="这件事有助于中文用户理解 AI 编程工具的新变化。",
        follow_up_points=["观察官方文档", "观察社区反馈"],
        source_refs=[
            {
                "signal_id": "sig_1",
                "title": "OpenAI releases a new coding agent",
                "url": "https://example.com/openai-coding-agent",
                "source_key": "hn_algolia",
            }
        ],
        status="draft",
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


def test_review_publisher_llm_agent_returns_publish_review():
    """验证审稿发布 LLM Agent 可输出 publish 决策。

    输入：完整事件档案、revision_count 和返回合法 JSON 的 fake LLM。
    输出：ReviewResultDraft，decision 为 publish 且风险等级为 low。
    """
    fake_client = FakeLLMClient([review_json()])
    agent = ReviewPublisherLLMAgent(fake_client)

    result = agent.review(sample_dossier(), revision_count=0)

    assert isinstance(result, ReviewResultDraft)
    assert result.decision == "publish"
    assert result.risk_level == "low"
    assert result.checked_items["source_supported"] is True
    assert agent.name == "review_publisher_llm"
    assert agent.role == "reviewer"
    assert agent.prompt_version == "p1-4-reviewer-v1"


def test_review_publisher_prompt_lists_allowed_decisions():
    """验证 prompt 明确限定审稿发布决策枚举。

    输入：完整事件档案和 fake LLM。
    输出：system/user prompt 包含允许的 decision 和审稿边界。
    """
    fake_client = FakeLLMClient([review_json()])
    agent = ReviewPublisherLLMAgent(fake_client)

    agent.review(sample_dossier(), revision_count=1)

    combined_prompt = fake_client.calls[0]["system_prompt"] + "\n" + fake_client.calls[0]["message"]
    assert "publish" in combined_prompt
    assert "revise" in combined_prompt
    assert "manual_review" in combined_prompt
    assert "reject" in combined_prompt
    assert "不要直接发布" in combined_prompt
    assert "不要改写正文" in combined_prompt
    assert "来源支撑" in combined_prompt
    assert "过度推断" in combined_prompt
    assert "风险不确定时选择 manual_review" in combined_prompt
    assert "revision_count: 1" in combined_prompt


def test_review_publisher_prompt_allows_bounded_heat_discussion_publish():
    """验证审稿 prompt 支持高热社区事件按表达边界发布。

    输入：HN 风格事件档案和 fake LLM。
    输出：prompt 明确热度源可支撑讨论本身，且不能写成官方已确认事实。
    """
    fake_client = FakeLLMClient([review_json()])
    agent = ReviewPublisherLLMAgent(fake_client)

    agent.review(sample_dossier(), revision_count=0)

    combined_prompt = fake_client.calls[0]["system_prompt"] + "\n" + fake_client.calls[0]["message"]
    assert "热度源可以支撑讨论正在发生" in combined_prompt
    assert "不要求每条热议型事件都有官方事实源" in combined_prompt
    assert "不能把社区讨论写成官方已确认事实" in combined_prompt
    assert "表达是否和来源强度匹配" in combined_prompt

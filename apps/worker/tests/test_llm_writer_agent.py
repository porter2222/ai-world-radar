import json

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


def rich_detail_body() -> str:
    """创建研究写作测试用高信息密度详情正文。

    输入：无。
    输出：至少五段、超过最低长度要求的 detail_body。
    """
    return (
        "OpenAI 新编码 Agent 之所以引发开发者关注，是因为它把 AI 编程工具的话题从“写几行代码”推向了“能否参与完整任务”。"
        "这类工具被期待承担需求拆解、跨文件修改、测试补全和错误定位等工作，而这些环节正是日常软件工程中最耗时间的部分。\n\n"
        "过去的 AI 编程助手更像是编辑器里的补全能力，开发者仍然需要自己理解上下文、决定改哪里、验证结果是否正确。"
        "Agent 形态的变化在于，它试图围绕一个目标连续行动，把规划、修改、检查和反馈串成一条更长的工作链。\n\n"
        "讨论焦点集中在真实项目里的可用性。开发者关心它能不能读懂项目结构，能不能遵守团队代码风格，能不能在修改后运行测试，"
        "也关心它在遇到失败时能否说明原因，而不是只给出一堆需要人工重新排查的代码。\n\n"
        "分歧主要来自可靠性和控制权。乐观者认为它会减少重复劳动，让小团队更快完成原型和迁移任务；谨慎者则担心它误解需求、"
        "制造隐藏缺陷，或把代码审查变成新的负担。真正决定价值的不是一次演示，而是它能否在复杂代码库里稳定交付可检查的结果。\n\n"
        "对中文开发者和 AI 产品团队来说，这件事值得放进工具选型和研发流程调整里观察。后续更关键的不是概念本身，"
        "而是真实团队是否会把它用于测试生成、问题修复、框架迁移、代码审查辅助和新人理解代码库等具体场景。"
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


def test_research_writer_prompt_bounds_community_heat_language():
    """验证写作 prompt 要求社区热度事件使用受限表达。

    输入：HN 来源信号和 fake LLM。
    输出：prompt 明确热度源只支撑讨论正在发生，不能写成官方已确认事实。
    """
    fake_client = FakeLLMClient([dossier_json()])
    agent = ResearchWriterLLMAgent(fake_client)

    agent.draft(candidate_draft(), [sample_signal()])

    combined_prompt = fake_client.calls[0]["system_prompt"] + "\n" + fake_client.calls[0]["message"]
    assert "热度源只支撑讨论正在发生" in combined_prompt
    assert "这个边界用于控制措辞和审稿判断" in combined_prompt
    assert "不要把来源分析过程写进 detail_body" in combined_prompt
    assert "不要写成官方已确认事实" in combined_prompt


def test_research_writer_prompt_treats_heat_events_as_discussion_reporting():
    """验证热度事件正文聚焦“讨论内容”而不是趋势判断。

    输入：HN 来源信号和 fake LLM。
    输出：prompt 明确热度事件要叙述外网正在讨论什么，并避免趋势结论。
    """
    fake_client = FakeLLMClient([dossier_json()])
    agent = ResearchWriterLLMAgent(fake_client)

    agent.draft(candidate_draft(), [sample_signal()])

    combined_prompt = fake_client.calls[0]["system_prompt"] + "\n" + fake_client.calls[0]["message"]
    assert "把热度事件写成外网正在讨论什么" in combined_prompt
    assert "不要判断趋势是否已经成立" in combined_prompt
    assert "避免使用持续升温、行业改变、正在重塑等趋势结论" in combined_prompt


def test_research_writer_prompt_requires_information_dense_detail_body():
    """验证写作 prompt 要求详情正文具备足够信息密度。

    输入：HN 来源信号和 fake LLM。
    输出：prompt 明确 detail_body 至少五段，并覆盖用户需要的核心信息。
    """
    fake_client = FakeLLMClient([dossier_json()])
    agent = ResearchWriterLLMAgent(fake_client)

    agent.draft(candidate_draft(), [sample_signal()])

    combined_prompt = fake_client.calls[0]["system_prompt"] + "\n" + fake_client.calls[0]["message"]
    assert "detail_body 至少 5 段" in combined_prompt
    assert "不少于 500 个中文字符" in combined_prompt
    assert "背景和触发点" in combined_prompt
    assert "关键变化或讨论焦点" in combined_prompt
    assert "不同观点或争议" in combined_prompt


def test_research_writer_prompt_keeps_detail_body_reader_facing():
    """验证详情正文 prompt 不把内部筛选和审稿语言暴露给用户。

    输入：HN 来源信号和 fake LLM。
    输出：prompt 明确正文只叙述事件本身，并禁止热度指标和后台元话术进入 detail_body。
    """
    fake_client = FakeLLMClient([dossier_json()])
    agent = ResearchWriterLLMAgent(fake_client)

    agent.draft(candidate_draft(), [sample_signal()])

    combined_prompt = fake_client.calls[0]["system_prompt"] + "\n" + fake_client.calls[0]["message"]
    assert "detail_body 只叙述事件本身" in combined_prompt
    assert "不要在 detail_body 中复述 points、comments、hn_heat_score 等热度指标" in combined_prompt
    assert "不要在 detail_body 中出现候选事件、输入信号、来源信号、来源边界" in combined_prompt
    assert "热度数据或传播情况" not in combined_prompt
    assert "来源边界和未确认内容" not in combined_prompt

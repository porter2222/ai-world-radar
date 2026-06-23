from __future__ import annotations

import json
from typing import Any

from worker.agents.llm_json_agent import LLMJsonAgent, LLMJsonResult
from worker.llm_client import LLMClient
from worker.schemas.event import EventCandidateDraft, EventDossierDraft, ReviewResultDraft


class OnDutyEditorLLMAgent:
    """值班编辑真实 LLM Agent。

    输入：标准化 source signals。
    输出：EventCandidateDraft，用于后续 EventService 创建候选事件。
    """

    name = "on_duty_editor_llm"
    role = "editor"
    prompt_version = "p1-4-editor-v1"

    def __init__(self, llm_client=None, max_retries: int = 2):
        """初始化值班编辑 LLM Agent。

        输入：可选 LLMClient 或测试 fake client，以及 JSON repair 最大重试次数。
        输出：可复用的 OnDutyEditorLLMAgent 实例。
        """
        self.llm_client = llm_client or LLMClient()
        self.json_agent = LLMJsonAgent(self.llm_client, max_retries=max_retries)
        self.model_provider = getattr(self.llm_client, "provider", None)
        self.model_name = getattr(self.llm_client, "model", None)
        self.last_result: LLMJsonResult[EventCandidateDraft] | None = None

    def triage(self, signals: list[dict[str, Any]]) -> EventCandidateDraft:
        """生成候选事件草案。

        输入：至少一条标准化来源信号。
        输出：EventCandidateDraft，包含候选事件 key、分类、评分和排序理由。
        """
        if not signals:
            raise ValueError("At least one source signal is required")
        result = self.json_agent.run_json(
            EventCandidateDraft,
            system_prompt=_editor_system_prompt(),
            user_prompt=_editor_user_prompt(signals),
            prompt_version=self.prompt_version,
        )
        self.last_result = result
        return result.payload


def _editor_system_prompt() -> str:
    """构造值班编辑 system prompt。

    输入：无。
    输出：限制模型角色、输出格式和工程边界的 system prompt。
    """
    return (
        "你是 AI World Radar 的值班编辑 Agent。"
        "你的任务是判断输入 source signals 是否值得形成一个 AI 圈事件候选。"
        "只输出 JSON，不要输出 Markdown，不要解释。"
        "不要写数据库，不要直接发布，不要删除或隐藏信号。"
        "不做完整事实核验，只根据输入信号给出 P1 阶段的候选事件判断。"
        "所有分数必须是 0 到 100 的数字。"
    )


def _editor_user_prompt(signals: list[dict[str, Any]]) -> str:
    """构造值班编辑 user prompt。

    输入：标准化 source signal dict 列表。
    输出：要求模型生成 EventCandidateDraft JSON 的 user prompt。
    """
    return (
        "请根据以下 source signals 生成一个 EventCandidateDraft JSON。\n"
        "字段必须包含 candidate_key、title、event_type、category、primary_subject、"
        "suggested_angle、heat_score、importance_score、audience_value_score、"
        "ranking_score、ranking_reason、merge_reason。\n"
        "source signals:\n"
        f"{json.dumps(signals, ensure_ascii=False, sort_keys=True)}"
    )


class ResearchWriterLLMAgent:
    """研究写作真实 LLM Agent。

    输入：候选事件草案、来源信号和可选修订意见。
    输出：EventDossierDraft，用于后续 EventService 保存事件档案。
    """

    name = "research_writer_llm"
    role = "writer"
    prompt_version = "p1-4-writer-v1"

    def __init__(self, llm_client=None, max_retries: int = 2):
        """初始化研究写作 LLM Agent。

        输入：可选 LLMClient 或测试 fake client，以及 JSON repair 最大重试次数。
        输出：可复用的 ResearchWriterLLMAgent 实例。
        """
        self.llm_client = llm_client or LLMClient()
        self.json_agent = LLMJsonAgent(self.llm_client, max_retries=max_retries)
        self.model_provider = getattr(self.llm_client, "provider", None)
        self.model_name = getattr(self.llm_client, "model", None)
        self.last_result: LLMJsonResult[EventDossierDraft] | None = None

    def draft(
        self,
        candidate: EventCandidateDraft,
        signals: list[dict[str, Any]],
        revision_instructions: str = "",
    ) -> EventDossierDraft:
        """生成事件档案草案。

        输入：候选事件草案、来源信号列表和审稿修订意见。
        输出：EventDossierDraft，包含首页卡片、详情正文、影响说明和来源引用。
        """
        if not signals:
            raise ValueError("At least one source signal is required")
        result = self.json_agent.run_json(
            EventDossierDraft,
            system_prompt=_writer_system_prompt(),
            user_prompt=_writer_user_prompt(candidate, signals, revision_instructions),
            prompt_version=self.prompt_version,
        )
        self.last_result = result
        return result.payload


def _writer_system_prompt() -> str:
    """构造研究写作 system prompt。

    输入：无。
    输出：限制写作角色、来源支撑和 JSON 输出格式的 system prompt。
    """
    return (
        "你是 AI World Radar 的研究写作 Agent，负责把候选事件写成面向中文用户的事件档案。"
        "只输出 JSON，不要输出 Markdown，不要解释。"
        "不要编造来源没有支撑的信息，不要夸大影响，不要直接写数据库。"
        "如果来源是 HN、Reddit、X、GitHub Trending 等热度源，热度源只支撑讨论正在发生。"
        "这个边界用于控制措辞和审稿判断，不要把来源分析过程写进 detail_body；不要写成官方已确认事实。"
        "把热度事件写成外网正在讨论什么，不要判断趋势是否已经成立。"
        "避免使用持续升温、行业改变、正在重塑等趋势结论；可写成开发者正在讨论、有人期待、也有人担心。"
        "detail_body 至少 5 段，不少于 500 个中文字符，必须有足够信息密度。"
        "detail_body 只叙述事件本身，像用户点开详情页后阅读的正文，不要输出编辑部自评、后台流程或产品分析口吻。"
        "五段应覆盖：背景和触发点、发生了什么、关键变化或讨论焦点、不同观点或争议、与中文用户相关的现实场景、后续进展。"
        "不要在 detail_body 中复述 points、comments、hn_heat_score 等热度指标。"
        "不要在 detail_body 中出现候选事件、输入信号、来源信号、来源边界、只有一条信号等后台或审稿语言。"
        "card_summary 不超过 120 字符。"
        "source_refs 必须引用输入 signal。"
    )


def _writer_user_prompt(
    candidate: EventCandidateDraft,
    signals: list[dict[str, Any]],
    revision_instructions: str,
) -> str:
    """构造研究写作 user prompt。

    输入：候选事件草案、来源信号列表和可选修订意见。
    输出：要求模型生成 EventDossierDraft JSON 的 user prompt。
    """
    revision_text = revision_instructions or "无"
    return (
        "请根据候选事件和 source signals 生成一个 EventDossierDraft JSON。\n"
        "字段必须包含 candidate_key、card_title、card_summary、category、signal_label、"
        "detail_title、detail_summary、detail_body、why_it_matters、follow_up_points、source_refs、status。\n"
        "写作要求：面向中文用户，解释发生了什么、为什么值得关注、后续看什么。\n"
        "热度源只支撑讨论正在发生；这个边界用于控制措辞和审稿判断，不要把来源分析过程写进 detail_body；"
        "不要写成官方已确认事实。\n"
        "把热度事件写成外网正在讨论什么，不要判断趋势是否已经成立；"
        "避免使用持续升温、行业改变、正在重塑等趋势结论，可写成开发者正在讨论、有人期待、也有人担心。\n"
        "detail_body 至少 5 段，不少于 500 个中文字符；detail_body 只叙述事件本身，"
        "必须覆盖背景和触发点、发生了什么、关键变化或讨论焦点、不同观点或争议、与中文用户相关的现实场景、后续进展。\n"
        "不要在 detail_body 中复述 points、comments、hn_heat_score 等热度指标；"
        "不要在 detail_body 中出现候选事件、输入信号、来源信号、来源边界、只有一条信号等后台或审稿语言。\n"
        "不要编造来源没有支撑的信息；source_refs 必须引用输入 signal；card_summary 不超过 120 字符。\n"
        f"修订意见：{revision_text}\n"
        f"candidate:\n{candidate.model_dump_json()}\n"
        "source signals:\n"
        f"{json.dumps(signals, ensure_ascii=False, sort_keys=True)}"
    )


class ReviewPublisherLLMAgent:
    """审稿发布真实 LLM Agent。

    输入：事件档案草案和当前修订次数。
    输出：ReviewResultDraft，用于后续 EventService 保存审稿结果并驱动状态变化。
    """

    name = "review_publisher_llm"
    role = "reviewer"
    prompt_version = "p1-4-reviewer-v1"

    def __init__(self, llm_client=None, max_retries: int = 2):
        """初始化审稿发布 LLM Agent。

        输入：可选 LLMClient 或测试 fake client，以及 JSON repair 最大重试次数。
        输出：可复用的 ReviewPublisherLLMAgent 实例。
        """
        self.llm_client = llm_client or LLMClient()
        self.json_agent = LLMJsonAgent(self.llm_client, max_retries=max_retries)
        self.model_provider = getattr(self.llm_client, "provider", None)
        self.model_name = getattr(self.llm_client, "model", None)
        self.last_result: LLMJsonResult[ReviewResultDraft] | None = None

    def review(self, dossier: EventDossierDraft, revision_count: int = 0) -> ReviewResultDraft:
        """审阅事件档案并生成结构化发布建议。

        输入：EventDossierDraft 和当前修订次数。
        输出：ReviewResultDraft，decision 只能是 publish、revise、manual_review 或 reject。
        """
        result = self.json_agent.run_json(
            ReviewResultDraft,
            system_prompt=_reviewer_system_prompt(),
            user_prompt=_reviewer_user_prompt(dossier, revision_count),
            prompt_version=self.prompt_version,
        )
        self.last_result = result
        return result.payload


def _reviewer_system_prompt() -> str:
    """构造审稿发布 system prompt。

    输入：无。
    输出：限制审稿角色、决策枚举和工程边界的 system prompt。
    """
    return (
        "你是 AI World Radar 的审稿发布 Agent，负责审阅事件档案草案并给出结构化建议。"
        "只输出 JSON，不要输出 Markdown，不要解释。"
        "decision 只能是 publish、revise、manual_review、reject。"
        "不要直接发布，不要改写正文，不要写数据库。"
        "必须检查来源支撑、过度推断、空泛表达和标题党风险。"
        "热度源可以支撑讨论正在发生，不要求每条热议型事件都有官方事实源。"
        "不要因为缺少官方事实源而要求修订；单一高热来源可以支撑热议型事件。"
        "审稿重点是表达是否和来源强度匹配；可以发布外网热议、社区正在讨论或传闻正在发酵。"
        "正文已经限定为讨论、争论、观点分歧时应倾向 publish。"
        "不能把社区讨论写成官方已确认事实；如果正文越过来源强度，应选择 revise 或 manual_review。"
        "只有出现未受限的确定性事实或无法理解的风险时才 manual_review。"
        "风险不确定时选择 manual_review。"
    )


def _reviewer_user_prompt(dossier: EventDossierDraft, revision_count: int) -> str:
    """构造审稿发布 user prompt。

    输入：事件档案草案和当前修订次数。
    输出：要求模型生成 ReviewResultDraft JSON 的 user prompt。
    """
    return (
        "请审阅以下 EventDossierDraft，并生成一个 ReviewResultDraft JSON。\n"
        "字段必须包含 decision、risk_level、issues、revision_instructions、checked_items。\n"
        "allowed decisions: publish, revise, manual_review, reject。\n"
        "checked_items 至少说明 source_supported、not_overstated、has_chinese_context。\n"
        f"revision_count: {revision_count}\n"
        f"dossier:\n{dossier.model_dump_json()}"
    )

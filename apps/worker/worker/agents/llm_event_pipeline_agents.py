from __future__ import annotations

import json
from typing import Any

from worker.agents.llm_json_agent import LLMJsonAgent, LLMJsonResult
from worker.llm_client import LLMClient
from worker.schemas.event import EventCandidateDraft, EventDossierDraft


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
        "不要编造来源没有支撑的信息；source_refs 必须引用输入 signal；card_summary 不超过 120 字符。\n"
        f"修订意见：{revision_text}\n"
        f"candidate:\n{candidate.model_dump_json()}\n"
        "source signals:\n"
        f"{json.dumps(signals, ensure_ascii=False, sort_keys=True)}"
    )

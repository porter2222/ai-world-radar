from __future__ import annotations

import json
from typing import Any

from worker.agents.llm_json_agent import LLMJsonAgent, LLMJsonResult
from worker.llm_client import LLMClient
from worker.schemas.editorial_selection import EditorialSelectionResult


class EditorialSelectorLLMAgent:
    """LLM 编辑筛选 Agent。

    输入：selector 前 candidate groups。
    输出：EditorialSelectionResult，只包含 selected / rejected / manual_review 建议。
    """

    name = "editorial_selector_llm"
    role = "editorial_selector"
    prompt_version = "p1-9-selector-v1"

    def __init__(self, llm_client=None, max_retries: int = 2, logger=None):
        """初始化 LLM 编辑筛选 Agent。

        输入：可选 LLMClient 或测试 fake client，以及 JSON repair 最大重试次数。
        输出：可复用的 EditorialSelectorLLMAgent 实例。
        """
        self.llm_client = llm_client or LLMClient()
        self.json_agent = LLMJsonAgent(
            self.llm_client,
            max_retries=max_retries,
            logger=logger,
            agent_name=self.name,
        )
        self.model_provider = getattr(self.llm_client, "provider", None)
        self.model_name = getattr(self.llm_client, "model", None)
        self.last_result: LLMJsonResult[EditorialSelectionResult] | None = None

    def select(self, candidate_groups: list[dict[str, Any]]) -> EditorialSelectionResult:
        """筛选候选事件组。

        输入：hard filter 和 grouping 后的 candidate group dict 列表。
        输出：EditorialSelectionResult；Agent 只给建议，不写库、不发布。
        """
        if not candidate_groups:
            raise ValueError("At least one candidate group is required")
        result = self.json_agent.run_json(
            EditorialSelectionResult,
            system_prompt=_selector_system_prompt(),
            user_prompt=_selector_user_prompt(candidate_groups),
            prompt_version=self.prompt_version,
        )
        self.last_result = result
        return result.payload


def _selector_system_prompt() -> str:
    """构造编辑筛选 system prompt。

    输入：无。
    输出：限制模型角色、输出格式和工程边界的 system prompt。
    """
    return (
        "你是 AI World Radar 的 LLM Editorial Selector。"
        "你的任务是从 candidate groups 中判断哪些 AI 圈事件值得进入写作和发布流程。"
        "只输出 JSON，不要输出 Markdown，不要解释。"
        "只能输出编辑筛选建议，不要写数据库，不要直接发布，不要修改 source_signals。"
        "不要做完整事实核验；本阶段判断的是事件展示价值、热度、重要性和中文用户理解价值。"
        "普通版本噪声、缺乏 AI 相关性的内容、无明显用户价值的条目应放入 rejected。"
        "信息不足但可能重要的条目应放入 manual_review。"
        "selected 项必须包含 priority_score、reason、suggested_angle，priority_score 必须是 0 到 100。"
    )


def _selector_user_prompt(candidate_groups: list[dict[str, Any]]) -> str:
    """构造编辑筛选 user prompt。

    输入：candidate group dict 列表。
    输出：要求模型生成 EditorialSelectionResult JSON 的 user prompt。
    """
    return (
        "请根据以下 candidate groups 生成一个 EditorialSelectionResult JSON。\n"
        "字段必须包含 selected、rejected、manual_review。\n"
        "selected 每项必须包含 candidate_group_id、signal_ids、event_title、priority_score、suggested_angle、reason。\n"
        "rejected 每项必须包含 candidate_group_id、reason。\n"
        "manual_review 每项必须包含 candidate_group_id、reason。\n"
        "只能输出编辑筛选建议，不要写数据库，不要直接发布，不要修改 source_signals。\n"
        "candidate groups:\n"
        f"{json.dumps(candidate_groups, ensure_ascii=False, sort_keys=True)}"
    )

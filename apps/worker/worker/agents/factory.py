from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from worker.agents.event_pipeline_agents import (
    OnDutyEditorAgentStub,
    ResearchWriterAgentStub,
    ReviewPublisherAgentStub,
)
from worker.agents.llm_event_pipeline_agents import (
    OnDutyEditorLLMAgent,
    ResearchWriterLLMAgent,
    ReviewPublisherLLMAgent,
)
from worker.llm_client import LLMClient


@dataclass(frozen=True)
class EventAgentSet:
    """封装事件 pipeline 使用的三类 Agent。

    输入：值班编辑、研究写作、审稿发布三个 Agent 实例。
    输出：可一次性注入 EventPipelineTools 的 Agent 集合。
    """

    editor: Any
    writer: Any
    reviewer: Any


def create_event_agents(mode: str = "llm", llm_client: Any | None = None, logger: Any | None = None) -> EventAgentSet:
    """根据模式创建事件 pipeline Agent 集合。

    输入：agent mode，支持 llm 或显式 stub；llm 模式可传入共享 LLMClient 或 fake client。
    输出：包含 editor、writer、reviewer 的 EventAgentSet。
    """
    normalized_mode = mode.lower().strip()
    if normalized_mode == "stub":
        return EventAgentSet(
            editor=OnDutyEditorAgentStub(),
            writer=ResearchWriterAgentStub(),
            reviewer=ReviewPublisherAgentStub(),
        )
    if normalized_mode == "llm":
        shared_client = llm_client or LLMClient()
        return EventAgentSet(
            editor=OnDutyEditorLLMAgent(shared_client, logger=logger),
            writer=ResearchWriterLLMAgent(shared_client, logger=logger),
            reviewer=ReviewPublisherLLMAgent(shared_client, logger=logger),
        )
    raise ValueError(f"Unsupported agent mode: {mode}")

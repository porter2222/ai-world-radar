from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from worker.schemas.common import WorkerSchema


EventPipelineStatus = Literal["initialized", "running", "succeeded", "manual_review", "failed"]


class EventPipelineState(WorkerSchema):
    """事件生产工作流状态。

    输入：LangGraph 各节点共享的 run、signal、candidate、dossier、review 和发布状态。
    输出：经过 Pydantic 校验的状态对象，用于节点之间传递和最终验收。
    """

    run_id: str | None = None
    run_key: str | None = None
    trigger_type: str = "manual"
    source_scope: dict[str, Any] = Field(default_factory=dict)
    signal_ids: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    dossier_id: str | None = None
    review_id: str | None = None
    review_decision: str | None = None
    published_event_id: str | None = None
    current_node: str = "initialized"
    revision_count: int = Field(default=0, ge=0, le=2)
    status: EventPipelineStatus = "initialized"
    errors: list[str] = Field(default_factory=list)
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)

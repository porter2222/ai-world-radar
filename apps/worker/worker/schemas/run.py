from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from worker.schemas.common import AgentRunStatus, PipelineRunStatus, WorkerSchema


class PipelineRunCreate(WorkerSchema):
    """pipeline 运行创建契约。

    输入：运行 key、触发类型、来源范围、初始状态和配置快照。
    输出：供 RunLogService 创建 PipelineRun 的结构化 payload。
    """

    run_key: str = Field(min_length=1, max_length=128)
    trigger_type: Literal["manual", "scheduled", "admin_retry"] = "manual"
    source_scope: dict[str, Any] = Field(default_factory=dict)
    status: PipelineRunStatus = "running"
    config_snapshot: dict[str, Any] = Field(default_factory=dict)


class AgentRunRecord(WorkerSchema):
    """Agent 运行记录契约。

    输入：pipeline_run_id、Agent 名称/角色、输入摘要、输出 JSON、trace 和状态。
    输出：供 RunLogService 写入 AgentRun 的结构化 payload。
    """

    pipeline_run_id: str = Field(min_length=1)
    candidate_id: str | None = None
    dossier_id: str | None = None
    agent_name: str = Field(min_length=1, max_length=128)
    agent_role: Literal["editor", "writer", "reviewer", "skill"]
    model_provider: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    input_summary: str = Field(min_length=1)
    output_json: dict[str, Any] = Field(default_factory=dict)
    trace_json: dict[str, Any] = Field(default_factory=dict)
    status: AgentRunStatus
    duration_ms: int | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)
    error_message: str | None = None

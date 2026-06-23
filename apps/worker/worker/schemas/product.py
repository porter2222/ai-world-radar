from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from worker.schemas.common import WorkerSchema


class ProductEventListItem(WorkerSchema):
    """前台事件列表项响应契约。

    输入：PublishedEvent 发布快照字段。
    输出：前台首页 / 事件雷达页可直接展示的事件卡片数据。
    """

    id: str
    slug: str
    title: str
    card_summary: str
    detail_summary: str
    category: str | None = None
    signal_label: str | None = None
    cover_image_url: str | None = None
    homepage_rank: int | None = None
    source_hint: str | None = None
    source_count: int = 0
    published_at: datetime


class ProductEventDetail(WorkerSchema):
    """前台事件详情响应契约。

    输入：PublishedEvent 发布快照和对应 EventDossier 发布版本。
    输出：事件详情页需要的正文、来源、影响说明和跟进点。
    """

    id: str
    slug: str
    title: str
    detail_summary: str
    detail_body: str
    why_it_matters: str
    follow_up_points: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    category: str | None = None
    signal_label: str | None = None
    cover_image_url: str | None = None
    published_at: datetime


class ProductPipelineRunItem(WorkerSchema):
    """后台 pipeline run 摘要响应契约。

    输入：PipelineRun ORM 字段。
    输出：后台运行列表和运行详情页可展示的计数与状态摘要。
    """

    id: str
    run_key: str
    trigger_type: str
    source_scope: dict[str, Any] = Field(default_factory=dict)
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    signals_count: int
    candidates_count: int
    dossiers_count: int
    published_count: int
    failed_count: int
    summary: str
    error_message: str | None = None


class ProductAgentRunItem(WorkerSchema):
    """后台 Agent run 摘要响应契约。

    输入：AgentRun ORM 字段和 trace_json 中的 token_usage。
    输出：后台审计页可展示的 Agent 运行摘要，不包含完整 LLM 原文。
    """

    id: str
    pipeline_run_id: str
    candidate_id: str | None = None
    dossier_id: str | None = None
    agent_name: str
    agent_role: str
    model_provider: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    status: str
    duration_ms: int | None = None
    retry_count: int
    token_usage: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime


class ManualReviewQueueItem(WorkerSchema):
    """后台人工审核队列项响应契约。

    输入：manual_review 状态的 EventCandidate、最新 EventDossier 和最新 ReviewResult。
    输出：后台人工审核队列的一行待处理事件。
    """

    candidate_id: str
    dossier_id: str
    review_id: str
    title: str
    category: str | None = None
    dossier_version: int
    risk_level: str
    issues: list[str] = Field(default_factory=list)
    revision_instructions: str
    updated_at: datetime

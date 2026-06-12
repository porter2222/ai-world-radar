from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from worker.schemas.common import EventDossierStatus, ReviewDecision, RiskLevel, WorkerSchema, score_field


class EventCandidateDraft(WorkerSchema):
    """候选事件草案契约。

    输入：候选事件 key、标题、分类、选题角度、评分和排序理由。
    输出：供 EventService 创建或更新 EventCandidate 的结构化 payload。
    """

    candidate_key: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1)
    event_type: str | None = Field(default=None, max_length=128)
    category: str | None = Field(default=None, max_length=128)
    primary_subject: str | None = Field(default=None, max_length=255)
    suggested_angle: str | None = None
    heat_score: float = score_field("外部热度分")
    importance_score: float = score_field("事件重要度分")
    audience_value_score: float = score_field("中文用户价值分")
    ranking_score: float = score_field("综合排序分")
    ranking_reason: str = Field(min_length=1)
    merge_reason: str | None = None


class EventDossierDraft(WorkerSchema):
    """事件档案草案契约。

    输入：首页卡片内容、详情内容、影响说明、跟进点和来源引用。
    输出：供 EventService 保存 EventDossier 版本的结构化 payload。
    """

    candidate_key: str = Field(min_length=1, max_length=255)
    card_title: str = Field(min_length=1)
    card_summary: str = Field(min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=128)
    signal_label: str | None = Field(default=None, max_length=128)
    cover_image_url: str | None = None
    detail_title: str = Field(min_length=1)
    detail_summary: str = Field(min_length=1)
    detail_body: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    follow_up_points: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    status: EventDossierStatus = "draft"


class ReviewResultDraft(WorkerSchema):
    """审稿结果草案契约。

    输入：审稿决策、风险等级、问题列表、修订说明和检查项。
    输出：供 EventService 保存 ReviewResult 并驱动 dossier 状态变化的结构化 payload。
    """

    decision: ReviewDecision
    risk_level: RiskLevel
    issues: list[str] = Field(default_factory=list)
    revision_instructions: str = ""
    checked_items: dict[str, Any] = Field(default_factory=dict)


class PublishEventCommand(WorkerSchema):
    """事件发布命令契约。

    输入：候选事件 ID、档案 ID 和发布模式。
    输出：供 EventService 创建 PublishedEvent 快照的结构化 command。
    """

    candidate_id: str = Field(min_length=1)
    dossier_id: str = Field(min_length=1)
    publish_mode: Literal["auto", "manual"] = "auto"

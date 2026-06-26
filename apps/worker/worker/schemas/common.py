from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkerSchema(BaseModel):
    """Worker Pydantic schema 基类。

    输入：各业务 schema 的字段数据。
    输出：禁止额外字段、自动去除字符串首尾空白的 Pydantic 模型。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


EventCandidateStatus = Literal[
    "new",
    "triaged",
    "merged",
    "drafting",
    "reviewing",
    "ready_to_publish",
    "published",
    "manual_review",
    "rejected",
    "failed",
    "hidden",
]
EventDossierStatus = Literal[
    "draft",
    "reviewing",
    "needs_revision",
    "approved",
    "manual_review",
    "rejected",
    "published_snapshot",
]
ReviewDecision = Literal["publish", "revise", "manual_review", "reject"]
RiskLevel = Literal["low", "medium", "high"]
PublishedEventStatus = Literal["published", "hidden", "hidden_duplicate", "archived"]
PipelineRunStatus = Literal["running", "succeeded", "partial_failed", "failed", "cancelled"]
AgentRunStatus = Literal["running", "succeeded", "failed"]


def score_field(description: str):
    """创建 0 到 100 的评分字段。

    输入：字段说明文本。
    输出：带默认值、最小值和最大值约束的 Pydantic Field。
    """
    return Field(default=0, ge=0, le=100, description=description)

from __future__ import annotations

from pydantic import Field

from worker.schemas.common import WorkerSchema


class EditorialSelectedItem(WorkerSchema):
    """LLM 编辑筛选选中项。

    输入：candidate group id、支撑 signal ids、事件标题、优先级分、选题角度和原因。
    输出：供后续 pipeline 决定是否进入写作的 selected 建议。
    """

    candidate_group_id: str = Field(min_length=1)
    signal_ids: list[str] = Field(min_length=1)
    event_title: str = Field(min_length=1)
    priority_score: float = Field(ge=0, le=100)
    suggested_angle: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class EditorialRejectedItem(WorkerSchema):
    """LLM 编辑筛选拒绝项。

    输入：candidate group id 和拒绝原因。
    输出：供审计记录和后续观察使用的 rejected 建议。
    """

    candidate_group_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class EditorialManualReviewItem(WorkerSchema):
    """LLM 编辑筛选人工复核项。

    输入：candidate group id 和需要人工确认的原因。
    输出：供后续人工队列或日志使用的 manual_review 建议。
    """

    candidate_group_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class EditorialSelectionResult(WorkerSchema):
    """LLM Editorial Selector 结构化输出。

    输入：LLM 返回的 selected、rejected 和 manual_review 三类列表。
    输出：通过 Pydantic 校验的编辑筛选建议；本 schema 不写库、不发布。
    """

    selected: list[EditorialSelectedItem] = Field(default_factory=list)
    rejected: list[EditorialRejectedItem] = Field(default_factory=list)
    manual_review: list[EditorialManualReviewItem] = Field(default_factory=list)

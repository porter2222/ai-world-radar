from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from worker.db.base import Base, TimestampMixin, new_id


class Source(Base, TimestampMixin):
    """信息源配置表。

    输入：来源 key、名称、类型、抓取方式、入口 URL 和抓取配置。
    输出：供 SourceSignal 关联和后续 source layer 调度使用。
    """

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("src"))
    source_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fetch_method: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_url: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    fetch_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(64))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    signals: Mapped[list["SourceSignal"]] = relationship(back_populates="source")


class SourceSignal(Base, TimestampMixin):
    """外部来源信号表。

    输入：来源 ID、原始标题/URL、内容摘要、source_hash、热度指标和 AI 预处理结果。
    输出：供候选事件归并、排序和溯源使用的最小信号单元。
    """

    __tablename__ = "source_signals"
    __table_args__ = (UniqueConstraint("source_id", "source_hash", name="uq_source_signals_source_hash"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("sig"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    pipeline_run_id: Mapped[str | None] = mapped_column(ForeignKey("pipeline_runs.id"))
    source_item_id: Mapped[str | None] = mapped_column(String(128))
    original_title: Mapped[str] = mapped_column(Text, nullable=False)
    original_url: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    language: Mapped[str | None] = mapped_column(String(32))
    raw_summary: Mapped[str | None] = mapped_column(Text)
    content_excerpt: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    content_cache_path: Mapped[str | None] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    heat_metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    ai_relevance: Mapped[float | None] = mapped_column(Float)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_category_hint: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="new")

    source: Mapped[Source] = relationship(back_populates="signals")


class EventCandidate(Base, TimestampMixin):
    """候选事件表。

    输入：候选事件 key、标题、分类、主体、选题角度、评分和状态。
    输出：供事件档案写作、审稿和发布快照引用。
    """

    __tablename__ = "event_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("cand"))
    candidate_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(128))
    primary_subject: Mapped[str | None] = mapped_column(String(255))
    suggested_angle: Mapped[str | None] = mapped_column(Text)
    heat_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    importance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    audience_value_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    ranking_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    ranking_reason: Mapped[str | None] = mapped_column(Text)
    merge_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="new")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_run_id: Mapped[str | None] = mapped_column(ForeignKey("pipeline_runs.id"))


class EventCandidateSignal(Base):
    """候选事件与来源信号关联表。

    输入：candidate_id、signal_id、关系类型、合并置信度和合并原因。
    输出：记录一个候选事件由哪些 SourceSignal 支撑。
    """

    __tablename__ = "event_candidate_signals"
    __table_args__ = (UniqueConstraint("candidate_id", "signal_id", name="uq_event_candidate_signal"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ecs"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("event_candidates.id"), nullable=False)
    signal_id: Mapped[str] = mapped_column(ForeignKey("source_signals.id"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, default="primary")
    merge_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    merge_reason: Mapped[str | None] = mapped_column(Text)
    added_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventDossier(Base, TimestampMixin):
    """事件档案版本表。

    输入：候选事件 ID、版本、卡片内容、详情正文、影响说明和来源引用。
    输出：供审稿和发布快照使用的事件档案版本。
    """

    __tablename__ = "event_dossiers"
    __table_args__ = (UniqueConstraint("candidate_id", "version", name="uq_event_dossiers_candidate_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("dos"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("event_candidates.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft")
    card_title: Mapped[str] = mapped_column(Text, nullable=False)
    card_summary: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(128))
    signal_label: Mapped[str | None] = mapped_column(String(128))
    cover_image_url: Mapped[str | None] = mapped_column(Text)
    detail_title: Mapped[str] = mapped_column(Text, nullable=False)
    detail_summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail_body: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    follow_up_points: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    generated_by_agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    generated_by_run_id: Mapped[str | None] = mapped_column(ForeignKey("pipeline_runs.id"))


class ReviewResult(Base):
    """审稿结果表。

    输入：dossier_id、candidate_id、审稿决策、风险等级、问题和检查项。
    输出：驱动 EventDossier 状态和 PublishedEvent 发布资格。
    """

    __tablename__ = "review_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rev"))
    dossier_id: Mapped[str] = mapped_column(ForeignKey("event_dossiers.id"), nullable=False)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("event_candidates.id"), nullable=False)
    pipeline_run_id: Mapped[str | None] = mapped_column(ForeignKey("pipeline_runs.id"))
    reviewer_agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(64), nullable=False)
    issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    revision_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checked_items: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublishedEvent(Base, TimestampMixin):
    """已发布事件快照表。

    输入：候选事件、事件档案、发布标题/摘要/正文、分类和来源引用。
    输出：供前台首页和详情页稳定读取的发布快照。
    """

    __tablename__ = "published_events"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_published_events_candidate"),
        UniqueConstraint("slug", name="uq_published_events_slug"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pub"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("event_candidates.id"), nullable=False)
    dossier_id: Mapped[str] = mapped_column(ForeignKey("event_dossiers.id"), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    published_title: Mapped[str] = mapped_column(Text, nullable=False)
    published_card_summary: Mapped[str] = mapped_column(Text, nullable=False)
    published_detail_summary: Mapped[str] = mapped_column(Text, nullable=False)
    published_detail_body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(128))
    signal_label: Mapped[str | None] = mapped_column(String(128))
    cover_image_url: Mapped[str | None] = mapped_column(Text)
    source_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    homepage_rank: Mapped[int | None] = mapped_column(Integer)
    ranking_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="published")
    publish_mode: Mapped[str] = mapped_column(String(64), nullable=False, default="auto")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PipelineRun(Base, TimestampMixin):
    """pipeline 运行记录表。

    输入：运行 key、触发类型、来源范围、计数、摘要、错误和配置快照。
    输出：供后台监控和审计一次 pipeline 运行。
    """

    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("run"))
    run_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    source_scope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signals_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidates_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dossiers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class AgentRun(Base, TimestampMixin):
    """Agent 运行记录表。

    输入：pipeline/candidate/dossier 关联、Agent 信息、输入摘要、输出 JSON、trace 和状态。
    输出：供后台查看 Agent 运行过程和后续 tool_calls 拆表依据。
    """

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("arun"))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("event_candidates.id"))
    dossier_id: Mapped[str | None] = mapped_column(String(64))
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_role: Mapped[str] = mapped_column(String(64), nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(64))
    model_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    input_summary: Mapped[str] = mapped_column(Text, nullable=False)
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    trace_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)


class AdminAction(Base):
    """后台管理员操作审计表。

    输入：操作人、动作、目标对象、原因、前后快照和执行状态。
    输出：供后续后台管理追踪人工修正行为。
    """

    __tablename__ = "admin_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("admin"))
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    before_snapshot: Mapped[dict | None] = mapped_column(JSON)
    after_snapshot: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

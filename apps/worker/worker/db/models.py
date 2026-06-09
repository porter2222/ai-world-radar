from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id(prefix: str) -> str:
    """生成带业务前缀的唯一 ID。

    输入：ID 前缀，例如 `run`、`ev`、`cluster`。
    输出：形如 `prefix_uuidhex` 的字符串。
    """
    return f"{prefix}_{uuid.uuid4().hex}"


class Base(DeclarativeBase):
    """SQLAlchemy declarative base。

    输入：无。
    输出：所有 ORM model 共享的 metadata 容器。
    """

    pass


class TimestampMixin:
    """通用时间戳 mixin。

    输入：无。
    输出：为继承模型提供 `created_at` 和 `updated_at` 字段。
    """

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Source(Base, TimestampMixin):
    """信息源配置表。

    输入：来源类型、入口 URL、权重和状态。
    输出：供 pipeline 判断启用来源和写入 EvidenceCard 关联。
    """

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fetch_method: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    discovery_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    heat_signal_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    impact_signal_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    language: Mapped[str | None] = mapped_column(String(32))
    category_hint: Mapped[str | None] = mapped_column(String(128))
    fetch_interval: Mapped[str | None] = mapped_column(String(64))
    capabilities: Mapped[dict | None] = mapped_column(JSON)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(64))
    failure_reason: Mapped[str | None] = mapped_column(Text)


class PipelineRun(Base):
    """pipeline 运行记录表。

    输入：每次运行的参数、状态、计数和错误摘要。
    输出：用于审计本地命令运行结果。
    """

    __tablename__ = "pipeline_runs"

    pipeline_run_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("run"))
    run_type: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    triggered_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_card_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_cluster_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_artifact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_step: Mapped[str | None] = mapped_column(String(128))
    error_summary: Mapped[str | None] = mapped_column(Text)
    model_usage: Mapped[dict | None] = mapped_column(JSON)
    config_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EvidenceCard(Base, TimestampMixin):
    """证据卡表。

    输入：HN 原始信号、原文缓存指针和 Agent stub 理解结果。
    输出：供事件聚合、排序和写作使用的内部证据单元。
    """

    __tablename__ = "evidence_cards"
    __table_args__ = (UniqueConstraint("source_id", "source_item_id", "prompt_version", name="uq_evidence_source_item_prompt"),)

    evidence_card_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ev"))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.pipeline_run_id"), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_type: Mapped[str] = mapped_column(String(64), nullable=False, default="post")
    original_title: Mapped[str] = mapped_column(Text, nullable=False)
    original_url: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_summary: Mapped[str | None] = mapped_column(Text)
    raw_excerpt: Mapped[str | None] = mapped_column(Text)
    raw_heat_metrics: Mapped[dict | None] = mapped_column(JSON)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)
    page_title: Mapped[str | None] = mapped_column(Text)
    page_excerpt: Mapped[str | None] = mapped_column(Text)
    page_text_hash: Mapped[str | None] = mapped_column(String(128))
    page_cache_path: Mapped[str | None] = mapped_column(Text)
    page_fetch_status: Mapped[str | None] = mapped_column(String(64))
    claim_summary: Mapped[str | None] = mapped_column(Text)
    normalized_title: Mapped[str | None] = mapped_column(Text)
    subjects: Mapped[list | None] = mapped_column(JSON)
    event_trigger: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(128))
    heat_clues: Mapped[list | None] = mapped_column(JSON)
    impact_clues: Mapped[list | None] = mapped_column(JSON)
    audience_value_reason: Mapped[str | None] = mapped_column(Text)
    suggested_route: Mapped[str | None] = mapped_column(String(128))
    candidate_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    candidate_reason: Mapped[str | None] = mapped_column(Text)
    merge_key_hint: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(255))
    content_hash: Mapped[str | None] = mapped_column(String(128))
    url_hash: Mapped[str | None] = mapped_column(String(128))
    model_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, default="stub-v1")
    card_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1")
    processing_status: Mapped[str] = mapped_column(String(64), nullable=False, default="processed")
    discard_reason: Mapped[str | None] = mapped_column(Text)


class EventCluster(Base, TimestampMixin):
    """内部事件聚合表。

    输入：EvidenceCard 聚合后的主体、触发点、分数和发布决策。
    输出：供内容生成和 PublishedEvent 发布使用。
    """

    __tablename__ = "event_clusters"
    __table_args__ = (UniqueConstraint("event_key", name="uq_event_clusters_event_key"),)

    event_cluster_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("cluster"))
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.pipeline_run_id"), nullable=False)
    last_seen_pipeline_run_id: Mapped[str | None] = mapped_column(ForeignKey("pipeline_runs.pipeline_run_id"))
    title_hint: Mapped[str] = mapped_column(Text, nullable=False)
    summary_hint: Mapped[str | None] = mapped_column(Text)
    primary_subject: Mapped[str | None] = mapped_column(String(255))
    subjects: Mapped[list | None] = mapped_column(JSON)
    event_trigger: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(128))
    merge_key: Mapped[str | None] = mapped_column(Text)
    heat_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    impact_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    audience_value_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ranking_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ranking_reason: Mapped[str | None] = mapped_column(Text)
    evidence_card_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event_time_hint: Mapped[str | None] = mapped_column(Text)
    cluster_status: Mapped[str] = mapped_column(String(64), nullable=False, default="new")
    publish_decision: Mapped[str] = mapped_column(String(64), nullable=False, default="hold")
    brief_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    planning_reason: Mapped[str | None] = mapped_column(Text)

    evidence_cards: Mapped[list["EventClusterCard"]] = relationship(back_populates="event_cluster")


class EventClusterCard(Base):
    """事件与证据卡关联表。

    输入：EventCluster ID、EvidenceCard ID 和合并原因。
    输出：记录一个事件由哪些证据支撑。
    """

    __tablename__ = "event_cluster_cards"
    __table_args__ = (UniqueConstraint("event_cluster_id", "evidence_card_id", name="uq_cluster_evidence_card"),)

    event_cluster_card_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ecc"))
    event_cluster_id: Mapped[str] = mapped_column(ForeignKey("event_clusters.event_cluster_id"), nullable=False)
    evidence_card_id: Mapped[str] = mapped_column(ForeignKey("evidence_cards.evidence_card_id"), nullable=False)
    signal_role: Mapped[str] = mapped_column(String(64), nullable=False, default="primary_signal")
    merge_reason: Mapped[str | None] = mapped_column(Text)
    added_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    event_cluster: Mapped[EventCluster] = relationship(back_populates="evidence_cards")


class ContentArtifact(Base, TimestampMixin):
    """内容产物表。

    输入：事件卡、详情页或 brief item 的生成内容。
    输出：供发布事件和简报引用的内容版本。
    """

    __tablename__ = "content_artifacts"

    content_artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("artifact"))
    event_cluster_id: Mapped[str] = mapped_column(ForeignKey("event_clusters.event_cluster_id"), nullable=False)
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.pipeline_run_id"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    body_format: Mapped[str] = mapped_column(String(64), nullable=False, default="markdown")
    cover_image_url: Mapped[str | None] = mapped_column(Text)
    evidence_card_ids: Mapped[list | None] = mapped_column(JSON)
    source_refs: Mapped[list | None] = mapped_column(JSON)
    generation_reason: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    generation_params: Mapped[dict | None] = mapped_column(JSON)


class QualityGateResult(Base):
    """质量门禁结果表。

    输入：内容产物的检查结果、失败原因和建议动作。
    输出：决定内容是否进入 PublishedEvent。
    """

    __tablename__ = "quality_gate_results"

    quality_gate_result_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("qg"))
    content_artifact_id: Mapped[str] = mapped_column(ForeignKey("content_artifacts.content_artifact_id"), nullable=False)
    event_cluster_id: Mapped[str] = mapped_column(ForeignKey("event_clusters.event_cluster_id"), nullable=False)
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.pipeline_run_id"), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(64), nullable=False, default="stub-v1")
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    check_results: Mapped[dict | None] = mapped_column(JSON)
    fail_reasons: Mapped[list | None] = mapped_column(JSON)
    warning_messages: Mapped[list | None] = mapped_column(JSON)
    recommended_action: Mapped[str] = mapped_column(String(64), nullable=False)
    checked_by: Mapped[str] = mapped_column(String(64), nullable=False, default="code")
    model_name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublishedEvent(Base, TimestampMixin):
    """公开发布事件表。

    输入：通过质量门禁的 card/detail 内容产物。
    输出：后续 Next.js 前台可查询展示的事件。
    """

    __tablename__ = "published_events"
    __table_args__ = (
        UniqueConstraint("event_cluster_id", name="uq_published_event_cluster"),
        UniqueConstraint("slug", name="uq_published_events_slug"),
    )

    published_event_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pub"))
    event_cluster_id: Mapped[str] = mapped_column(ForeignKey("event_clusters.event_cluster_id"), nullable=False)
    card_artifact_id: Mapped[str] = mapped_column(ForeignKey("content_artifacts.content_artifact_id"), nullable=False)
    detail_artifact_id: Mapped[str] = mapped_column(ForeignKey("content_artifacts.content_artifact_id"), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    display_title: Mapped[str] = mapped_column(Text, nullable=False)
    display_summary: Mapped[str | None] = mapped_column(Text)
    cover_image_url: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(128))
    publish_status: Mapped[str] = mapped_column(String(64), nullable=False, default="published")
    visibility: Mapped[str] = mapped_column(String(64), nullable=False, default="public")
    published_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    first_published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    homepage_rank: Mapped[int | None] = mapped_column(Integer)
    ranking_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_ranked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_note: Mapped[str | None] = mapped_column(Text)


class Brief(Base, TimestampMixin):
    """每日简报主表。

    输入：简报标题、概览、版本和运行批次。
    输出：简报条目的父记录。
    """

    __tablename__ = "briefs"
    __table_args__ = (UniqueConstraint("brief_date", "version", name="uq_briefs_date_version"),)

    brief_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("brief"))
    brief_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    overview: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="published")
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.pipeline_run_id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BriefItem(Base, TimestampMixin):
    """每日简报条目表。

    输入：简报 ID、已发布事件 ID 和 brief 内容产物 ID。
    输出：保证每条简报都能关联回 PublishedEvent。
    """

    __tablename__ = "brief_items"
    __table_args__ = (UniqueConstraint("brief_id", "published_event_id", name="uq_brief_published_event"),)

    brief_item_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("brief_item"))
    brief_id: Mapped[str] = mapped_column(ForeignKey("briefs.brief_id"), nullable=False)
    published_event_id: Mapped[str] = mapped_column(ForeignKey("published_events.published_event_id"), nullable=False)
    brief_artifact_id: Mapped[str] = mapped_column(ForeignKey("content_artifacts.content_artifact_id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String(128))
    highlight_reason: Mapped[str | None] = mapped_column(Text)


class AdminAction(Base):
    """管理员操作审计表。

    输入：操作人、动作、目标对象和前后快照。
    输出：供后续管理页追踪人工操作。
    """

    __tablename__ = "admin_actions"

    admin_action_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("admin"))
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    before_snapshot: Mapped[dict | None] = mapped_column(JSON)
    after_snapshot: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text)
    related_job_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

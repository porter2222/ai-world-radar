"""create event dossier core tables

Revision ID: 202606120001
Revises:
Create Date: 2026-06-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202606120001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 P1-1 事件档案数据底座核心表。

    输入：当前 Alembic 数据库连接。
    输出：创建 SourceSignal 到 PublishedEvent 链路所需的 10 张核心表。
    """
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("fetch_method", sa.String(length=64), nullable=False),
        sa.Column("entry_url", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("default_weight", sa.Float(), nullable=False),
        sa.Column("fetch_config", sa.JSON(), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True)),
        sa.Column("last_status", sa.String(length=64)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("source_scope", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("signals_count", sa.Integer(), nullable=False),
        sa.Column("candidates_count", sa.Integer(), nullable=False),
        sa.Column("dossiers_count", sa.Integer(), nullable=False),
        sa.Column("published_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "event_candidates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("candidate_key", sa.String(length=255), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(length=128)),
        sa.Column("category", sa.String(length=128)),
        sa.Column("primary_subject", sa.String(length=255)),
        sa.Column("suggested_angle", sa.Text()),
        sa.Column("heat_score", sa.Float(), nullable=False),
        sa.Column("importance_score", sa.Float(), nullable=False),
        sa.Column("audience_value_score", sa.Float(), nullable=False),
        sa.Column("ranking_score", sa.Float(), nullable=False),
        sa.Column("ranking_reason", sa.Text()),
        sa.Column("merge_reason", sa.Text()),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_run_id", sa.String(length=64), sa.ForeignKey("pipeline_runs.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "source_signals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_id", sa.String(length=64), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=64), sa.ForeignKey("pipeline_runs.id")),
        sa.Column("source_item_id", sa.String(length=128)),
        sa.Column("original_title", sa.Text(), nullable=False),
        sa.Column("original_url", sa.Text()),
        sa.Column("canonical_url", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("language", sa.String(length=32)),
        sa.Column("raw_summary", sa.Text()),
        sa.Column("content_excerpt", sa.Text()),
        sa.Column("content_hash", sa.String(length=128)),
        sa.Column("content_cache_path", sa.Text()),
        sa.Column("source_hash", sa.String(length=255), nullable=False),
        sa.Column("heat_metrics", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("ai_relevance", sa.Float()),
        sa.Column("ai_summary", sa.Text()),
        sa.Column("ai_category_hint", sa.String(length=128)),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_id", "source_hash", name="uq_source_signals_source_hash"),
    )
    op.create_table(
        "event_candidate_signals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("candidate_id", sa.String(length=64), sa.ForeignKey("event_candidates.id"), nullable=False),
        sa.Column("signal_id", sa.String(length=64), sa.ForeignKey("source_signals.id"), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("merge_confidence", sa.Float(), nullable=False),
        sa.Column("merge_reason", sa.Text()),
        sa.Column("added_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("candidate_id", "signal_id", name="uq_event_candidate_signal"),
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(length=64), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("candidate_id", sa.String(length=64), sa.ForeignKey("event_candidates.id")),
        sa.Column("dossier_id", sa.String(length=64)),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("agent_role", sa.String(length=64), nullable=False),
        sa.Column("model_provider", sa.String(length=64)),
        sa.Column("model_name", sa.String(length=128)),
        sa.Column("prompt_version", sa.String(length=64)),
        sa.Column("input_summary", sa.Text(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("trace_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "event_dossiers",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("candidate_id", sa.String(length=64), sa.ForeignKey("event_candidates.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("card_title", sa.Text(), nullable=False),
        sa.Column("card_summary", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=128)),
        sa.Column("signal_label", sa.String(length=128)),
        sa.Column("cover_image_url", sa.Text()),
        sa.Column("detail_title", sa.Text(), nullable=False),
        sa.Column("detail_summary", sa.Text(), nullable=False),
        sa.Column("detail_body", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("follow_up_points", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("generated_by_agent_run_id", sa.String(length=64), sa.ForeignKey("agent_runs.id")),
        sa.Column("generated_by_run_id", sa.String(length=64), sa.ForeignKey("pipeline_runs.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("candidate_id", "version", name="uq_event_dossiers_candidate_version"),
    )
    op.create_table(
        "review_results",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("dossier_id", sa.String(length=64), sa.ForeignKey("event_dossiers.id"), nullable=False),
        sa.Column("candidate_id", sa.String(length=64), sa.ForeignKey("event_candidates.id"), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=64), sa.ForeignKey("pipeline_runs.id")),
        sa.Column("reviewer_agent_run_id", sa.String(length=64), sa.ForeignKey("agent_runs.id")),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=64), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("revision_instructions", sa.Text(), nullable=False),
        sa.Column("checked_items", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "published_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("candidate_id", sa.String(length=64), sa.ForeignKey("event_candidates.id"), nullable=False),
        sa.Column("dossier_id", sa.String(length=64), sa.ForeignKey("event_dossiers.id"), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("published_title", sa.Text(), nullable=False),
        sa.Column("published_card_summary", sa.Text(), nullable=False),
        sa.Column("published_detail_summary", sa.Text(), nullable=False),
        sa.Column("published_detail_body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=128)),
        sa.Column("signal_label", sa.String(length=128)),
        sa.Column("cover_image_url", sa.Text()),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("homepage_rank", sa.Integer()),
        sa.Column("ranking_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("publish_mode", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("candidate_id", name="uq_published_events_candidate"),
        sa.UniqueConstraint("slug", name="uq_published_events_slug"),
    )
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("operator", sa.String(length=128), nullable=False),
        sa.Column("action_type", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=128), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("before_snapshot", sa.JSON()),
        sa.Column("after_snapshot", sa.JSON()),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    """按依赖反序删除 P1-1 核心表。

    输入：当前 Alembic 数据库连接。
    输出：删除本 migration 创建的 10 张核心表。
    """
    op.drop_table("admin_actions")
    op.drop_table("published_events")
    op.drop_table("review_results")
    op.drop_table("event_dossiers")
    op.drop_table("agent_runs")
    op.drop_table("event_candidate_signals")
    op.drop_table("source_signals")
    op.drop_table("event_candidates")
    op.drop_table("pipeline_runs")
    op.drop_table("sources")

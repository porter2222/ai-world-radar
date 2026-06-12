from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from worker.schemas.event import EventCandidateDraft, EventDossierDraft, PublishEventCommand, ReviewResultDraft
from worker.schemas.run import AgentRunRecord, PipelineRunCreate
from worker.schemas.source import SourceSignalCreate


def test_source_signal_requires_source_hash_and_title():
    """验证 SourceSignalCreate 接收来源哈希和标题。

    输入：HN 风格来源、标题、URL、发布时间、摘要、source_hash 和热度指标。
    输出：schema 校验后的 source_hash 与 heat_metrics 保持可读可用。
    """
    signal = SourceSignalCreate(
        source_key="hn_algolia",
        source_item_id="123",
        original_title="OpenAI releases a new model",
        original_url="https://example.com/openai-model",
        canonical_url="https://example.com/openai-model",
        published_at=datetime(2026, 6, 12, tzinfo=UTC),
        raw_summary="HN discussion about a new OpenAI model.",
        source_hash="hn_algolia:123",
        heat_metrics={"points": 245, "comments": 88},
    )

    assert signal.source_hash == "hn_algolia:123"
    assert signal.heat_metrics["points"] == 245


def test_source_signal_rejects_empty_title():
    """验证 SourceSignalCreate 拒绝空标题。

    输入：空 original_title 的来源信号。
    输出：Pydantic ValidationError。
    """
    with pytest.raises(ValidationError):
        SourceSignalCreate(
            source_key="hn_algolia",
            source_item_id="123",
            original_title="",
            source_hash="hn_algolia:123",
        )


def test_event_candidate_score_range():
    """验证 EventCandidateDraft 接收 0 到 100 的排序分。

    输入：候选事件标题、分类、角度和四类评分。
    输出：schema 保留 ranking_score。
    """
    candidate = EventCandidateDraft(
        candidate_key="openai-new-model",
        title="OpenAI 新模型引发开发者讨论",
        category="模型与产品",
        suggested_angle="解释这次模型更新对开发者工具链的影响",
        heat_score=82,
        importance_score=90,
        audience_value_score=76,
        ranking_score=85,
        ranking_reason="HN 热度较高，且来自重要 AI 公司相关消息。",
    )

    assert candidate.ranking_score == 85


def test_event_candidate_rejects_score_over_100():
    """验证 EventCandidateDraft 拒绝超过 100 的分数。

    输入：heat_score 为 101 的候选事件。
    输出：Pydantic ValidationError。
    """
    with pytest.raises(ValidationError):
        EventCandidateDraft(
            candidate_key="bad-score",
            title="异常分数事件",
            heat_score=101,
            importance_score=50,
            audience_value_score=50,
            ranking_score=50,
            ranking_reason="bad score",
        )


def test_event_dossier_contains_card_and_detail_content():
    """验证 EventDossierDraft 同时包含卡片和详情内容。

    输入：首页卡片字段、详情页字段、影响说明、跟进点和来源引用。
    输出：schema 保留卡片标题和 follow_up_points。
    """
    dossier = EventDossierDraft(
        candidate_key="openai-new-model",
        card_title="OpenAI 新模型引发开发者讨论",
        card_summary="开发者关注其能力、价格和工具链影响。",
        category="模型与产品",
        signal_label="高热讨论",
        detail_title="OpenAI 新模型为什么引发开发者关注",
        detail_summary="这次讨论集中在模型能力、调用成本和开发者工具集成。",
        detail_body="这是一段面向中文用户的事件解释正文，说明背景、变化和可能影响。",
        why_it_matters="它可能影响 AI 编程工具和应用开发成本。",
        follow_up_points=["是否开放 API", "是否影响现有工具价格"],
        source_refs=[{"title": "HN discussion", "url": "https://news.ycombinator.com/item?id=123"}],
    )

    assert dossier.card_title == "OpenAI 新模型引发开发者讨论"
    assert dossier.follow_up_points == ["是否开放 API", "是否影响现有工具价格"]


def test_review_result_decision_is_limited():
    """验证 ReviewResultDraft 的决策枚举。

    输入：publish 决策、低风险、检查项。
    输出：schema 保留合法 decision。
    """
    review = ReviewResultDraft(
        decision="publish",
        risk_level="low",
        issues=[],
        revision_instructions="",
        checked_items={"has_sources": True, "not_copying_source": True},
    )

    assert review.decision == "publish"


def test_publish_command_requires_dossier_id():
    """验证发布命令必须包含 dossier_id。

    输入：candidate_id、dossier_id 和 auto 发布模式。
    输出：schema 保留 publish_mode。
    """
    command = PublishEventCommand(
        candidate_id="cand_1",
        dossier_id="dos_1",
        publish_mode="auto",
    )

    assert command.publish_mode == "auto"


def test_pipeline_and_agent_run_schema():
    """验证 PipelineRunCreate 与 AgentRunRecord 的运行记录契约。

    输入：一次手动 pipeline run 和一次编辑 Agent 运行记录。
    输出：schema 保留 trigger_type 与 agent_role。
    """
    pipeline = PipelineRunCreate(
        run_key="manual-20260612-001",
        trigger_type="manual",
        source_scope={"sources": ["hn_algolia"]},
    )
    agent_run = AgentRunRecord(
        pipeline_run_id="run_1",
        agent_name="值班编辑 Agent",
        agent_role="editor",
        status="succeeded",
        input_summary="3 条 HN signals",
        output_json={"candidate_count": 1},
    )

    assert pipeline.trigger_type == "manual"
    assert agent_run.agent_role == "editor"

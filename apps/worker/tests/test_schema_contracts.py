from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from worker.schemas.event import EventCandidateDraft, EventDossierDraft, PublishEventCommand, ReviewResultDraft
from worker.schemas.run import AgentRunRecord, PipelineRunCreate
from worker.schemas.source import SourceSignalCreate


def rich_detail_body() -> str:
    """构造信息密度足够的事件详情正文。

    输入：无。
    输出：至少五段、聚焦事件本身的详情正文。
    """
    return (
        "OpenAI 式 coding agents 的讨论把 AI 编程工具重新推到软件工程流程的中心。"
        "这类工具不再只被理解为自动补全或问答助手，而是被放进需求拆解、代码修改、测试运行和结果复核等连续任务中讨论。\n\n"
        "它被关注的原因在于，开发者日常工作包含大量跨文件理解和反复验证。"
        "如果 Agent 能理解项目上下文、遵守现有代码约定并解释修改原因，它就可能从单点辅助工具变成团队工作流中的协作层。\n\n"
        "讨论焦点集中在真实项目里的可靠性。开发者关心它能不能处理迁移脚本、测试补全、问题定位和代码审查辅助，"
        "也关心它是否会在复杂依赖、旧代码和模糊需求下给出难以维护的改动。\n\n"
        "不同观点之间的分歧很清楚。乐观者看重效率提升和小团队产能，谨慎者更担心错误代码、上下文误读、权限边界和审查负担。"
        "这种分歧说明 Agent 的价值不只取决于模型能力，还取决于它如何进入工程制度和质量控制流程。\n\n"
        "对中文开发者来说，这件事提示了一个具体方向：AI 编程工具的竞争可能从演示能力转向可验证的工作流能力。"
        "后续更值得关注的是团队试点案例、测试自动化配套、代码审查方式变化，以及工具是否能稳定嵌入真实研发流程。"
        "这些进展会直接影响开发者学习重点和团队引入新工具时的风险控制方式。"
    )


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
        detail_body=rich_detail_body(),
        why_it_matters="它可能影响 AI 编程工具和应用开发成本。",
        follow_up_points=["是否开放 API", "是否影响现有工具价格"],
        source_refs=[{"title": "HN discussion", "url": "https://news.ycombinator.com/item?id=123"}],
    )

    assert dossier.card_title == "OpenAI 新模型引发开发者讨论"
    assert dossier.follow_up_points == ["是否开放 API", "是否影响现有工具价格"]


def test_event_dossier_rejects_thin_detail_body():
    """验证详情正文不能只是低信息量短摘要。

    输入：只有三段、信息量不足的 detail_body。
    输出：Pydantic ValidationError，避免低质量正文进入发布链路。
    """
    with pytest.raises(ValidationError):
        EventDossierDraft(
            candidate_key="openai-new-model",
            card_title="OpenAI 新模型引发开发者讨论",
            card_summary="开发者关注其能力、价格和工具链影响。",
            category="模型与产品",
            signal_label="高热讨论",
            detail_title="OpenAI 新模型为什么引发开发者关注",
            detail_summary="这次讨论集中在模型能力、调用成本和开发者工具集成。",
            detail_body=(
                "发生了什么：HN 上开发者正在讨论 OpenAI 新编码 Agent。\n\n"
                "为什么重要：编码 Agent 可能改变开发者使用 AI 工具的方式。\n\n"
                "后续看什么：观察官方说明、API 能力和社区反馈。"
            ),
            why_it_matters="它可能影响 AI 编程工具和应用开发成本。",
            follow_up_points=["是否开放 API", "是否影响现有工具价格"],
            source_refs=[{"title": "HN discussion", "url": "https://news.ycombinator.com/item?id=123"}],
        )


def test_event_dossier_rejects_internal_process_language_in_detail_body():
    """验证详情正文不能暴露后台流程或热度指标语言。

    输入：长度和段落数达标、但包含“候选事件 / 来源信号 / comments”等后台词的 detail_body。
    输出：Pydantic ValidationError，避免工程过程语言出现在用户详情页。
    """
    body = rich_detail_body().replace(
        "OpenAI 式 coding agents 的讨论把 AI 编程工具重新推到软件工程流程的中心",
        "此次候选事件来自来源信号，Hacker News 上该讨论获得 512 points 和 186 comments",
    )
    with pytest.raises(ValidationError):
        EventDossierDraft(
            candidate_key="openai-new-model",
            card_title="OpenAI 新模型引发开发者讨论",
            card_summary="开发者关注其能力、价格和工具链影响。",
            category="模型与产品",
            signal_label="高热讨论",
            detail_title="OpenAI 新模型为什么引发开发者关注",
            detail_summary="这次讨论集中在模型能力、调用成本和开发者工具集成。",
            detail_body=body,
            why_it_matters="它可能影响 AI 编程工具和应用开发成本。",
            follow_up_points=["是否开放 API", "是否影响现有工具价格"],
            source_refs=[{"title": "HN discussion", "url": "https://news.ycombinator.com/item?id=123"}],
        )


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

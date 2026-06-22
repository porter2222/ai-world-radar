from worker.agents.event_pipeline_agents import (
    OnDutyEditorAgentStub,
    ResearchWriterAgentStub,
    ReviewPublisherAgentStub,
)
from worker.schemas.event import EventCandidateDraft, EventDossierDraft, ReviewResultDraft


def sample_signal():
    """创建 Agent stub 测试用来源信号。

    输入：无。
    输出：包含标题、URL、摘要和热度指标的 dict。
    """
    return {
        "id": "sig_1",
        "source_key": "demo",
        "original_title": "OpenAI releases a new developer tool",
        "original_url": "https://example.com/openai-tool",
        "raw_summary": "Developers discuss the new tool and pricing.",
        "heat_metrics": {"points": 120, "comments": 45},
    }


def test_editor_stub_returns_candidate_draft():
    """验证值班编辑 stub 输出候选事件 schema。

    输入：一条来源信号 dict。
    输出：EventCandidateDraft，包含 candidate_key、标题和评分。
    """
    result = OnDutyEditorAgentStub().triage([sample_signal()])

    assert isinstance(result, EventCandidateDraft)
    assert result.candidate_key == "demo-openai-releases-a-new-developer-tool"
    assert result.ranking_score > 0


def test_writer_stub_returns_dossier_draft_with_source_refs():
    """验证研究写作 stub 输出事件档案 schema。

    输入：候选事件草案和来源信号列表。
    输出：EventDossierDraft，包含中文卡片、详情正文和 source_refs。
    """
    candidate = OnDutyEditorAgentStub().triage([sample_signal()])
    result = ResearchWriterAgentStub().draft(candidate, [sample_signal()])

    assert isinstance(result, EventDossierDraft)
    assert result.candidate_key == candidate.candidate_key
    assert result.source_refs[0]["url"] == "https://example.com/openai-tool"
    assert "中文用户" in result.why_it_matters


def test_writer_stub_detail_body_is_reader_facing():
    """验证 stub 详情正文不包含后台流程和热度指标话术。

    输入：候选事件草案和来源信号列表。
    输出：detail_body 聚焦事件本身，不出现候选事件、来源信号、来源边界、points/comments 等词。
    """
    candidate = OnDutyEditorAgentStub().triage([sample_signal()])
    result = ResearchWriterAgentStub().draft(candidate, [sample_signal()])

    banned_terms = [
        "候选事件",
        "输入信号",
        "来源信号",
        "来源边界",
        "P1 阶段",
        "points",
        "comments",
        "hn_heat_score",
    ]
    for term in banned_terms:
        assert term not in result.detail_body


def test_reviewer_stub_returns_publish_review_for_complete_dossier():
    """验证审稿发布 stub 对完整 dossier 给出发布建议。

    输入：完整事件档案草案。
    输出：ReviewResultDraft，decision 为 publish 且风险为 low。
    """
    candidate = OnDutyEditorAgentStub().triage([sample_signal()])
    dossier = ResearchWriterAgentStub().draft(candidate, [sample_signal()])
    result = ReviewPublisherAgentStub().review(dossier, revision_count=0)

    assert isinstance(result, ReviewResultDraft)
    assert result.decision == "publish"
    assert result.risk_level == "low"

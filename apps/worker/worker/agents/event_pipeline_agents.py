from __future__ import annotations

import re
from typing import Any

from worker.schemas.event import EventCandidateDraft, EventDossierDraft, ReviewResultDraft


def _first_signal(signals: list[dict[str, Any]]) -> dict[str, Any]:
    """读取第一个来源信号。

    输入：来源信号 dict 列表。
    输出：第一个信号 dict；列表为空时抛出 ValueError。
    """
    if not signals:
        raise ValueError("At least one source signal is required")
    return signals[0]


def _slugify(value: str) -> str:
    """把标题归一化为稳定 key 片段。

    输入：任意标题字符串。
    输出：小写、短横线连接的 ASCII key 片段。
    """
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


def _bounded_score(value: float) -> float:
    """把分数限制在 0 到 100。

    输入：任意数值分数。
    输出：符合 P1 schema 范围的浮点分。
    """
    return max(0.0, min(100.0, float(value)))


def _rich_stub_detail_body(summary: str, revision_note: str) -> str:
    """生成信息密度足够的 stub 详情正文。

    输入：来源摘要和可选审稿修订说明。
    输出：至少五段、满足 EventDossierDraft 详情质量要求的正文。
    """
    return (
        f"来源信号显示：{summary} 这说明 AI 圈或开发者社区正在围绕该主题形成讨论，值得被整理成事件档案。"
        "P1 阶段优先记录这种正在升温的讨论，但不会把它直接改写成官方已经确认的事实。\n\n"
        "这类事件通常需要先解释背景和触发点：相关模型、产品、工具或开源项目为什么突然被关注，"
        "它和开发者工作流、模型使用成本、产品能力边界或行业采用节奏之间有什么关系。\n\n"
        "详情页还需要呈现讨论焦点，而不只是复述标题。用户需要知道社区正在关心哪些具体问题，"
        "例如能力是否稳定、集成是否方便、成本是否可控、是否会改变团队协作方式，以及是否存在明显争议。"
        "这些信息能帮助读者区分短期噪声、真实采用阻力和后续值得追踪的产品信号。\n\n"
        "对中文用户来说，这类事件的价值在于把外网碎片信号转译成可判断的信息：它可能影响工具选型、学习重点、"
        "产品路线判断和后续观察优先级。即便暂时没有官方结论，热度本身也能反映 AI 圈的关注方向，"
        "尤其适合提醒用户哪些英文社区话题正在从小圈子扩散到更广泛的开发者视野。\n\n"
        "来源边界必须保留清楚：当前正文只能说明该主题正在被讨论，不能写成官方已经发布、能力已经验证或趋势已经定论。"
        "后续应继续观察官方说明、开发者实测、价格变化、API 能力和社区反馈。"
        f"{revision_note}"
    )


class OnDutyEditorAgentStub:
    """值班编辑确定性 stub。

    输入：标准化来源信号列表。
    输出：EventCandidateDraft，用于后续 EventService 创建候选事件。
    """

    name = "on_duty_editor_stub"
    role = "editor"

    def triage(self, signals: list[dict[str, Any]]) -> EventCandidateDraft:
        """生成候选事件草案。

        输入：至少一条来源信号，包含标题、来源 key 和热度指标。
        输出：包含候选事件 key、标题、分类、评分和排序理由的 EventCandidateDraft。
        """
        signal = _first_signal(signals)
        title = str(signal.get("original_title") or "Untitled AI signal")
        source_key = str(signal.get("source_key") or "source")
        metrics = signal.get("heat_metrics") or {}
        points = float(metrics.get("points") or 0)
        comments = float(metrics.get("comments") or 0)
        heat_score = _bounded_score(points * 0.45 + comments * 0.9)
        importance_score = _bounded_score(70 + min(points, 100) * 0.15)
        audience_value_score = _bounded_score(72 + min(comments, 80) * 0.2)
        ranking_score = _bounded_score(heat_score * 0.35 + importance_score * 0.35 + audience_value_score * 0.3)

        return EventCandidateDraft(
            candidate_key=f"{source_key}-{_slugify(title)}",
            title=f"{title} 引发 AI 圈关注",
            event_type="product_update",
            category="模型与产品",
            primary_subject="OpenAI",
            suggested_angle="从开发者工具链和中文用户使用成本角度解释这件事。",
            heat_score=heat_score,
            importance_score=importance_score,
            audience_value_score=audience_value_score,
            ranking_score=ranking_score,
            ranking_reason="来源信号同时具备讨论热度、产品相关性和中文用户理解价值。",
            merge_reason="P1-2 stub 暂按首条信号生成一个候选事件。",
        )


class ResearchWriterAgentStub:
    """研究写作确定性 stub。

    输入：候选事件草案、来源信号列表和可选修订说明。
    输出：EventDossierDraft，用于后续 EventService 保存事件档案。
    """

    name = "research_writer_stub"
    role = "writer"

    def draft(
        self,
        candidate: EventCandidateDraft,
        signals: list[dict[str, Any]],
        revision_instructions: str = "",
    ) -> EventDossierDraft:
        """生成事件档案草案。

        输入：EventCandidateDraft、来源信号列表和审稿修订意见。
        输出：首页卡片、详情正文、影响说明、跟进点和来源引用组成的 EventDossierDraft。
        """
        signal = _first_signal(signals)
        title = str(signal.get("original_title") or candidate.title)
        summary = str(signal.get("raw_summary") or signal.get("content_excerpt") or "来源信号显示该事件正在被开发者讨论。")
        revision_note = f"\n\n本版已按审稿意见修订：{revision_instructions}" if revision_instructions else ""
        source_refs = [
            {
                "signal_id": signal.get("id"),
                "title": title,
                "url": signal.get("original_url"),
                "source_key": signal.get("source_key"),
            }
        ]

        return EventDossierDraft(
            candidate_key=candidate.candidate_key,
            card_title=title,
            card_summary="开发者正在关注这项 AI 工具变化及其使用影响。",
            category=candidate.category,
            signal_label="高热讨论",
            detail_title=f"{title} 为什么值得关注",
            detail_summary=f"{summary} 这条事件档案会先解释变化本身，再说明它对中文用户的影响。",
            detail_body=_rich_stub_detail_body(summary, revision_note),
            why_it_matters="这件事可能影响中文用户理解 AI 工具链变化、评估使用成本和判断后续跟进价值。",
            follow_up_points=["观察官方文档是否更新", "观察开发者社区是否持续讨论", "观察价格和 API 能力是否明确"],
            source_refs=source_refs,
            status="draft",
        )


class ReviewPublisherAgentStub:
    """审稿发布确定性 stub。

    输入：事件档案草案和当前修订次数。
    输出：ReviewResultDraft，给出发布、修订或人工处理建议。
    """

    name = "review_publisher_stub"
    role = "reviewer"

    def review(self, dossier: EventDossierDraft, revision_count: int = 0) -> ReviewResultDraft:
        """审阅事件档案并给出发布建议。

        输入：EventDossierDraft 和 revision_count。
        输出：ReviewResultDraft；完整内容发布，不完整内容先修订，超过两次进入人工处理。
        """
        issues: list[str] = []
        if not dossier.detail_body.strip():
            issues.append("详情正文为空")
        if not dossier.source_refs:
            issues.append("缺少来源引用")
        if not dossier.why_it_matters.strip():
            issues.append("缺少影响说明")

        if not issues:
            return ReviewResultDraft(
                decision="publish",
                risk_level="low",
                issues=[],
                revision_instructions="",
                checked_items={"has_body": True, "has_sources": True, "has_impact": True},
            )

        if revision_count >= 2:
            return ReviewResultDraft(
                decision="manual_review",
                risk_level="medium",
                issues=issues,
                revision_instructions="已达到 P1 最大修订次数，请人工确认来源和正文。",
                checked_items={"has_body": not bool("详情正文为空" in issues), "has_sources": bool(dossier.source_refs)},
            )

        return ReviewResultDraft(
            decision="revise",
            risk_level="medium",
            issues=issues,
            revision_instructions="请补齐详情正文、来源引用和影响说明后再提交审稿。",
            checked_items={"has_body": not bool("详情正文为空" in issues), "has_sources": bool(dossier.source_refs)},
        )

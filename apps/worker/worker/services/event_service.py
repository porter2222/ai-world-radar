from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from worker.models import (
    EventCandidate,
    EventCandidateSignal,
    EventDossier,
    PublishedEvent,
    ReviewResult,
    SourceSignal,
)
from worker.schemas.event import EventCandidateDraft, EventDossierDraft, PublishEventCommand, ReviewResultDraft


class EventService:
    """事件档案生产与发布服务。

    输入：SQLAlchemy Session。
    输出：提供候选事件、事件档案、审稿结果和发布快照的受控写入能力。
    """

    def __init__(self, session: Session):
        """初始化服务。

        输入：外部传入且由调用方管理事务的 Session。
        输出：可复用的 EventService 实例。
        """
        self.session = session

    def create_candidate_with_signals(
        self,
        payload: EventCandidateDraft,
        signal_ids: list[str],
        merge_reason: str = "",
    ) -> EventCandidate:
        """按 candidate_key 幂等创建候选事件并关联信号。

        输入：EventCandidateDraft、SourceSignal ID 列表和合并原因。
        输出：已刷新并关联信号的 EventCandidate ORM 对象。
        """
        candidate = self.session.scalar(
            select(EventCandidate).where(EventCandidate.candidate_key == payload.candidate_key)
        )
        if candidate is None:
            candidate = EventCandidate(candidate_key=payload.candidate_key)
            self.session.add(candidate)

        candidate.title = payload.title
        candidate.event_type = payload.event_type
        candidate.category = payload.category
        candidate.primary_subject = payload.primary_subject
        candidate.suggested_angle = payload.suggested_angle
        candidate.heat_score = payload.heat_score
        candidate.importance_score = payload.importance_score
        candidate.audience_value_score = payload.audience_value_score
        candidate.ranking_score = payload.ranking_score
        candidate.ranking_reason = payload.ranking_reason
        candidate.merge_reason = payload.merge_reason or merge_reason
        candidate.status = "triaged"
        self.session.flush()

        for signal_id in signal_ids:
            if self.session.get(SourceSignal, signal_id) is None:
                raise ValueError(f"SourceSignal not found for id={signal_id}")
            association = self.session.scalar(
                select(EventCandidateSignal).where(
                    EventCandidateSignal.candidate_id == candidate.id,
                    EventCandidateSignal.signal_id == signal_id,
                )
            )
            if association is None:
                self.session.add(
                    EventCandidateSignal(
                        candidate_id=candidate.id,
                        signal_id=signal_id,
                        relation_type="primary",
                        merge_confidence=1.0,
                        merge_reason=merge_reason,
                    )
                )

        self.session.flush()
        return candidate

    def save_dossier(self, candidate_id: str, payload: EventDossierDraft) -> EventDossier:
        """保存候选事件的一版事件档案。

        输入：candidate_id 和 EventDossierDraft。
        输出：已刷新后的 EventDossier ORM 对象。
        """
        candidate = self.session.get(EventCandidate, candidate_id)
        if candidate is None:
            raise ValueError(f"EventCandidate not found for id={candidate_id}")

        version = self._next_dossier_version(candidate_id)
        dossier = EventDossier(
            candidate_id=candidate_id,
            version=version,
            status=payload.status,
            card_title=payload.card_title,
            card_summary=payload.card_summary,
            category=payload.category,
            signal_label=payload.signal_label,
            cover_image_url=payload.cover_image_url,
            detail_title=payload.detail_title,
            detail_summary=payload.detail_summary,
            detail_body=payload.detail_body,
            why_it_matters=payload.why_it_matters,
            follow_up_points=payload.follow_up_points,
            source_refs=payload.source_refs,
        )
        candidate.status = "reviewing"
        self.session.add(dossier)
        self.session.flush()
        return dossier

    def save_review_result(self, dossier_id: str, payload: ReviewResultDraft) -> ReviewResult:
        """保存审稿结果并更新 dossier 状态。

        输入：dossier_id 和 ReviewResultDraft。
        输出：已刷新后的 ReviewResult ORM 对象。
        """
        dossier = self.session.get(EventDossier, dossier_id)
        if dossier is None:
            raise ValueError(f"EventDossier not found for id={dossier_id}")

        review = ReviewResult(
            dossier_id=dossier.id,
            candidate_id=dossier.candidate_id,
            decision=payload.decision,
            risk_level=payload.risk_level,
            issues=payload.issues,
            revision_instructions=payload.revision_instructions,
            checked_items=payload.checked_items,
        )
        dossier.status = {
            "publish": "approved",
            "revise": "needs_revision",
            "manual_review": "manual_review",
            "reject": "rejected",
        }[payload.decision]
        self.session.add(review)
        self.session.flush()
        return review

    def publish_dossier(self, payload: PublishEventCommand) -> PublishedEvent:
        """发布已通过审稿的事件档案快照。

        输入：PublishEventCommand，包含 candidate_id、dossier_id 和发布模式。
        输出：幂等返回的 PublishedEvent ORM 对象。
        """
        existing = self.session.scalar(
            select(PublishedEvent).where(PublishedEvent.candidate_id == payload.candidate_id)
        )
        if existing is not None:
            return existing

        candidate = self.session.get(EventCandidate, payload.candidate_id)
        dossier = self.session.get(EventDossier, payload.dossier_id)
        if candidate is None:
            raise ValueError(f"EventCandidate not found for id={payload.candidate_id}")
        if dossier is None:
            raise ValueError(f"EventDossier not found for id={payload.dossier_id}")
        if dossier.candidate_id != candidate.id:
            raise ValueError("Dossier does not belong to candidate")

        approved_review = self.session.scalar(
            select(ReviewResult).where(
                ReviewResult.dossier_id == dossier.id,
                ReviewResult.decision == "publish",
            )
        )
        if approved_review is None:
            raise ValueError("Dossier has no publish review result")

        slug = self._unique_slug(candidate.candidate_key, candidate.id)
        published = PublishedEvent(
            candidate_id=candidate.id,
            dossier_id=dossier.id,
            slug=slug,
            published_title=dossier.detail_title,
            published_card_summary=dossier.card_summary,
            published_detail_summary=dossier.detail_summary,
            published_detail_body=dossier.detail_body,
            category=dossier.category,
            signal_label=dossier.signal_label,
            cover_image_url=dossier.cover_image_url,
            source_refs=dossier.source_refs,
            ranking_score=candidate.ranking_score,
            status="published",
            publish_mode=payload.publish_mode,
        )
        candidate.status = "published"
        dossier.status = "published_snapshot"
        self.session.add(published)
        self.session.flush()
        return published

    def _next_dossier_version(self, candidate_id: str) -> int:
        """计算候选事件的下一版 dossier version。

        输入：candidate_id。
        输出：该 candidate 当前最大 version + 1。
        """
        current = self.session.scalar(
            select(func.max(EventDossier.version)).where(EventDossier.candidate_id == candidate_id)
        )
        return (current or 0) + 1

    def _unique_slug(self, candidate_key: str, candidate_id: str) -> str:
        """生成发布事件 slug，避免不同 candidate 碰撞。

        输入：candidate_key 和 candidate_id。
        输出：可用于 PublishedEvent 的唯一 slug。
        """
        base_slug = re.sub(r"[^a-z0-9]+", "-", candidate_key.lower()).strip("-") or candidate_id.lower()
        existing = self.session.scalar(select(PublishedEvent).where(PublishedEvent.slug == base_slug))
        if existing is None or existing.candidate_id == candidate_id:
            return base_slug
        return f"{base_slug}-{candidate_id[-8:]}"

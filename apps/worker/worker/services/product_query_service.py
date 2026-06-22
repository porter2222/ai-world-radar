from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from worker.models import AgentRun, EventCandidate, EventDossier, PipelineRun, PublishedEvent, ReviewResult
from worker.schemas.product import (
    ManualReviewQueueItem,
    ProductAgentRunItem,
    ProductEventDetail,
    ProductEventListItem,
    ProductPipelineRunItem,
)


class ProductQueryService:
    """产品接口层只读查询服务。

    输入：SQLAlchemy Session。
    输出：供 FastAPI 或其他产品层复用的只读查询方法。
    """

    def __init__(self, session: Session):
        """初始化产品查询服务。

        输入：由调用方管理生命周期和事务的 SQLAlchemy Session。
        输出：可执行产品只读查询的服务实例。
        """
        self.session = session

    def list_published_events(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        category: str | None = None,
    ) -> list[ProductEventListItem]:
        """查询前台已发布事件列表。

        输入：分页参数和可选 category 过滤条件。
        输出：只包含 `published` 状态的事件卡片列表，不暴露内部排序分。
        """
        statement = select(PublishedEvent).where(PublishedEvent.status == "published")
        if category:
            statement = statement.where(PublishedEvent.category == category)
        statement = (
            statement.order_by(
                PublishedEvent.homepage_rank.is_(None),
                PublishedEvent.homepage_rank.asc(),
                PublishedEvent.ranking_score.desc(),
                PublishedEvent.published_at.desc(),
                PublishedEvent.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return [self._event_list_item(event) for event in self.session.scalars(statement).all()]

    def get_event_by_slug(self, slug: str) -> ProductEventDetail | None:
        """按 slug 查询前台事件详情。

        输入：PublishedEvent.slug。
        输出：事件详情响应；未找到 published 事件时返回 None。
        """
        row = self.session.execute(
            select(PublishedEvent, EventDossier)
            .join(EventDossier, EventDossier.id == PublishedEvent.dossier_id)
            .where(PublishedEvent.slug == slug, PublishedEvent.status == "published")
        ).one_or_none()
        if row is None:
            return None
        published, dossier = row
        return ProductEventDetail(
            id=published.id,
            slug=published.slug,
            title=published.published_title,
            detail_summary=published.published_detail_summary,
            detail_body=published.published_detail_body,
            why_it_matters=dossier.why_it_matters,
            follow_up_points=list(dossier.follow_up_points or []),
            source_refs=list(published.source_refs or []),
            category=published.category,
            signal_label=published.signal_label,
            cover_image_url=published.cover_image_url,
            published_at=published.published_at,
        )

    def list_pipeline_runs(self, *, limit: int = 20, offset: int = 0) -> list[ProductPipelineRunItem]:
        """查询后台 pipeline run 列表。

        输入：分页参数。
        输出：按启动时间倒序排列的 pipeline run 摘要列表。
        """
        statement = (
            select(PipelineRun)
            .order_by(PipelineRun.started_at.desc(), PipelineRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._pipeline_run_item(run) for run in self.session.scalars(statement).all()]

    def get_pipeline_run(self, run_id: str) -> ProductPipelineRunItem | None:
        """按 ID 查询单次 pipeline run。

        输入：pipeline run ID。
        输出：运行摘要；不存在时返回 None。
        """
        run = self.session.get(PipelineRun, run_id)
        if run is None:
            return None
        return self._pipeline_run_item(run)

    def list_agent_runs(self, run_id: str) -> list[ProductAgentRunItem]:
        """查询某次 pipeline run 下的 Agent 运行记录。

        输入：pipeline run ID。
        输出：Agent run 摘要列表，隐藏完整 trace_json 和 llm_raw_text。
        """
        statement = (
            select(AgentRun)
            .where(AgentRun.pipeline_run_id == run_id)
            .order_by(AgentRun.created_at.asc(), AgentRun.id.asc())
        )
        return [self._agent_run_item(agent_run) for agent_run in self.session.scalars(statement).all()]

    def list_manual_review_items(self, *, limit: int = 20, offset: int = 0) -> list[ManualReviewQueueItem]:
        """查询人工审核队列。

        输入：分页参数。
        输出：当前处于 manual_review 的 candidate 最新 dossier/review 列表。
        """
        candidates = self.session.scalars(
            select(EventCandidate)
            .where(EventCandidate.status == "manual_review")
            .order_by(EventCandidate.updated_at.desc(), EventCandidate.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        items: list[ManualReviewQueueItem] = []
        for candidate in candidates:
            dossier = self.session.scalar(
                select(EventDossier)
                .where(EventDossier.candidate_id == candidate.id, EventDossier.status == "manual_review")
                .order_by(EventDossier.version.desc())
            )
            if dossier is None:
                continue
            review = self.session.scalar(
                select(ReviewResult)
                .where(ReviewResult.dossier_id == dossier.id, ReviewResult.decision == "manual_review")
                .order_by(ReviewResult.created_at.desc(), ReviewResult.id.desc())
            )
            if review is None:
                continue
            items.append(
                ManualReviewQueueItem(
                    candidate_id=candidate.id,
                    dossier_id=dossier.id,
                    review_id=review.id,
                    title=dossier.detail_title,
                    category=dossier.category,
                    dossier_version=dossier.version,
                    risk_level=review.risk_level,
                    issues=list(review.issues or []),
                    revision_instructions=review.revision_instructions,
                    updated_at=dossier.updated_at,
                )
            )
        return items

    def _event_list_item(self, event: PublishedEvent) -> ProductEventListItem:
        """把 PublishedEvent 转成前台列表响应。

        输入：PublishedEvent ORM 对象。
        输出：ProductEventListItem。
        """
        return ProductEventListItem(
            id=event.id,
            slug=event.slug,
            title=event.published_title,
            card_summary=event.published_card_summary,
            detail_summary=event.published_detail_summary,
            category=event.category,
            signal_label=event.signal_label,
            cover_image_url=event.cover_image_url,
            homepage_rank=event.homepage_rank,
            published_at=event.published_at,
        )

    def _pipeline_run_item(self, run: PipelineRun) -> ProductPipelineRunItem:
        """把 PipelineRun 转成后台运行摘要响应。

        输入：PipelineRun ORM 对象。
        输出：ProductPipelineRunItem。
        """
        return ProductPipelineRunItem(
            id=run.id,
            run_key=run.run_key,
            trigger_type=run.trigger_type,
            source_scope=dict(run.source_scope or {}),
            status=run.status,
            started_at=run.started_at,
            ended_at=run.ended_at,
            signals_count=run.signals_count,
            candidates_count=run.candidates_count,
            dossiers_count=run.dossiers_count,
            published_count=run.published_count,
            failed_count=run.failed_count,
            summary=run.summary,
            error_message=run.error_message,
        )

    def _agent_run_item(self, agent_run: AgentRun) -> ProductAgentRunItem:
        """把 AgentRun 转成后台审计响应。

        输入：AgentRun ORM 对象。
        输出：不包含完整 trace_json 和 llm_raw_text 的 ProductAgentRunItem。
        """
        trace_json = agent_run.trace_json or {}
        token_usage = trace_json.get("token_usage") if isinstance(trace_json, dict) else None
        return ProductAgentRunItem(
            id=agent_run.id,
            pipeline_run_id=agent_run.pipeline_run_id,
            candidate_id=agent_run.candidate_id,
            dossier_id=agent_run.dossier_id,
            agent_name=agent_run.agent_name,
            agent_role=agent_run.agent_role,
            model_provider=agent_run.model_provider,
            model_name=agent_run.model_name,
            prompt_version=agent_run.prompt_version,
            status=agent_run.status,
            duration_ms=agent_run.duration_ms,
            retry_count=agent_run.retry_count,
            token_usage=token_usage,
            error_message=agent_run.error_message,
            created_at=agent_run.created_at,
        )

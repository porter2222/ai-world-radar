from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from worker.models import AgentRun, EventCandidate, EventDossier, PipelineRun, PublishedEvent, ReviewResult
from worker.schemas.product import (
    ManualReviewQueueItem,
    ProductAgentRunItem,
    ProductEventDetail,
    ProductEventListItem,
    ProductPipelineRunItem,
)


SOURCE_KEY_DISPLAY_NAMES = {
    "hn_algolia": "Hacker News",
    "github_releases": "GitHub Release",
    "github_repo_trends": "GitHub",
    "github_changelog": "GitHub",
    "openai_news": "OpenAI",
    "anthropic_news": "Anthropic",
    "nvidia_news": "NVIDIA",
    "deepmind_blog": "Google DeepMind",
    "google_ai_blog": "Google AI",
    "huggingface_blog": "Hugging Face",
    "pytorch_blog": "PyTorch",
    "ollama_blog": "Ollama",
    "aws_machine_learning_blog": "AWS ML Blog",
}

SOURCE_KEY_PLATFORM_KEYS = {
    "hn_algolia": "hacker_news",
    "github_releases": "github",
    "github_repo_trends": "github",
    "github_changelog": "github",
    "openai_news": "openai",
    "anthropic_news": "anthropic",
    "nvidia_news": "nvidia",
    "deepmind_blog": "google",
    "google_ai_blog": "google",
    "huggingface_blog": "hugging_face",
    "pytorch_blog": "pytorch",
    "ollama_blog": "ollama",
    "aws_machine_learning_blog": "aws",
}

DOMAIN_DISPLAY_NAMES = {
    "news.ycombinator.com": "Hacker News",
    "github.com": "GitHub",
    "openai.com": "OpenAI",
    "anthropic.com": "Anthropic",
    "nvidia.com": "NVIDIA",
    "deepmind.google": "Google DeepMind",
    "blog.google": "Google AI",
    "huggingface.co": "Hugging Face",
    "pytorch.org": "PyTorch",
    "ollama.com": "Ollama",
    "aws.amazon.com": "AWS ML Blog",
}


def _source_hint_and_count(source_refs: list[dict[str, Any]]) -> tuple[str | None, int]:
    """生成首页事件卡的单行来源提示。

    输入：PublishedEvent.source_refs 中的来源引用列表。
    输出：短来源提示和按平台去重后的来源数量；不返回完整来源明细。
    """
    refs = [ref for ref in source_refs if isinstance(ref, dict)]
    if not refs:
        return None, 0

    platform_keys = {_source_platform_key(ref) for ref in refs}
    source_count = len({key for key in platform_keys if key})
    if source_count == 0:
        return None, 0

    first_source_name = _source_display_name(refs[0])
    if source_count == 1:
        return first_source_name, 1
    return f"{first_source_name} 等 {source_count} 源", source_count


def _source_display_name(ref: dict[str, Any]) -> str:
    """读取单条来源在首页卡片上的短展示名。

    输入：一条 source ref，可能包含 source_key、url、title。
    输出：适合单行展示的平台名；优先使用平台映射，最后才用标题兜底。
    """
    source_key = _clean_text(ref.get("source_key"))
    if source_key and source_key in SOURCE_KEY_DISPLAY_NAMES:
        return SOURCE_KEY_DISPLAY_NAMES[source_key]

    domain = _source_domain(ref)
    if domain:
        if domain in DOMAIN_DISPLAY_NAMES:
            return DOMAIN_DISPLAY_NAMES[domain]
        return domain.removeprefix("www.")

    return _clean_text(ref.get("title")) or "未知来源"


def _source_platform_key(ref: dict[str, Any]) -> str:
    """生成来源平台去重 key。

    输入：一条 source ref，可能包含 source_key、url、title。
    输出：用于 source_count 去重的稳定平台 key。
    """
    source_key = _clean_text(ref.get("source_key"))
    if source_key:
        return SOURCE_KEY_PLATFORM_KEYS.get(source_key, source_key)

    domain = _source_domain(ref)
    if domain:
        return _platform_key_from_domain(domain)

    return (_clean_text(ref.get("title")) or "unknown").lower()


def _source_domain(ref: dict[str, Any]) -> str:
    """从来源 URL 中提取域名。

    输入：一条 source ref。
    输出：小写域名；没有合法 URL 时返回空字符串。
    """
    url = _clean_text(ref.get("url"))
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return (parsed.hostname or "").lower()


def _platform_key_from_domain(domain: str) -> str:
    """把域名归一化成平台去重 key。

    输入：来源 URL 域名。
    输出：平台级 key，常见子域会归并到同一个平台。
    """
    normalized = domain.removeprefix("www.")
    if normalized.endswith("github.com"):
        return "github"
    if normalized.endswith("ycombinator.com"):
        return "hacker_news"
    if normalized.endswith("openai.com"):
        return "openai"
    if normalized.endswith("anthropic.com"):
        return "anthropic"
    if normalized.endswith("nvidia.com"):
        return "nvidia"
    if normalized.endswith("google") or normalized.endswith("google.com"):
        return "google"
    if normalized.endswith("huggingface.co"):
        return "hugging_face"
    if normalized.endswith("pytorch.org"):
        return "pytorch"
    if normalized.endswith("ollama.com"):
        return "ollama"
    if normalized.endswith("amazon.com"):
        return "aws"
    return normalized


def _clean_text(value: Any) -> str:
    """清洗来源字段中的短文本。

    输入：任意来源字段值。
    输出：去除首尾空白后的字符串；空值返回空字符串。
    """
    return str(value or "").strip()


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
        recent_hours: int = 48,
        min_recent_items: int = 8,
        backfill_days: int = 7,
        now: datetime | None = None,
    ) -> list[ProductEventListItem]:
        """查询前台已发布事件列表。

        输入：分页参数、可选 category 和首页时效窗口内部参数。
        输出：近期首页事件卡片列表；低量时向 7 天兜底，不暴露内部排序分。
        """
        current_time = self._current_time(now)
        recent_cutoff = current_time - timedelta(hours=recent_hours)
        backfill_cutoff = current_time - timedelta(days=backfill_days)
        base_filters = self._published_base_filters(category)
        recent_count = self.session.scalar(
            select(func.count())
            .select_from(PublishedEvent)
            .where(*base_filters, PublishedEvent.published_at >= recent_cutoff)
        ) or 0
        cutoff = backfill_cutoff if recent_count < min_recent_items else recent_cutoff
        statement = (
            select(PublishedEvent)
            .where(*base_filters, PublishedEvent.published_at >= cutoff)
            .order_by(
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

    def _current_time(self, now: datetime | None) -> datetime:
        """返回首页窗口计算使用的当前时间。

        输入：测试可注入的 now；生产调用传 None。
        输出：带 UTC 时区的 datetime，用于计算 recent/backfill cutoff。
        """
        if now is not None:
            return now if now.tzinfo else now.replace(tzinfo=UTC)
        return datetime.now(UTC)

    def _published_base_filters(self, category: str | None) -> list[Any]:
        """生成已发布事件列表的基础过滤条件。

        输入：可选 category。
        输出：SQLAlchemy where 条件列表，供近期窗口和兜底窗口复用。
        """
        filters: list[Any] = [PublishedEvent.status == "published"]
        if category:
            filters.append(PublishedEvent.category == category)
        return filters

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
        source_hint, source_count = _source_hint_and_count(list(event.source_refs or []))
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
            source_hint=source_hint,
            source_count=source_count,
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

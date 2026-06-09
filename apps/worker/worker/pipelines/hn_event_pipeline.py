from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from worker.agents.brief_writer_agent import BriefWriterAgentStub
from worker.agents.detail_writer_agent import DetailWriterAgentStub
from worker.agents.evidence_agent import EvidenceAgentStub
from worker.agents.event_cluster_agent import EventClusterAgentStub
from worker.agents.quality_gate_agent import QualityGateAgentStub
from worker.agents.ranking_agent import RankingAgentStub
from worker.collectors.hn_algolia import HNStory, fetch_hn_stories
from worker.collectors.page_cache import PageFetchResult, fetch_and_cache_url
from worker.db.models import (
    Brief,
    BriefItem,
    ContentArtifact,
    EventCluster,
    EventClusterCard,
    EvidenceCard,
    PipelineRun,
    PublishedEvent,
    QualityGateResult,
    Source,
    new_id,
)
from worker.reports.pipeline_report_writer import PipelineReport, PipelineReportWriter

PageFetcher = Callable[[str | None, str, Path], PageFetchResult]


@dataclass(frozen=True)
class PipelineResult:
    pipeline_run_id: str
    status: str
    fetched_count: int
    evidence_card_count: int
    event_cluster_count: int
    published_event_count: int
    brief_item_count: int
    report_path: Path | None
    errors: list[str]


class HNEventPipeline:
    def __init__(
        self,
        session: Session,
        runtime_dir: Path,
        page_fetcher: PageFetcher = fetch_and_cache_url,
    ) -> None:
        self.session = session
        self.runtime_dir = runtime_dir
        self.page_fetcher = page_fetcher
        self.evidence_agent = EvidenceAgentStub()
        self.cluster_agent = EventClusterAgentStub()
        self.ranking_agent = RankingAgentStub()
        self.detail_writer = DetailWriterAgentStub()
        self.brief_writer = BriefWriterAgentStub()
        self.quality_gate = QualityGateAgentStub()

    def run(
        self,
        days: int,
        limit: int,
        force: bool = False,
        stories: list[HNStory] | None = None,
    ) -> PipelineResult:
        pipeline_run = PipelineRun(
            pipeline_run_id=new_id("run"),
            run_type="manual",
            triggered_by="system",
            status="running",
            config_version="p1-hn-stub-v1",
        )
        self.session.add(pipeline_run)
        self._ensure_hn_source()
        self.session.flush()

        errors: list[str] = []
        quality_gate_failures: list[str] = []
        fetched_stories = stories if stories is not None else fetch_hn_stories(days=days, limit=limit)
        published_this_run = 0

        try:
            for story in fetched_stories[:limit]:
                evidence_model, evidence_payload = self._get_or_create_evidence_card(story, pipeline_run.pipeline_run_id, force)
                ranked_cluster = self._get_or_create_cluster(evidence_model, evidence_payload, pipeline_run.pipeline_run_id)
                if published_this_run >= 10:
                    continue
                if ranked_cluster["publish_decision"] != "publish":
                    continue
                created = self._publish_if_needed(ranked_cluster, evidence_payload, pipeline_run.pipeline_run_id, quality_gate_failures)
                if created:
                    published_this_run += 1

            brief_item_count = self._create_brief(pipeline_run.pipeline_run_id)
            pipeline_run.status = "success"
            pipeline_run.finished_at = datetime.now(UTC)
            pipeline_run.source_count = 1
            pipeline_run.evidence_card_count = self._count(EvidenceCard)
            pipeline_run.event_cluster_count = self._count(EventCluster)
            pipeline_run.content_artifact_count = self._count(ContentArtifact)
            pipeline_run.published_event_count = self._count(PublishedEvent)
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            errors.append(str(exc))
            pipeline_run.status = "failed"
            pipeline_run.error_summary = str(exc)
            pipeline_run.finished_at = datetime.now(UTC)
            self.session.add(pipeline_run)
            self.session.commit()
            brief_item_count = 0

        result = PipelineResult(
            pipeline_run_id=pipeline_run.pipeline_run_id,
            status=pipeline_run.status,
            fetched_count=len(fetched_stories),
            evidence_card_count=self._count(EvidenceCard),
            event_cluster_count=self._count(EventCluster),
            published_event_count=self._count(PublishedEvent),
            brief_item_count=brief_item_count,
            report_path=None,
            errors=errors,
        )
        report_path = self._write_report(result, days, limit, quality_gate_failures)
        return PipelineResult(**{**result.__dict__, "report_path": report_path})

    def _ensure_hn_source(self) -> Source:
        source = self.session.scalar(select(Source).where(Source.source_id == "hacker_news"))
        if source:
            return source

        source = Source(
            source_id="hacker_news",
            name="Hacker News",
            source_type="community",
            fetch_method="hn_api",
            url="https://hn.algolia.com/api",
            enabled=True,
            discovery_weight=1.0,
            heat_signal_weight=1.0,
            impact_signal_weight=0.5,
            language="en",
            category_hint="developer_tools",
            last_status="success",
        )
        self.session.add(source)
        return source

    def _get_or_create_evidence_card(
        self,
        story: HNStory,
        pipeline_run_id: str,
        force: bool,
    ) -> tuple[EvidenceCard, dict]:
        existing = self.session.scalar(
            select(EvidenceCard).where(
                EvidenceCard.source_id == "hacker_news",
                EvidenceCard.source_item_id == story.hn_id,
                EvidenceCard.prompt_version == EvidenceAgentStub.prompt_version,
            )
        )
        if existing and not force:
            return existing, evidence_model_to_payload(existing)

        page = self.page_fetcher(story.original_url, story.hn_id, self.runtime_dir)
        payload = self.evidence_agent.build(story, page)

        if existing:
            self._apply_evidence_payload(existing, payload, pipeline_run_id)
            self.session.flush()
            return existing, payload

        evidence = EvidenceCard(evidence_card_id=new_id("ev"), pipeline_run_id=pipeline_run_id)
        self._apply_evidence_payload(evidence, payload, pipeline_run_id)
        self.session.add(evidence)
        self.session.flush()
        return evidence, payload

    def _apply_evidence_payload(self, evidence: EvidenceCard, payload: dict, pipeline_run_id: str) -> None:
        evidence.pipeline_run_id = pipeline_run_id
        evidence.source_id = payload["source_id"]
        evidence.source_item_id = payload["source_item_id"]
        evidence.original_title = payload["original_title"]
        evidence.original_url = payload["original_url"]
        evidence.author = payload["author"]
        evidence.raw_summary = payload["story_text"]
        evidence.raw_excerpt = payload["page_excerpt"]
        evidence.raw_heat_metrics = payload["raw_heat_metrics"]
        evidence.raw_metadata = {"matched_source": "hacker_news"}
        evidence.page_title = payload["page_title"]
        evidence.page_excerpt = payload["page_excerpt"]
        evidence.page_text_hash = payload["page_text_hash"]
        evidence.page_cache_path = payload["page_cache_path"]
        evidence.page_fetch_status = payload["fetch_status"]
        evidence.claim_summary = payload["claim_summary"]
        evidence.normalized_title = payload["normalized_title"]
        evidence.subjects = payload["subjects"]
        evidence.event_trigger = payload["event_trigger"]
        evidence.event_type = payload["event_type"]
        evidence.category = payload["category"]
        evidence.heat_clues = payload["heat_clues"]
        evidence.impact_clues = payload["impact_clues"]
        evidence.audience_value_reason = payload["audience_value_reason"]
        evidence.suggested_route = payload["suggested_route"]
        evidence.candidate_score = payload["candidate_score"]
        evidence.candidate_reason = payload["candidate_reason"]
        evidence.merge_key_hint = payload["merge_key_hint"]
        evidence.dedupe_key = payload["dedupe_key"]
        evidence.model_name = payload["model_name"]
        evidence.prompt_version = payload["prompt_version"]
        evidence.processing_status = payload["processing_status"]

    def _get_or_create_cluster(self, evidence_model: EvidenceCard, evidence_payload: dict, pipeline_run_id: str) -> dict:
        cluster_payload = self.cluster_agent.cluster(evidence_payload)
        ranked = self.ranking_agent.rank(cluster_payload)
        cluster = self.session.scalar(select(EventCluster).where(EventCluster.event_key == ranked["event_key"]))

        if cluster is None:
            cluster = EventCluster(
                event_cluster_id=new_id("cluster"),
                event_key=ranked["event_key"],
                created_pipeline_run_id=pipeline_run_id,
                title_hint=ranked["title_hint"],
            )
            self.session.add(cluster)

        cluster.last_seen_pipeline_run_id = pipeline_run_id
        cluster.title_hint = ranked["title_hint"]
        cluster.summary_hint = ranked["summary_hint"]
        cluster.primary_subject = ranked["primary_subject"]
        cluster.subjects = ranked["subjects"]
        cluster.event_trigger = ranked["event_trigger"]
        cluster.event_type = ranked["event_type"]
        cluster.category = ranked["category"]
        cluster.merge_key = ranked["merge_key"]
        cluster.heat_score = ranked["heat_score"]
        cluster.impact_score = ranked["impact_score"]
        cluster.audience_value_score = ranked["audience_value_score"]
        cluster.ranking_score = ranked["ranking_score"]
        cluster.ranking_reason = ranked["ranking_reason"]
        cluster.evidence_card_count = ranked["evidence_card_count"]
        cluster.source_count = ranked["source_count"]
        cluster.cluster_status = ranked["cluster_status"]
        cluster.publish_decision = ranked["publish_decision"]
        cluster.brief_candidate = ranked["brief_candidate"]
        cluster.planning_reason = ranked["ranking_reason"]
        self.session.flush()

        association = self.session.scalar(
            select(EventClusterCard).where(
                EventClusterCard.event_cluster_id == cluster.event_cluster_id,
                EventClusterCard.evidence_card_id == evidence_model.evidence_card_id,
            )
        )
        if association is None:
            self.session.add(
                EventClusterCard(
                    event_cluster_card_id=new_id("ecc"),
                    event_cluster_id=cluster.event_cluster_id,
                    evidence_card_id=evidence_model.evidence_card_id,
                    signal_role="primary_signal",
                    merge_reason="Deterministic stub: one HN story maps to one event cluster.",
                )
            )

        ranked["event_cluster_id"] = cluster.event_cluster_id
        return ranked

    def _publish_if_needed(
        self,
        ranked_cluster: dict,
        evidence_payload: dict,
        pipeline_run_id: str,
        quality_gate_failures: list[str],
    ) -> bool:
        existing = self.session.scalar(
            select(PublishedEvent).where(PublishedEvent.event_cluster_id == ranked_cluster["event_cluster_id"])
        )
        if existing:
            return False

        detail = self.detail_writer.write(ranked_cluster, evidence_payload)
        gate = self.quality_gate.check(detail)

        card_artifact = ContentArtifact(
            content_artifact_id=new_id("artifact"),
            event_cluster_id=ranked_cluster["event_cluster_id"],
            pipeline_run_id=pipeline_run_id,
            artifact_type="event_card",
            content_version=1,
            status="qc_passed" if gate["recommended_action"] == "publish" else "qc_failed",
            title=detail["title"],
            summary=detail["summary"],
            body=detail["summary"],
            body_format="markdown",
            evidence_card_ids=[evidence_payload["source_item_id"]],
            source_refs=detail["source_refs"],
            generation_reason="deterministic stub",
            model_name="deterministic-stub",
            prompt_version="stub-v1",
        )
        detail_artifact = ContentArtifact(
            content_artifact_id=new_id("artifact"),
            event_cluster_id=ranked_cluster["event_cluster_id"],
            pipeline_run_id=pipeline_run_id,
            artifact_type="event_detail",
            content_version=1,
            status="qc_passed" if gate["recommended_action"] == "publish" else "qc_failed",
            title=detail["title"],
            summary=detail["summary"],
            body=detail["body"],
            body_format="markdown",
            evidence_card_ids=[evidence_payload["source_item_id"]],
            source_refs=detail["source_refs"],
            generation_reason="deterministic stub",
            model_name="deterministic-stub",
            prompt_version="stub-v1",
        )
        self.session.add_all([card_artifact, detail_artifact])
        self.session.flush()

        self.session.add(
            QualityGateResult(
                quality_gate_result_id=new_id("qg"),
                content_artifact_id=detail_artifact.content_artifact_id,
                event_cluster_id=ranked_cluster["event_cluster_id"],
                pipeline_run_id=pipeline_run_id,
                gate_version=gate["gate_version"],
                status=gate["status"],
                check_results=gate["check_results"],
                fail_reasons=gate["fail_reasons"],
                recommended_action=gate["recommended_action"],
                checked_by=gate["checked_by"],
            )
        )

        if gate["recommended_action"] != "publish":
            quality_gate_failures.append(f"{ranked_cluster['event_key']}: {gate['fail_reasons']}")
            return False

        self.session.add(
            PublishedEvent(
                published_event_id=detail["published_event_id"],
                event_cluster_id=ranked_cluster["event_cluster_id"],
                card_artifact_id=card_artifact.content_artifact_id,
                detail_artifact_id=detail_artifact.content_artifact_id,
                slug=ranked_cluster["event_key"],
                display_title=detail["title"],
                display_summary=detail["summary"],
                category=detail["category"],
                publish_status="published",
                visibility="public",
                published_by="system",
                ranking_score=detail["ranking_score"],
            )
        )
        return True

    def _create_brief(self, pipeline_run_id: str) -> int:
        events = list(
            self.session.scalars(
                select(PublishedEvent)
                .where(PublishedEvent.publish_status == "published")
                .order_by(PublishedEvent.ranking_score.desc())
                .limit(5)
            )
        )
        if not events:
            return 0

        brief_payload = self.brief_writer.write(
            [
                {
                    "published_event_id": event.published_event_id,
                    "title": event.display_title,
                    "summary": event.display_summary or "",
                }
                for event in events
            ]
        )
        version = self._next_brief_version()
        brief = Brief(
            brief_id=new_id("brief"),
            brief_date=datetime.now(UTC),
            title=brief_payload["title"],
            overview=brief_payload["overview"],
            status="published",
            item_count=len(brief_payload["items"]),
            pipeline_run_id=pipeline_run_id,
            version=version,
            published_at=datetime.now(UTC),
        )
        self.session.add(brief)
        self.session.flush()

        for item in brief_payload["items"]:
            event = next(event for event in events if event.published_event_id == item["published_event_id"])
            artifact = ContentArtifact(
                content_artifact_id=new_id("artifact"),
                event_cluster_id=event.event_cluster_id,
                pipeline_run_id=pipeline_run_id,
                artifact_type="brief_item",
                content_version=1,
                status="qc_passed",
                title=item["item_title"],
                summary=item["item_summary"],
                body=item["item_summary"],
                body_format="markdown",
                source_refs=[],
                generation_reason=item["item_reason"],
                model_name="deterministic-stub",
                prompt_version="stub-v1",
            )
            self.session.add(artifact)
            self.session.flush()
            self.session.add(
                BriefItem(
                    brief_item_id=new_id("brief_item"),
                    brief_id=brief.brief_id,
                    published_event_id=item["published_event_id"],
                    brief_artifact_id=artifact.content_artifact_id,
                    sort_order=item["sort_order"],
                    section="top",
                    highlight_reason=item["item_reason"],
                )
            )

        return len(brief_payload["items"])

    def _next_brief_version(self) -> int:
        existing_versions = self.session.scalars(select(Brief.version)).all()
        return (max(existing_versions) if existing_versions else 0) + 1

    def _write_report(
        self,
        result: PipelineResult,
        days: int,
        limit: int,
        quality_gate_failures: list[str],
    ) -> Path:
        report = PipelineReport(
            pipeline_run_id=result.pipeline_run_id,
            status=result.status,
            days=days,
            limit=limit,
            fetched_count=result.fetched_count,
            evidence_card_count=result.evidence_card_count,
            event_cluster_count=result.event_cluster_count,
            published_event_count=result.published_event_count,
            brief_item_count=result.brief_item_count,
            quality_gate_failures=quality_gate_failures,
            errors=result.errors,
        )
        return PipelineReportWriter(self.runtime_dir / "pipeline-reports").write(report)

    def _count(self, model: type) -> int:
        return len(list(self.session.scalars(select(model))))


def evidence_model_to_payload(evidence: EvidenceCard) -> dict:
    return {
        "source_id": evidence.source_id,
        "source_item_id": evidence.source_item_id,
        "original_title": evidence.original_title,
        "original_url": evidence.original_url,
        "author": evidence.author,
        "published_at": evidence.published_at.isoformat() if evidence.published_at else None,
        "points": (evidence.raw_heat_metrics or {}).get("points", 0),
        "num_comments": (evidence.raw_heat_metrics or {}).get("num_comments", 0),
        "story_text": evidence.raw_summary,
        "page_title": evidence.page_title,
        "page_excerpt": evidence.page_excerpt,
        "page_text_hash": evidence.page_text_hash,
        "page_cache_path": evidence.page_cache_path,
        "fetch_status": evidence.page_fetch_status,
        "claim_summary": evidence.claim_summary,
        "normalized_title": evidence.normalized_title,
        "subjects": evidence.subjects or ["AI"],
        "event_trigger": evidence.event_trigger,
        "event_type": evidence.event_type,
        "category": evidence.category,
        "heat_clues": evidence.heat_clues or [],
        "impact_clues": evidence.impact_clues or [],
        "audience_value_reason": evidence.audience_value_reason,
        "suggested_route": evidence.suggested_route,
        "candidate_score": evidence.candidate_score,
        "candidate_reason": evidence.candidate_reason,
        "merge_key_hint": evidence.merge_key_hint,
        "dedupe_key": evidence.dedupe_key,
        "raw_heat_metrics": evidence.raw_heat_metrics or {},
        "processing_status": evidence.processing_status,
        "model_name": evidence.model_name,
        "prompt_version": evidence.prompt_version,
    }

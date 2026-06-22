from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from worker.agents.event_pipeline_agents import (
    OnDutyEditorAgentStub,
    ResearchWriterAgentStub,
    ReviewPublisherAgentStub,
)
from worker.agents.factory import EventAgentSet
from worker.models import EventCandidate, EventDossier, PipelineRun, PublishedEvent, SourceSignal
from worker.schemas.event import EventCandidateDraft, EventDossierDraft, PublishEventCommand
from worker.schemas.run import AgentRunRecord, PipelineRunCreate
from worker.services.event_service import EventService
from worker.services.run_log_service import RunLogService


class EventPipelineTools:
    """事件工作流工程工具集合。

    输入：SQLAlchemy Session 和可选三 Agent 或 Agent 集合。
    输出：供 LangGraph 节点调用的受控数据库写入能力。
    """

    def __init__(
        self,
        session: Session,
        editor: Any | None = None,
        writer: Any | None = None,
        reviewer: Any | None = None,
        agents: EventAgentSet | None = None,
    ):
        """初始化 tool 适配层。

        输入：调用方管理事务的 Session，以及可替换的 Agent 实例或 Agent 集合。
        输出：绑定服务层和三类 Agent 的 EventPipelineTools 实例。
        """
        self.session = session
        self.event_service = EventService(session)
        self.run_log_service = RunLogService(session)
        selected_agents = agents or EventAgentSet(
            editor=OnDutyEditorAgentStub(),
            writer=ResearchWriterAgentStub(),
            reviewer=ReviewPublisherAgentStub(),
        )
        self.editor = editor or selected_agents.editor
        self.writer = writer or selected_agents.writer
        self.reviewer = reviewer or selected_agents.reviewer
        self.current_run_id: str | None = None

    def start_run(self, run_key: str, source_scope: dict[str, Any]) -> PipelineRun:
        """创建本轮 pipeline run。

        输入：run_key 和来源范围快照。
        输出：已 flush 的 PipelineRun，并把 run_id 保存为后续 tool 默认上下文。
        """
        run = self.run_log_service.start_pipeline_run(
            PipelineRunCreate(
                run_key=run_key,
                trigger_type="manual",
                source_scope=source_scope,
                status="running",
                config_snapshot={"pipeline": "p1-2-event-pipeline"},
            )
        )
        self.current_run_id = run.id
        return run

    def load_signals(self, signal_ids: list[str]) -> list[dict[str, Any]]:
        """读取并标准化来源信号。

        输入：SourceSignal ID 列表。
        输出：供 Agent stub 使用的信号 dict 列表；任一 ID 不存在时抛出 ValueError。
        """
        signals: list[dict[str, Any]] = []
        for signal_id in signal_ids:
            signal = self.session.get(SourceSignal, signal_id)
            if signal is None:
                raise ValueError(f"SourceSignal not found for id={signal_id}")
            if self.current_run_id is not None:
                signal.pipeline_run_id = self.current_run_id
            signals.append(self._signal_to_dict(signal))
        self.session.flush()
        return signals

    def create_candidate(self, signals: list[dict[str, Any]]) -> EventCandidate:
        """通过值班编辑 Agent 和 EventService 创建候选事件。

        输入：已标准化的来源信号 dict 列表。
        输出：已写入数据库并关联来源信号的 EventCandidate。
        """
        draft = self.editor.triage(signals)
        candidate = self.event_service.create_candidate_with_signals(
            draft,
            signal_ids=[str(signal["id"]) for signal in signals],
            merge_reason=draft.merge_reason or "",
        )
        if self.current_run_id is not None:
            candidate.created_by_run_id = self.current_run_id
            self.session.flush()
        return candidate

    def create_dossier(
        self,
        candidate: EventCandidate,
        signals: list[dict[str, Any]],
        revision_instructions: str = "",
    ) -> EventDossier:
        """通过研究写作 Agent 和 EventService 创建事件档案。

        输入：候选事件 ORM、来源信号 dict 列表和可选修订说明。
        输出：已写入数据库的 EventDossier。
        """
        draft = self.writer.draft(self._candidate_to_draft(candidate), signals, revision_instructions)
        dossier = self.event_service.save_dossier(candidate.id, draft)
        if self.current_run_id is not None:
            dossier.generated_by_run_id = self.current_run_id
            self.session.flush()
        return dossier

    def review_dossier(self, dossier: EventDossier, revision_count: int = 0):
        """通过审稿发布 Agent 和 EventService 保存审稿结果。

        输入：事件档案 ORM 和当前修订次数。
        输出：已写入数据库的 ReviewResult。
        """
        draft = self.reviewer.review(self._dossier_to_draft(dossier), revision_count=revision_count)
        review = self.event_service.save_review_result(dossier.id, draft)
        if self.current_run_id is not None:
            review.pipeline_run_id = self.current_run_id
            self.session.flush()
        return review

    def publish_if_approved(
        self,
        candidate_id: str,
        dossier_id: str,
        decision: str,
    ) -> PublishedEvent | None:
        """按审稿决策发布事件。

        输入：candidate_id、dossier_id 和审稿 decision。
        输出：当 decision 为 publish 时返回 PublishedEvent，否则返回 None。
        """
        if decision != "publish":
            return None
        return self.event_service.publish_dossier(
            PublishEventCommand(candidate_id=candidate_id, dossier_id=dossier_id, publish_mode="auto")
        )

    def record_agent_result(
        self,
        run_id: str,
        agent_name: str,
        agent_role: Literal["editor", "writer", "reviewer", "skill"],
        input_summary: str,
        output_json: dict[str, Any],
        candidate_id: str | None = None,
        dossier_id: str | None = None,
        retry_count: int = 0,
        agent: Any | None = None,
    ):
        """记录一次 Agent 输出。

        输入：run_id、Agent 名称/角色、输入摘要、输出 JSON、可选业务对象 ID 和 Agent 实例。
        输出：已写入数据库的 AgentRun。
        """
        metadata = self._successful_agent_metadata(agent)
        trace_json = {"pipeline": "p1-2-event-pipeline", "token_usage": metadata["token_usage"]}
        if metadata["raw_text"] is not None:
            trace_json.update(
                {
                    "llm_raw_text": metadata["raw_text"],
                    "llm_prompt_version": metadata["prompt_version"],
                    "llm_retry_count": metadata["retry_count"],
                }
            )
        return self.run_log_service.record_agent_run(
            AgentRunRecord(
                pipeline_run_id=run_id,
                candidate_id=candidate_id,
                dossier_id=dossier_id,
                agent_name=agent_name,
                agent_role=agent_role,
                model_provider=metadata["model_provider"],
                model_name=metadata["model_name"],
                prompt_version=metadata["prompt_version"],
                input_summary=input_summary,
                output_json=output_json,
                trace_json=trace_json,
                status="succeeded",
                duration_ms=metadata["duration_ms"],
                retry_count=metadata["retry_count"] if metadata["retry_count"] is not None else retry_count,
            )
        )

    def record_agent_failure(
        self,
        run_id: str,
        agent: Any,
        agent_role: Literal["editor", "writer", "reviewer", "skill"],
        input_summary: str,
        error_message: str,
        candidate_id: str | None = None,
        dossier_id: str | None = None,
    ):
        """记录一次失败的 Agent 输出。

        输入：run_id、Agent 实例、角色、输入摘要、错误信息和可选业务对象 ID。
        输出：status=failed 的 AgentRun。
        """
        json_agent = getattr(agent, "json_agent", None)
        retry_count = getattr(json_agent, "max_retries", 0)
        prompt_version = getattr(agent, "prompt_version", None)
        token_usage = getattr(json_agent, "last_token_usage", None)
        return self.run_log_service.record_agent_run(
            AgentRunRecord(
                pipeline_run_id=run_id,
                candidate_id=candidate_id,
                dossier_id=dossier_id,
                agent_name=getattr(agent, "name", "unknown_agent"),
                agent_role=agent_role,
                model_provider=getattr(agent, "model_provider", None),
                model_name=getattr(agent, "model_name", None),
                prompt_version=prompt_version,
                input_summary=input_summary,
                output_json={},
                trace_json={
                    "pipeline": "p1-2-event-pipeline",
                    "llm_prompt_version": prompt_version,
                    "token_usage": token_usage,
                },
                status="failed",
                duration_ms=getattr(json_agent, "last_duration_ms", None),
                retry_count=retry_count,
                error_message=error_message,
            )
        )

    def finish_run_with_counts(
        self,
        run_id: str,
        status: str,
        summary: str,
        error_message: str | None = None,
    ) -> PipelineRun:
        """按最终数据库结果回填并结束 pipeline run。

        输入：run_id、最终状态、摘要和可选错误信息。
        输出：计数字段与最终入库结果一致的 PipelineRun。
        """
        run = self.session.get(PipelineRun, run_id)
        if run is None:
            raise ValueError(f"PipelineRun not found for id={run_id}")

        run.signals_count = self._count(SourceSignal.id, SourceSignal.pipeline_run_id == run_id)
        run.candidates_count = self._count(EventCandidate.id, EventCandidate.created_by_run_id == run_id)
        run.dossiers_count = self._count(EventDossier.id, EventDossier.generated_by_run_id == run_id)
        run.published_count = self.session.scalar(
            select(func.count(PublishedEvent.id))
            .join(EventDossier, PublishedEvent.dossier_id == EventDossier.id)
            .where(EventDossier.generated_by_run_id == run_id)
        ) or 0
        run.failed_count = 0 if status in {"succeeded", "manual_review"} else 1
        self.session.flush()
        return self.run_log_service.finish_pipeline_run(
            run_id,
            status=status,
            summary=summary,
            error_message=error_message,
        )

    def _signal_to_dict(self, signal: SourceSignal) -> dict[str, Any]:
        """把 SourceSignal ORM 转为 Agent 输入。

        输入：SourceSignal ORM 对象。
        输出：包含来源 key、标题、URL、摘要和热度指标的 dict。
        """
        return {
            "id": signal.id,
            "source_key": signal.source.source_key,
            "source_item_id": signal.source_item_id,
            "original_title": signal.original_title,
            "original_url": signal.original_url,
            "canonical_url": signal.canonical_url,
            "raw_summary": signal.raw_summary,
            "content_excerpt": signal.content_excerpt,
            "heat_metrics": signal.heat_metrics,
            "metadata": signal.metadata_json,
        }

    def _candidate_to_draft(self, candidate: EventCandidate) -> EventCandidateDraft:
        """把 EventCandidate ORM 还原为写作 stub 输入。

        输入：EventCandidate ORM 对象。
        输出：EventCandidateDraft。
        """
        return EventCandidateDraft(
            candidate_key=candidate.candidate_key,
            title=candidate.title,
            event_type=candidate.event_type,
            category=candidate.category,
            primary_subject=candidate.primary_subject,
            suggested_angle=candidate.suggested_angle,
            heat_score=candidate.heat_score,
            importance_score=candidate.importance_score,
            audience_value_score=candidate.audience_value_score,
            ranking_score=candidate.ranking_score,
            ranking_reason=candidate.ranking_reason or "P1-2 workflow candidate",
            merge_reason=candidate.merge_reason,
        )

    def _dossier_to_draft(self, dossier: EventDossier) -> EventDossierDraft:
        """把 EventDossier ORM 还原为审稿 stub 输入。

        输入：EventDossier ORM 对象。
        输出：EventDossierDraft。
        """
        candidate = self.session.get(EventCandidate, dossier.candidate_id)
        if candidate is None:
            raise ValueError(f"EventCandidate not found for id={dossier.candidate_id}")
        return EventDossierDraft(
            candidate_key=candidate.candidate_key,
            card_title=dossier.card_title,
            card_summary=dossier.card_summary,
            category=dossier.category,
            signal_label=dossier.signal_label,
            cover_image_url=dossier.cover_image_url,
            detail_title=dossier.detail_title,
            detail_summary=dossier.detail_summary,
            detail_body=dossier.detail_body,
            why_it_matters=dossier.why_it_matters,
            follow_up_points=dossier.follow_up_points,
            source_refs=dossier.source_refs,
            status=dossier.status,
        )

    def _count(self, column: Any, condition: Any) -> int:
        """执行简单计数查询。

        输入：计数字段和 where 条件。
        输出：匹配条件的行数。
        """
        return self.session.scalar(select(func.count(column)).where(condition)) or 0

    def _successful_agent_metadata(self, agent: Any | None) -> dict[str, Any]:
        """读取成功 Agent 调用的 LLM metadata。

        输入：Agent 实例；stub 或 None 会返回空 metadata。
        输出：provider、model、prompt_version、retry_count 和 raw_text 组成的 dict。
        """
        if agent is None:
            return {
                "model_provider": None,
                "model_name": None,
                "prompt_version": None,
                "retry_count": None,
                "duration_ms": None,
                "token_usage": None,
                "raw_text": None,
            }
        last_result = getattr(agent, "last_result", None)
        return {
            "model_provider": getattr(agent, "model_provider", None),
            "model_name": getattr(agent, "model_name", None),
            "prompt_version": getattr(last_result, "prompt_version", None) or getattr(agent, "prompt_version", None),
            "retry_count": getattr(last_result, "retry_count", None),
            "duration_ms": getattr(last_result, "duration_ms", None),
            "token_usage": getattr(last_result, "token_usage", None),
            "raw_text": getattr(last_result, "raw_text", None),
        }

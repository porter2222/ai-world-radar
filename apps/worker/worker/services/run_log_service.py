from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from worker.models import AgentRun, PipelineRun
from worker.schemas.run import AgentRunRecord, PipelineRunCreate


class RunLogService:
    """运行记录写入服务。

    输入：SQLAlchemy Session。
    输出：提供 PipelineRun 和 AgentRun 的最小写入能力。
    """

    def __init__(self, session: Session):
        """初始化服务。

        输入：外部传入且由调用方管理事务的 Session。
        输出：可复用的 RunLogService 实例。
        """
        self.session = session

    def start_pipeline_run(self, payload: PipelineRunCreate) -> PipelineRun:
        """创建 pipeline run 记录。

        输入：PipelineRunCreate payload。
        输出：刷新后的 PipelineRun ORM 对象。
        """
        run = PipelineRun(
            run_key=payload.run_key,
            trigger_type=payload.trigger_type,
            source_scope=payload.source_scope,
            status=payload.status,
            config_snapshot=payload.config_snapshot,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def finish_pipeline_run(
        self,
        run_id: str,
        *,
        status: str,
        summary: str = "",
        error_message: str | None = None,
    ) -> PipelineRun:
        """结束 pipeline run 并写入摘要。

        输入：run_id、最终状态、摘要和可选错误信息。
        输出：更新并刷新后的 PipelineRun ORM 对象。
        """
        run = self.session.get(PipelineRun, run_id)
        if run is None:
            raise ValueError(f"PipelineRun not found for id={run_id}")

        run.status = status
        run.summary = summary
        run.error_message = error_message
        run.ended_at = datetime.now(UTC)
        self.session.flush()
        return run

    def record_agent_run(self, payload: AgentRunRecord) -> AgentRun:
        """记录一次 Agent 运行。

        输入：AgentRunRecord payload。
        输出：刷新后的 AgentRun ORM 对象。
        """
        agent_run = AgentRun(
            pipeline_run_id=payload.pipeline_run_id,
            candidate_id=payload.candidate_id,
            dossier_id=payload.dossier_id,
            agent_name=payload.agent_name,
            agent_role=payload.agent_role,
            model_provider=payload.model_provider,
            model_name=payload.model_name,
            prompt_version=payload.prompt_version,
            input_summary=payload.input_summary,
            output_json=payload.output_json,
            trace_json=payload.trace_json,
            status=payload.status,
            duration_ms=payload.duration_ms,
            retry_count=payload.retry_count,
            error_message=payload.error_message,
        )
        self.session.add(agent_run)
        self.session.flush()
        return agent_run

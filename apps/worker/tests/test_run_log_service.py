from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from worker.models import Base
from worker.schemas.run import AgentRunRecord, PipelineRunCreate
from worker.services.run_log_service import RunLogService


def make_session():
    """创建运行记录服务测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 `autoflush=False` 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def test_pipeline_and_agent_run_logging():
    """验证 pipeline run 和 agent run 写入。

    输入：一次手动 pipeline run 和一次编辑 Agent 运行记录。
    输出：PipelineRun 可被 finish，AgentRun 关联到该 run。
    """
    session = make_session()
    service = RunLogService(session)

    run = service.start_pipeline_run(
        PipelineRunCreate(
            run_key="manual-20260612-001",
            trigger_type="manual",
            source_scope={"sources": ["hn_algolia"]},
        )
    )
    agent_run = service.record_agent_run(
        AgentRunRecord(
            pipeline_run_id=run.id,
            agent_name="值班编辑 Agent",
            agent_role="editor",
            status="succeeded",
            input_summary="1 signal",
            output_json={"candidate_count": 1},
            trace_json={"tool_calls": []},
        )
    )
    service.finish_pipeline_run(run.id, status="succeeded", summary="generated 1 candidate")

    assert run.status == "succeeded"
    assert run.summary == "generated 1 candidate"
    assert agent_run.pipeline_run_id == run.id

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from worker.models import AgentRun, Base, PipelineRun, PublishedEvent
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.signal_service import SignalService
from worker.workflows.event_pipeline import run_event_pipeline


def make_session():
    """创建 workflow 测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 autoflush=False 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def seed_signal(session):
    """写入一条 workflow 可消费的来源信号。

    输入：测试 Session。
    输出：SourceSignal ORM 对象。
    """
    service = SignalService(session)
    service.upsert_source(SourceCreate(source_key="demo", name="Demo", source_type="fixture", fetch_method="manual"))
    return service.upsert_signal(
        SourceSignalCreate(
            source_key="demo",
            source_item_id="demo-1",
            original_title="OpenAI releases a new developer tool",
            original_url="https://example.com/openai-tool",
            raw_summary="Developers discuss the new tool.",
            source_hash="demo:1",
            heat_metrics={"points": 120, "comments": 45},
        )
    )


def test_langgraph_pipeline_publishes_event_and_records_counts():
    """验证 LangGraph 工作流首跑即可发布事件并记录真实计数。

    输入：一条预置 SourceSignal 和 run_key。
    输出：PublishedEvent、PipelineRun、AgentRun 均入库，PipelineRun 计数等于最终表结果。
    """
    session = make_session()
    signal = seed_signal(session)

    state = run_event_pipeline(
        session,
        signal_ids=[signal.id],
        run_key="manual-p1-2-workflow",
        source_scope={"source": "demo"},
    )

    published_count = len(session.scalars(select(PublishedEvent)).all())
    agent_run_count = len(session.scalars(select(AgentRun)).all())
    run = session.scalar(select(PipelineRun))

    assert state.status == "succeeded"
    assert state.published_event_id is not None
    assert published_count == 1
    assert agent_run_count == 3
    assert run.signals_count == 1
    assert run.candidates_count == 1
    assert run.dossiers_count == 1
    assert run.published_count == published_count
    assert run.failed_count == 0

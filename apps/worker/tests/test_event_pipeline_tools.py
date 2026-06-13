from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from worker.models import Base, PublishedEvent
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.signal_service import SignalService
from worker.tools.event_pipeline_tools import EventPipelineTools


def make_session():
    """创建 tool 测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 autoflush=False 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def seed_signal(session):
    """写入一条 tool 可处理的来源信号。

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


def test_tools_create_publish_flow_and_update_run_counts():
    """验证工程 tool 通过服务层完成候选、档案、审稿、发布和 run 计数。

    输入：一条 SourceSignal 和确定性 Agent stub。
    输出：PublishedEvent 入库，PipelineRun 计数字段与最终数据库结果一致。
    """
    session = make_session()
    signal = seed_signal(session)
    tools = EventPipelineTools(session)
    run = tools.start_run(run_key="manual-p1-2-tools", source_scope={"source": "demo"})

    signals = tools.load_signals([signal.id])
    candidate = tools.create_candidate(signals)
    dossier = tools.create_dossier(candidate, signals)
    review = tools.review_dossier(dossier)
    published = tools.publish_if_approved(candidate.id, dossier.id, review.decision)
    finished_run = tools.finish_run_with_counts(run.id, status="succeeded", summary="tool smoke")

    assert published is not None
    assert session.scalar(select(PublishedEvent)).id == published.id
    assert finished_run.signals_count == 1
    assert finished_run.candidates_count == 1
    assert finished_run.dossiers_count == 1
    assert finished_run.published_count == 1
    assert finished_run.failed_count == 0

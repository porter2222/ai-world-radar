from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from worker.collectors.hn_algolia import HNStory
from worker.collectors.page_cache import PageFetchResult
from worker.db.models import Base, Brief, BriefItem, EvidenceCard, EventCluster, PipelineRun, PublishedEvent, Source
from worker.pipelines.hn_event_pipeline import HNEventPipeline


def make_story(hn_id: str, score: int) -> HNStory:
    """构造 pipeline 测试用 HNStory。

    输入：HN ID 和基础 points。
    输出：可进入 pipeline 的 HNStory。
    """
    return HNStory(
        hn_id=hn_id,
        title=f"OpenAI story {hn_id}",
        original_url=f"https://example.com/{hn_id}",
        author="tester",
        points=score,
        num_comments=5,
        created_at=None,
        created_at_i=None,
        story_text=None,
        hn_heat_score=score + 10,
        matched_query="OpenAI",
    )


def fake_page_fetcher(url: str | None, hn_id: str, runtime_dir: Path) -> PageFetchResult:
    """构造不访问网络的页面抓取函数。

    输入：URL、HN ID、runtime 目录。
    输出：固定成功状态的 PageFetchResult。
    """
    return PageFetchResult(
        url=url or "",
        page_title=f"Cached title {hn_id}",
        page_excerpt=f"Cached excerpt for {hn_id}",
        page_text_hash=f"hash-{hn_id}",
        page_cache_path=f"runtime/source-pages/2026-06-09/hn-{hn_id}-page.txt",
        fetch_status="success",
        fetched_at="2026-06-09T00:00:00+00:00",
    )


def count(session: Session, model: type) -> int:
    """统计测试数据库中的记录数。

    输入：Session 和 ORM model。
    输出：该表当前记录数。
    """
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_hn_event_pipeline_writes_core_records_and_is_idempotent(tmp_path):
    """验证 pipeline 写入核心记录并保持 PublishedEvent 幂等。

    输入：内存 SQLite、固定 HNStory、fake page fetcher。
    输出：断言 EvidenceCard/EventCluster/PublishedEvent/Brief 等记录数符合预期。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    stories = [make_story("1001", 50), make_story("1002", 80)]

    with Session(engine) as session:
        pipeline = HNEventPipeline(session=session, runtime_dir=tmp_path, page_fetcher=fake_page_fetcher)

        first = pipeline.run(days=7, limit=10, stories=stories)
        second = pipeline.run(days=7, limit=10, stories=stories)

        assert first.status == "success"
        assert second.status == "success"
        assert count(session, Source) == 1
        assert count(session, PipelineRun) == 2
        assert count(session, EvidenceCard) == 2
        assert count(session, EventCluster) == 2
        assert count(session, PublishedEvent) == 2
        assert count(session, Brief) == 2
        assert count(session, BriefItem) == 4


def test_hn_event_pipeline_first_run_creates_brief_with_autoflush_disabled(tmp_path):
    """验证生产式 autoflush=False 首跑也能生成简报。

    输入：autoflush=False 的 Session、单条 HNStory、fake page fetcher。
    输出：断言首跑 PublishedEvent、Brief、BriefItem 均入库，且 PipelineRun 计数准确。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    stories = [make_story("first-run-1001", 80)]

    with session_factory() as session:
        pipeline = HNEventPipeline(session=session, runtime_dir=tmp_path, page_fetcher=fake_page_fetcher)

        result = pipeline.run(days=7, limit=1, force=True, stories=stories)
        pipeline_run = session.get(PipelineRun, result.pipeline_run_id)

        assert result.status == "success"
        assert count(session, PublishedEvent) == 1
        assert count(session, Brief) == 1
        assert count(session, BriefItem) == 1
        assert result.published_event_count == 1
        assert result.brief_item_count == 1
        assert pipeline_run is not None
        assert pipeline_run.published_event_count == count(session, PublishedEvent)

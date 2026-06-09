from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from worker.collectors.hn_algolia import HNStory
from worker.collectors.page_cache import PageFetchResult
from worker.db.models import Base, Brief, BriefItem, EvidenceCard, EventCluster, PipelineRun, PublishedEvent, Source
from worker.pipelines.hn_event_pipeline import HNEventPipeline


def make_story(hn_id: str, score: int) -> HNStory:
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
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_hn_event_pipeline_writes_core_records_and_is_idempotent(tmp_path):
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

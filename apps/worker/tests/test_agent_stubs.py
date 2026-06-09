from worker.agents.brief_writer_agent import BriefWriterAgentStub
from worker.agents.detail_writer_agent import DetailWriterAgentStub
from worker.agents.evidence_agent import EvidenceAgentStub
from worker.agents.event_cluster_agent import EventClusterAgentStub
from worker.agents.quality_gate_agent import QualityGateAgentStub
from worker.agents.ranking_agent import RankingAgentStub
from worker.collectors.hn_algolia import HNStory
from worker.collectors.page_cache import PageFetchResult


def make_story() -> HNStory:
    return HNStory(
        hn_id="1001",
        title="OpenAI launches a new coding agent",
        original_url="https://example.com/openai-coding-agent",
        author="alice",
        points=41,
        num_comments=12,
        created_at=None,
        created_at_i=None,
        story_text=None,
        hn_heat_score=65,
        matched_query="OpenAI",
    )


def make_page() -> PageFetchResult:
    return PageFetchResult(
        url="https://example.com/openai-coding-agent",
        page_title="OpenAI coding agent",
        page_excerpt="OpenAI announced a coding agent for developers.",
        page_text_hash="abc123",
        page_cache_path="runtime/source-pages/2026-06-09/hn-1001-page.txt",
        fetch_status="success",
        fetched_at="2026-06-09T00:00:00+00:00",
    )


def test_agent_stubs_return_structured_outputs():
    evidence = EvidenceAgentStub().build(make_story(), make_page())
    cluster = EventClusterAgentStub().cluster(evidence)
    ranked = RankingAgentStub().rank(cluster)
    detail = DetailWriterAgentStub().write(ranked, evidence)
    gate = QualityGateAgentStub().check(detail)
    brief = BriefWriterAgentStub().write([detail])

    assert evidence["source_item_id"] == "1001"
    assert cluster["event_key"].startswith("hn-1001")
    assert ranked["publish_decision"] == "publish"
    assert detail["artifact_type"] == "event_detail"
    assert gate["recommended_action"] == "publish"
    assert brief["items"][0]["published_event_id"] == detail["published_event_id"]

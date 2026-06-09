import json
from pathlib import Path

from worker.collectors.hn_algolia import DEFAULT_QUERY_PROFILE, collect_from_algolia_payload, parse_algolia_hit


FIXTURE = Path(__file__).parent / "fixtures" / "hn_algolia_response.json"


def test_parse_algolia_hit_maps_required_story_fields():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    story = parse_algolia_hit(payload["hits"][0], query="OpenAI")

    assert story.hn_id == "1001"
    assert story.title == "OpenAI launches a new coding agent"
    assert story.original_url == "https://example.com/openai-coding-agent"
    assert story.points == 41
    assert story.num_comments == 12
    assert story.hn_heat_score == 65
    assert story.matched_query == "OpenAI"


def test_collect_from_algolia_payload_sorts_by_heat_score_descending():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    stories = collect_from_algolia_payload(payload, query="Claude", limit=10)

    assert [story.hn_id for story in stories] == ["1002", "1001"]
    assert stories[0].hn_heat_score == 80


def test_default_query_profile_contains_core_ai_terms():
    assert "OpenAI" in DEFAULT_QUERY_PROFILE
    assert "Claude" in DEFAULT_QUERY_PROFILE
    assert "MCP" in DEFAULT_QUERY_PROFILE

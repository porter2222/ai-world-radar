import json
from pathlib import Path

from worker.collectors.hn_algolia import DEFAULT_QUERY_PROFILE, collect_from_algolia_payload, parse_algolia_hit


FIXTURE = Path(__file__).parent / "fixtures" / "hn_algolia_response.json"


def test_parse_algolia_hit_maps_required_story_fields():
    """验证 Algolia hit 能映射为 HNStory。

    输入：fixture 中的单条 HN hit。
    输出：断言 ID、标题、URL、热度分和命中 query 正确。
    """
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
    """验证 payload 解析后按热度分降序排列。

    输入：包含重复项的 HN fixture payload。
    输出：断言去重后 story 顺序和热度分正确。
    """
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    stories = collect_from_algolia_payload(payload, query="Claude", limit=10)

    assert [story.hn_id for story in stories] == ["1002", "1001"]
    assert stories[0].hn_heat_score == 80


def test_default_query_profile_contains_core_ai_terms():
    """验证默认 query profile 覆盖核心 AI 关键词。

    输入：DEFAULT_QUERY_PROFILE。
    输出：断言 OpenAI、Claude、MCP 等关键词存在。
    """
    assert "OpenAI" in DEFAULT_QUERY_PROFILE
    assert "Claude" in DEFAULT_QUERY_PROFILE
    assert "MCP" in DEFAULT_QUERY_PROFILE

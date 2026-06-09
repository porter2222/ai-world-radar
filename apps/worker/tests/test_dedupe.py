from worker.collectors.hn_algolia import HNStory, dedupe_stories


def make_story(hn_id: str, url: str, score: int) -> HNStory:
    return HNStory(
        hn_id=hn_id,
        title=f"Story {hn_id}",
        original_url=url,
        author="tester",
        points=score,
        num_comments=0,
        created_at=None,
        created_at_i=None,
        story_text=None,
        hn_heat_score=score,
        matched_query="OpenAI",
    )


def test_dedupe_stories_prefers_higher_heat_for_same_hn_id():
    stories = [
        make_story("1001", "https://example.com/a", 10),
        make_story("1001", "https://example.com/b", 30),
    ]

    deduped = dedupe_stories(stories)

    assert len(deduped) == 1
    assert deduped[0].original_url == "https://example.com/b"


def test_dedupe_stories_removes_duplicate_urls_across_ids():
    stories = [
        make_story("1001", "https://example.com/same", 10),
        make_story("1002", "https://example.com/same", 20),
        make_story("1003", "https://example.com/other", 5),
    ]

    deduped = dedupe_stories(stories)

    assert [story.hn_id for story in deduped] == ["1002", "1003"]

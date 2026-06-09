from worker.collectors.hn_algolia import HNStory, dedupe_stories


def make_story(hn_id: str, url: str, score: int) -> HNStory:
    """构造去重测试用 HNStory。

    输入：HN ID、URL 和热度分。
    输出：可传给 `dedupe_stories` 的 HNStory。
    """
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
    """验证相同 HN ID 保留热度更高的一条。

    输入：两个 HN ID 相同但热度不同的 story。
    输出：断言只保留高热度 story。
    """
    stories = [
        make_story("1001", "https://example.com/a", 10),
        make_story("1001", "https://example.com/b", 30),
    ]

    deduped = dedupe_stories(stories)

    assert len(deduped) == 1
    assert deduped[0].original_url == "https://example.com/b"


def test_dedupe_stories_removes_duplicate_urls_across_ids():
    """验证不同 HN ID 但 URL 相同时也会去重。

    输入：两个 URL 相同、一个 URL 不同的 story。
    输出：断言重复 URL 只保留热度更高的一条。
    """
    stories = [
        make_story("1001", "https://example.com/same", 10),
        make_story("1002", "https://example.com/same", 20),
        make_story("1003", "https://example.com/other", 5),
    ]

    deduped = dedupe_stories(stories)

    assert [story.hn_id for story in deduped] == ["1002", "1003"]

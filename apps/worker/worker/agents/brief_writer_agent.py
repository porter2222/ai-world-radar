from __future__ import annotations


class BriefWriterAgentStub:
    """今日简报 stub。

    输入：已发布事件列表。
    输出：简报标题、概览和最多 5 条 brief item。
    """

    def write(self, published_events: list[dict]) -> dict:
        """从已发布事件生成简报。

        输入：PublishedEvent 风格的 dict 列表，已按排序分降序排列。
        输出：包含 title、overview、items 的简报 dict。
        """
        top_events = published_events[:5]
        return {
            "title": "AI World Radar 今日简报",
            "overview": f"本轮从 Hacker News 候选中生成 {len(top_events)} 条可发布事件。",
            "items": [
                {
                    "published_event_id": event["published_event_id"],
                    "item_title": event["title"],
                    "item_summary": event["summary"],
                    "item_reason": "进入简报是因为该事件在本轮排序中靠前。",
                    "sort_order": index + 1,
                }
                for index, event in enumerate(top_events)
            ],
        }

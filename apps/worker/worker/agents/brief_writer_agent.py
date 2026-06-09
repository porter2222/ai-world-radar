from __future__ import annotations


class BriefWriterAgentStub:
    def write(self, published_events: list[dict]) -> dict:
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
